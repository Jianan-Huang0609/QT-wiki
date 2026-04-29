"""QueryAgent - 基于索引召回的 Wiki 问答智能体."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from App.agents.structured_knowledge import build_structured_context
from wiki.indexing import build_index, load_page_index, rank_page_index
from wiki.models.page import PageSection, WikiPage
from wiki.store.files import load_all_pages, load_page, save_page

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = REPO_ROOT / "Raw"


@dataclass
class SearchResult:
    """搜索结果."""

    source_type: str
    source_id: str
    title: str
    content: str
    relevance_score: float
    source_refs: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class Answer:
    """回答结果."""

    question: str
    answer_text: str
    sources: list[SearchResult]
    confidence: float
    used_llm: bool = False


class QueryAgent:
    """查询智能体.

    主路径:
    1. 加载机器索引 pages.jsonl
    2. 基于问题召回少量候选页面
    3. 只加载候选页面正文和来源引用
    4. 基于受控上下文回答并返回引用
    """

    def __init__(self):
        self.history: list[dict] = []
        self.llm = None

    def _get_llm(self):
        """延迟初始化 LLM 客户端."""
        if self.llm is None:
            from Tool.llm.client import LLMTool

            self.llm = LLMTool()
        return self.llm

    def query(self, question: str, use_llm: bool = True, interactive: bool = False) -> Answer:
        """回答用户问题."""
        print(f"[QueryAgent] 问题: {question}")

        index_entries = self._load_or_build_index()
        ranked_entries = rank_page_index(question, index_entries, limit=5)
        pages = self._load_ranked_pages(ranked_entries)
        structured_context = build_structured_context(question, package_limit=4, relation_limit=10)
        print(f"[QueryAgent] 索引召回 {len(pages)} 个 Wiki 页面")

        if use_llm and pages:
            answer = self._ask_llm_with_retrieved_context(question, pages, ranked_entries, structured_context)
        else:
            answer = self._fallback_answer(question, pages, ranked_entries, structured_context)

        self.history.append(
            {
                "question": question,
                "answer": answer.answer_text,
                "sources": [result.source_id for result in answer.sources],
            }
        )

        if interactive and answer.confidence > 0.3:
            self._prompt_archive(question, answer)

        return answer

    def _load_or_build_index(self) -> list[dict[str, Any]]:
        entries = load_page_index()
        if entries:
            return entries
        if load_all_pages():
            build_index()
            return load_page_index()
        return []

    def _load_ranked_pages(self, ranked_entries: list[dict[str, Any]]) -> list[WikiPage]:
        pages: list[WikiPage] = []
        for entry in ranked_entries:
            page_id = entry.get("page_id", "")
            if not page_id:
                continue
            try:
                pages.append(load_page(page_id))
            except FileNotFoundError:
                continue
        return pages

    def _ask_llm_with_retrieved_context(
        self,
        question: str,
        pages: list[WikiPage],
        ranked_entries: list[dict[str, Any]],
        structured_context: dict[str, Any],
    ) -> Answer:
        context = self._build_retrieved_context(pages)
        structured_relations = structured_context.get("relations", [])
        relation_context = ""
        if structured_relations and any(kw in question for kw in ("关系", "映射", "对应", "关联", "要求", "实现", "约束", "记录", "职责")):
            relation_lines = ["\n--- 结构化关系 ---"]
            for rel in structured_relations:
                relation_lines.append(
                    f"- [{rel['relation_type']}] {rel['from_object_name']} → {rel['to_object_name']} "
                    f"({rel['claim_type']}, 置信度 {rel['confidence']:.0%})"
                )
            relation_context = "\n".join(relation_lines)

        prompt = f"""你是企业知识库问答专家。请只基于以下已召回的 Wiki 页面、来源引用和结构化关系回答问题。

用户问题: {question}

召回内容:
{context}
{relation_context}

输出格式:
相关页面: [页面标题1], [页面标题2]

回答:
[你的回答，必须包含引用，如 [来源: 页面标题]]

要求:
- 只能使用召回内容回答
- 如果召回内容不足，明确说明"根据现有 Wiki 内容，无法回答此问题"
- 不要编造未出现在召回内容或来源引用中的事实
- 回答尽量简洁，但必须保留可追溯来源
        - 若涉及法规与内部流程的映射关系，优先引用结构化关系中的 requires/produces/responsible_for"""

        try:
            llm_response = self._get_llm().ask(prompt, max_tokens=2000, temperature=0.2)
            answer_text, cited_titles = self._parse_llm_answer(llm_response)
            sources = self._sources_from_pages(pages, ranked_entries, cited_titles)
            confidence = 0.85 if sources else 0.35
            return Answer(question=question, answer_text=answer_text, sources=sources, confidence=confidence, used_llm=True)
        except Exception as exc:
            print(f"[QueryAgent] LLM 调用失败，回退到索引摘要回答: {exc}")
            return self._fallback_answer(question, pages, ranked_entries, structured_context)

    def _build_retrieved_context(self, pages: list[WikiPage]) -> str:
        lines: list[str] = []
        for page in pages:
            lines.extend(
                [
                    f"\n--- {page.title} ({page.page_type}) ---",
                    f"page_id: {page.page_id}",
                    f"摘要: {page.summary}",
                ]
            )
            for section in page.sections[:6]:
                content = section.content[:1200] if len(section.content) > 1200 else section.content
                lines.extend(["", f"[{section.heading}]", content])
                for ref in section.source_refs[:5]:
                    lines.append(f"来源: {_format_ref(ref)}")
            for ref in page.source_refs[:8]:
                lines.append(f"页面来源: {_format_ref(ref)}")
        return "\n".join(lines).strip()

    def _fallback_answer(
        self,
        question: str,
        pages: list[WikiPage],
        ranked_entries: list[dict[str, Any]],
        structured_context: dict[str, Any],
    ) -> Answer:
        structured_relations = structured_context.get("relations", [])
        if not pages and not structured_relations:
            return Answer(question=question, answer_text="抱歉，在 Wiki 索引中没有找到相关信息。", sources=[], confidence=0.0, used_llm=False)

        sources = self._sources_from_pages(pages, ranked_entries, [])
        lines: list[str] = []
        if structured_relations:
            lines.extend(["基于已批准的结构化映射：", ""])
            for relation in structured_relations[:5]:
                lines.append(
                    f"- {relation['from_object_name']} → {relation['to_object_name']} "
                    f"({relation['relation_type']}, {relation['claim_type']})"
                )
            lines.append("")
        if pages:
            lines.extend(["基于 Wiki 索引召回的相关页面：", ""])
        for source in sources[:3]:
            lines.append(f"- **{source.title}**: {source.content[:240]}...")
        confidence = 0.6 if structured_relations else min(1.0, sum(result.relevance_score for result in sources) / 12)
        return Answer(question=question, answer_text="\n".join(lines), sources=sources[:5], confidence=confidence, used_llm=False)

    def _sources_from_pages(
        self,
        pages: list[WikiPage],
        ranked_entries: list[dict[str, Any]],
        cited_titles: list[str],
    ) -> list[SearchResult]:
        score_by_page_id = {
            entry.get("page_id", ""): float(entry.get("relevance_score", 0.0))
            for entry in ranked_entries
        }
        cited = {title.strip() for title in cited_titles if title.strip()}
        selected_pages = pages
        if cited:
            cited_pages = [page for page in pages if page.title in cited]
            selected_pages = cited_pages or pages

        results: list[SearchResult] = []
        for page in selected_pages:
            content = page.summary
            if page.sections:
                content = f"{content} " + " ".join(section.content for section in page.sections[:3])
            results.append(
                SearchResult(
                    source_type="wiki",
                    source_id=page.page_id,
                    title=page.title,
                    content=content[:800],
                    relevance_score=score_by_page_id.get(page.page_id, 1.0),
                    source_refs=page.source_refs,
                )
            )
        results.sort(key=lambda item: item.relevance_score, reverse=True)
        return results

    def _parse_llm_answer(self, response: str) -> tuple[str, list[str]]:
        lines = response.strip().split("\n")
        answer_lines: list[str] = []
        cited_pages: list[str] = []
        in_answer = False

        for line in lines:
            line = line.strip()
            if not line:
                continue
            if line.startswith("相关页面:") or line.startswith("相关页面："):
                pages_text = line.split(":", 1)[1] if ":" in line else line.split("：", 1)[1]
                cited_pages = re.findall(r"\[(.*?)\]", pages_text)
                continue
            if line.startswith("回答:") or line.startswith("回答："):
                in_answer = True
                continue
            if in_answer:
                answer_lines.append(line)

        if not answer_lines:
            answer_lines = [line.strip() for line in lines if line.strip() and not line.startswith("相关页面")]

        answer_text = "\n".join(answer_lines).strip()
        if not cited_pages:
            cited_pages = re.findall(r"\[来源[:：]\s*(.*?)\]", answer_text)
        return answer_text, cited_pages

    def _prompt_archive(self, question: str, answer: Answer) -> None:
        try:
            print("\n" + "-" * 40)
            print("是否将此回答归档为 Wiki 页面？")
            print("输入页面标题归档，或按回车跳过")
            user_input = input("> ").strip()
            if user_input:
                page_id = self.archive_as_wiki_page(question, answer, user_input)
                print(f"[已归档] {page_id}" if page_id else "[归档失败]")
        except (EOFError, KeyboardInterrupt):
            pass

    def archive_as_wiki_page(self, question: str, answer: Answer, title: str = "") -> str | None:
        """将高价值问答归档为 Wiki 页面."""
        import datetime

        if not title:
            title = f"Q: {question[:30]}..."

        page_id = title.lower().replace(" ", "-").replace("?", "").replace("？", "")[:50]
        sources_text = "\n".join(f"- [{source.source_type}] {source.title}" for source in answer.sources)
        source_refs = [
            ref
            for source in answer.sources
            for ref in source.source_refs
            if source.source_type == "wiki"
        ]

        page = WikiPage(
            page_id=page_id,
            title=title,
            page_type="qa",
            summary=answer.answer_text[:500],
            sections=[
                PageSection(heading="问题", content=question, source_refs=[]),
                PageSection(heading="回答", content=answer.answer_text, source_refs=source_refs),
                PageSection(heading="来源", content=sources_text, source_refs=source_refs),
            ],
            source_refs=source_refs,
            linked_pages=[source.source_id for source in answer.sources if source.source_type == "wiki"],
            review_status="published",
            page_version=1,
            updated_at=datetime.datetime.now().isoformat(timespec="seconds"),
        )

        save_page(page)
        build_index()
        print(f"[QueryAgent] 已归档为 Wiki 页面: {page_id}")
        return page_id

    def interactive_query(self) -> None:
        """交互式查询模式."""
        print("\n" + "=" * 50)
        print("QueryAgent 交互模式")
        print("输入问题获取回答，输入 'archive <标题>' 归档最后回答，输入 'quit' 退出")
        print("=" * 50 + "\n")

        last_answer = None
        last_question = None

        while True:
            try:
                user_input = input("\n[Q] ").strip()
                if user_input.lower() == "quit":
                    break
                if user_input.lower().startswith("archive "):
                    if last_answer and last_question:
                        self.archive_as_wiki_page(last_question, last_answer, user_input[8:].strip())
                        last_answer = None
                    else:
                        print("[QueryAgent] 没有可归档的回答")
                    continue
                if user_input:
                    answer = self.query(user_input)
                    last_answer = answer
                    last_question = user_input
                    print(f"\n[A] (置信度: {answer.confidence:.2f})")
                    print(answer.answer_text)
                    print("\n[提示] 输入 'archive <标题>' 将此回答归档为 Wiki 页面")
            except KeyboardInterrupt:
                break
            except Exception as exc:
                print(f"[QueryAgent] 错误: {exc}")

        print("\n[QueryAgent] 再见!")


def _format_ref(ref: dict[str, Any]) -> str:
    parts = [
        ref.get("document_id", ""),
        ref.get("fragment_id", ""),
        ref.get("anchor_label", ""),
        ref.get("file_name", ""),
    ]
    quote = str(ref.get("quote", "")).strip()
    suffix = f" | {quote[:160]}" if quote else ""
    return " / ".join(str(part) for part in parts if part) + suffix


if __name__ == "__main__":
    import sys

    agent = QueryAgent()
    if len(sys.argv) < 2:
        agent.interactive_query()
    else:
        question = " ".join(sys.argv[1:])
        answer = agent.query(question)
        print(f"\n[A] (置信度: {answer.confidence:.2f})")
        print(answer.answer_text)
