"""QueryAgent - 查询智能体，向 Wiki 提问并归档好答案."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

REPO_ROOT = Path(__file__).resolve().parents[2]
PAGE_DIR = REPO_ROOT / "wiki" / "output" / "pages"
RAW_DIR = REPO_ROOT / "Raw"


@dataclass
class SearchResult:
    """搜索结果."""

    source_type: str  # wiki, raw
    source_id: str
    title: str
    content: str
    relevance_score: float


@dataclass
class Answer:
    """回答结果."""

    question: str
    answer_text: str
    sources: list[SearchResult]
    confidence: float


class QueryAgent:
    """查询智能体.

    工作流:
    1. 理解用户问题
    2. 将整个 Wiki 传给 LLM，让它自己决定检索什么
    3. 综合信息生成回答（使用 LLM）
    4. 提供引用来源
    5. 询问用户是否将好答案归档为 Wiki 页面
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
        """回答用户问题.

        Args:
            question: 用户问题
            use_llm: 是否使用 LLM 生成回答
            interactive: 是否交互式询问归档

        Returns:
            回答结果
        """
        print(f"[QueryAgent] 问题: {question}")

        # 1. 加载所有 Wiki 内容
        wiki_pages = self._load_all_wiki_pages()
        print(f"[QueryAgent] 加载了 {len(wiki_pages)} 个 Wiki 页面")

        # 2. 使用 LLM 进行智能检索和回答
        if use_llm and wiki_pages:
            answer = self._ask_llm_with_full_context(question, wiki_pages)
        else:
            # 回退到简单检索
            answer = self._fallback_search(question, wiki_pages)

        # 3. 记录历史
        self.history.append(
            {
                "question": question,
                "answer": answer.answer_text,
                "sources": [r.source_id for r in answer.sources],
            }
        )

        # 4. 交互式询问是否归档
        if interactive and answer.confidence > 0.3:
            self._prompt_archive(question, answer)

        return answer

    def _load_all_wiki_pages(self) -> list[dict]:
        """加载所有 Wiki 页面."""
        pages = []
        if not PAGE_DIR.exists():
            return pages

        for file_path in PAGE_DIR.glob("*.json"):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    page = json.load(f)
                    page["_file"] = file_path.name
                    pages.append(page)
            except Exception:
                continue

        return pages

    def _ask_llm_with_full_context(self, question: str, wiki_pages: list[dict]) -> Answer:
        """使用 LLM 基于完整 Wiki 内容回答问题."""
        # 构建 Wiki 索引
        wiki_index = self._build_wiki_index(wiki_pages)

        # 构建提示词
        prompt = f"""你是企业知识库问答专家。请基于以下 Wiki 知识库内容，回答用户问题。

用户问题: {question}

Wiki 知识库内容:
{wiki_index}

请按以下格式输出:
1. 首先，列出你认为相关的 Wiki 页面（引用页面标题）
2. 然后，基于相关内容回答问题
3. 如果信息不足，明确说明

输出格式:
相关页面: [页面标题1], [页面标题2]

回答:
[你的回答，包含引用如 [来源: 页面标题]]

要求:
- 只基于提供的 Wiki 内容回答
- 如果 Wiki 中没有相关信息，明确说明"根据现有 Wiki 内容，无法回答此问题"
- 回答要准确、简洁
- 必须标注引用来源"""

        try:
            llm_response = self._get_llm().ask(prompt, max_tokens=2000, temperature=0.3)

            # 解析 LLM 响应
            answer_text, cited_pages = self._parse_llm_answer(llm_response)

            # 构建搜索结果
            sources = []
            for page_title in cited_pages:
                for page in wiki_pages:
                    if page.get("title") == page_title:
                        sources.append(
                            SearchResult(
                                source_type="wiki",
                                source_id=page.get("page_id", ""),
                                title=page_title,
                                content=page.get("summary", ""),
                                relevance_score=1.0,
                            )
                        )
                        break

            confidence = 0.9 if sources else 0.3

            return Answer(
                question=question,
                answer_text=answer_text,
                sources=sources,
                confidence=confidence,
            )

        except Exception as e:
            print(f"[QueryAgent] LLM 调用失败，回退到简单检索: {e}")
            return self._fallback_search(question, wiki_pages)

    def _build_wiki_index(self, wiki_pages: list[dict]) -> str:
        """构建 Wiki 索引文本."""
        lines = []

        for page in wiki_pages:
            title = page.get("title", "")
            page_type = page.get("page_type", "")
            summary = page.get("summary", "")

            lines.append(f"\n--- {title} ({page_type}) ---")
            lines.append(f"摘要: {summary}")

            # 添加所有章节内容
            for section in page.get("sections", []):
                heading = section.get("heading", "")
                content = section.get("content", "")
                if content:
                    lines.append(f"\n[{heading}]")
                    lines.append(content[:1000] if len(content) > 1000 else content)

            lines.append("")

        return "\n".join(lines)

    def _parse_llm_answer(self, response: str) -> tuple[str, list[str]]:
        """解析 LLM 的回答，提取答案和引用的页面."""
        lines = response.strip().split("\n")

        answer_lines = []
        cited_pages = []
        in_answer = False

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # 提取相关页面
            if line.startswith("相关页面:") or line.startswith("相关页面："):
                pages_text = line.split(":", 1)[1] if ":" in line else line.split("：", 1)[1] if "：" in line else ""
                # 提取方括号中的页面名
                import re
                cited_pages = re.findall(r'\[(.*?)\]', pages_text)
                continue

            # 开始回答部分
            if line.startswith("回答:") or line.startswith("回答："):
                in_answer = True
                continue

            if in_answer:
                answer_lines.append(line)

        # 如果没有明确的"回答:"标记，使用所有非相关页面行
        if not answer_lines:
            for line in lines:
                if not line.startswith("相关页面"):
                    answer_lines.append(line)

        answer_text = "\n".join(answer_lines).strip()

        # 如果没有提取到引用页面，从回答中尝试提取
        if not cited_pages:
            import re

            cited_pages = re.findall(r'\[来源[:：]\s*(.*?)\]', answer_text)

        return answer_text, cited_pages

    def _fallback_search(self, question: str, wiki_pages: list[dict]) -> Answer:
        """回退到简单关键词检索."""
        keywords = self._extract_keywords(question)
        results = []

        for page in wiki_pages:
            score = self._calculate_relevance(page, keywords)
            if score > 0:
                content = page.get("summary", "")
                if page.get("sections"):
                    content += " " + " ".join(
                        s.get("content", "") for s in page["sections"]
                    )

                results.append(
                    SearchResult(
                        source_type="wiki",
                        source_id=page.get("page_id", ""),
                        title=page.get("title", ""),
                        content=content[:500],
                        relevance_score=score,
                    )
                )

        results.sort(key=lambda x: x.relevance_score, reverse=True)

        if results:
            answer_text = f"基于 Wiki 中的相关页面:\n\n"
            for r in results[:3]:
                answer_text += f"- **{r.title}**: {r.content[:200]}...\n"
            confidence = min(1.0, sum(r.relevance_score for r in results) / 5)
        else:
            answer_text = "抱歉，在 Wiki 中没有找到相关信息。"
            confidence = 0.0

        return Answer(
            question=question,
            answer_text=answer_text,
            sources=results[:5],
            confidence=confidence,
        )

    def _extract_keywords(self, query: str) -> list[str]:
        """提取查询关键词."""
        stopwords = {"的", "了", "和", "是", "在", "有", "什么", "如何", "怎么", "吗", "呢", "请", "问"}
        words = re.findall(r"[\u4e00-\u9fa5]{2,}|[a-zA-Z]{2,}", query)
        return [w for w in words if w not in stopwords]

    def _calculate_relevance(self, page: dict, keywords: list[str]) -> float:
        """计算页面与关键词的相关性."""
        score = 0.0
        text = (page.get("title", "") + " " + page.get("summary", "")).lower()

        for keyword in keywords:
            if keyword.lower() in text:
                score += 1.0

        for section in page.get("sections", []):
            section_text = (section.get("heading", "") + " " + section.get("content", "")).lower()
            for keyword in keywords:
                if keyword.lower() in section_text:
                    score += 0.5

        return score

    def _prompt_archive(self, question: str, answer: Answer):
        """询问用户是否归档为 Wiki 页面."""
        try:
            print("\n" + "-" * 40)
            print("是否将此回答归档为 Wiki 页面？")
            print("输入页面标题归档，或按回车跳过")
            user_input = input("> ").strip()

            if user_input:
                page_id = self.archive_as_wiki_page(question, answer, user_input)
                if page_id:
                    print(f"[已归档] {page_id}")
                else:
                    print("[归档失败]")
        except (EOFError, KeyboardInterrupt):
            pass

    def archive_as_wiki_page(self, question: str, answer: Answer, title: str = "") -> str | None:
        """将好的回答归档为 Wiki 页面."""
        from wiki.models.page import WikiPage
        from wiki.store.files import PAGE_DIR
        import datetime

        if not title:
            title = f"Q: {question[:30]}..."

        page_id = title.lower().replace(" ", "-").replace("?", "").replace("？", "")[:50]

        sources_text = "\n".join(f"- [{s.source_type}] {s.title}" for s in answer.sources)

        page = WikiPage(
            page_id=page_id,
            title=title,
            page_type="qa",
            summary=answer.answer_text[:500],
            sections=[
                {
                    "heading": "问题",
                    "content": question,
                    "source_refs": [],
                },
                {
                    "heading": "回答",
                    "content": answer.answer_text,
                    "source_refs": [],
                },
                {
                    "heading": "来源",
                    "content": sources_text,
                    "source_refs": [{"document_id": s.source_id} for s in answer.sources if s.source_type == "raw"],
                },
            ],
            source_refs=[{"document_id": s.source_id} for s in answer.sources if s.source_type == "raw"],
            linked_pages=[s.source_id for s in answer.sources if s.source_type == "wiki"],
            review_status="published",
            page_version=1,
            updated_at=datetime.datetime.now().isoformat(),
        )

        file_path = PAGE_DIR / f"{page_id}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(page.to_dict(), f, ensure_ascii=False, indent=2)

        print(f"[QueryAgent] 已归档为 Wiki 页面: {page_id}")
        return page_id

    def interactive_query(self):
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
                        title = user_input[8:].strip()
                        self.archive_as_wiki_page(last_question, last_answer, title)
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
            except Exception as e:
                print(f"[QueryAgent] 错误: {e}")

        print("\n[QueryAgent] 再见!")


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
