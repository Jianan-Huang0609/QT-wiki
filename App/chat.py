from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from Tool.llm.client import ask_llm
from wiki.index.local import CitationHit, LocalWikiIndex, PageHit

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class Citation:
    citation_id: str
    page_id: str
    page_title: str
    document_id: str
    fragment_id: str
    file_name: str
    anchor_label: str
    quote: str
    score: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class MatchedPage:
    page_id: str
    title: str
    summary: str
    score: float
    page_type: str
    linked_pages: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ChatAnswer:
    answer: str
    citations: list[Citation]
    matched_pages: list[MatchedPage]
    confidence: str
    used_llm: bool
    question: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "answer": self.answer,
            "citations": [citation.to_dict() for citation in self.citations],
            "matched_pages": [page.to_dict() for page in self.matched_pages],
            "confidence": self.confidence,
            "used_llm": self.used_llm,
            "question": self.question,
        }


class ChatbotService:
    def __init__(self, *, index: LocalWikiIndex | None = None) -> None:
        self.index = index or LocalWikiIndex()
        self._is_ready = False

    def reindex(self) -> dict[str, int]:
        self.index.refresh()
        self._is_ready = True
        summary = {
            "pages": len(self.index.pages),
            "documents": len(self.index.doc_lookup),
            "fragments": len(self.index.fragment_lookup),
        }
        LOGGER.info("聊天检索索引刷新完成：%s", json.dumps(summary, ensure_ascii=False))
        return summary

    def answer_question(
        self,
        question: str,
        *,
        use_llm: bool = False,
        top_k_pages: int = 5,
        top_k_citations: int = 8,
    ) -> ChatAnswer:
        if not self._is_ready:
            self.reindex()

        LOGGER.info("收到问题：%s", question)
        page_hits = self.index.search_pages(question, top_k=top_k_pages)
        LOGGER.info("页面检索完成：命中 %s 个页面", len(page_hits))
        citation_hits = self.index.collect_citations(question, page_hits, top_k=top_k_citations)
        LOGGER.info("证据片段检索完成：命中 %s 个片段", len(citation_hits))

        matched_pages = [
            MatchedPage(
                page_id=hit.page_id,
                title=hit.title,
                summary=hit.summary,
                score=round(hit.score, 4),
                page_type=hit.page_type,
                linked_pages=hit.linked_pages,
            )
            for hit in page_hits
        ]
        citations = [
            Citation(
                citation_id=f"c{index}",
                page_id=hit.page_id,
                page_title=hit.page_title,
                document_id=hit.document_id,
                fragment_id=hit.fragment_id,
                file_name=hit.file_name,
                anchor_label=hit.anchor_label,
                quote=hit.quote,
                score=round(hit.score, 4),
            )
            for index, hit in enumerate(citation_hits, start=1)
        ]

        if not matched_pages:
            LOGGER.info("未命中任何页面，返回证据不足回答")
            return ChatAnswer(
                question=question,
                answer="现有 Wiki 证据不足以回答该问题。",
                citations=[],
                matched_pages=[],
                confidence="low",
                used_llm=False,
            )

        answer = self._build_fallback_answer(question, matched_pages, citations)
        used_llm = False
        if use_llm and citations:
            try:
                LOGGER.info("开始调用 LLM 生成问答回复：页面=%s，片段=%s", len(matched_pages), len(citations))
                llm_answer = ask_llm(
                    _build_chat_prompt(question, matched_pages, citations),
                    temperature=0.2,
                    max_tokens=800,
                    system=(
                        "你是企业Wiki问答助手。"
                        "只能依据提供的页面摘要和证据片段回答，不要编造来源。"
                        "优先回答有证据支持的部分，并在相关句子后标注[c1][c2]。"
                        "如果问题有部分内容缺少证据，请单独列出“未覆盖点”，说明哪些部分当前无法确认。"
                        "在存在可用证据时，不要直接给出笼统的“证据不足无法回答”。"
                        "回答中引用证据时使用[c1][c2]这样的编号，不要编造来源。"
                    ),
                )
                if _is_insufficient_answer(llm_answer):
                    LOGGER.warning("LLM 返回证据不足模板，已回退为规则式回答：问题=%s", question)
                else:
                    answer = llm_answer
                    used_llm = True
                    LOGGER.info("LLM 问答回复生成完成")
            except Exception:
                LOGGER.exception("LLM 问答回复失败，回退到规则式回答")

        confidence = _confidence_label(matched_pages, citations)
        if _is_insufficient_answer(answer):
            confidence = "low"
        LOGGER.info("问题回答完成：confidence=%s，used_llm=%s", confidence, used_llm)
        return ChatAnswer(
            question=question,
            answer=answer,
            citations=citations,
            matched_pages=matched_pages,
            confidence=confidence,
            used_llm=used_llm,
        )

    def _build_fallback_answer(
        self,
        question: str,
        matched_pages: list[MatchedPage],
        citations: list[Citation],
    ) -> str:
        top_pages = matched_pages[:2]
        answer_lines = [f"针对“{question}”，当前 Wiki 中可直接参考以下内容："]
        for page in top_pages:
            page_citation_ids = [citation.citation_id for citation in citations if citation.page_id == page.page_id][:2]
            citation_suffix = " ".join(f"[{citation_id}]" for citation_id in page_citation_ids)
            summary = page.summary.strip() or "该页面当前没有可用摘要。"
            answer_lines.append(f"《{page.title}》：{summary} {citation_suffix}".rstrip())

        if citations:
            answer_lines.append("可优先查看的证据片段：")
            for citation in citations[:3]:
                answer_lines.append(
                    f"- [{citation.citation_id}] {citation.file_name} {citation.anchor_label}：{_trim(citation.quote, 120)}"
                )
        else:
            answer_lines.append("当前没有检索到可直接引用的证据片段。")
        return "\n".join(answer_lines)


def _build_chat_prompt(question: str, matched_pages: list[MatchedPage], citations: list[Citation]) -> str:
    page_lines = []
    for page in matched_pages[:5]:
        page_lines.append(
            f"- 页面《{page.title}》\n"
            f"  类型: {page.page_type}\n"
            f"  摘要: {page.summary or '无'}"
        )

    citation_lines = []
    for citation in citations[:8]:
        citation_lines.append(
            f"- [{citation.citation_id}] 页面《{citation.page_title}》 | "
            f"{citation.file_name} {citation.anchor_label}\n"
            f"  片段: {citation.quote}"
        )

    return (
        f"用户问题：{question}\n\n"
        "候选页面：\n"
        f"{chr(10).join(page_lines)}\n\n"
        "证据片段：\n"
        f"{chr(10).join(citation_lines)}\n\n"
        "请先输出“回答”，优先回答有证据支持的内容并附引用编号。"
        "如果有无法覆盖的部分，再输出“未覆盖点”并说明原因。"
    )


def _trim(text: str, limit: int) -> str:
    clean = " ".join(text.split())
    if len(clean) <= limit:
        return clean
    return clean[:limit].rstrip() + "..."


def _confidence_label(matched_pages: list[MatchedPage], citations: list[Citation]) -> str:
    if not matched_pages:
        return "low"
    top_score = matched_pages[0].score
    if top_score >= 3 and len(citations) >= 2:
        return "high"
    if top_score >= 1 or citations:
        return "medium"
    return "low"


def _is_insufficient_answer(answer: str) -> bool:
    compact = "".join(answer.split())
    if not compact:
        return True

    hard_patterns = (
        "现有Wiki证据不足以回答该问题",
        "现有wiki证据不足以回答该问题",
        "证据不足以回答",
    )
    if any(pattern in compact for pattern in hard_patterns):
        return True

    soft_patterns = ("证据不足", "信息不足", "无法回答", "无法判断", "缺少依据")
    return len(compact) <= 80 and any(pattern in compact for pattern in soft_patterns)
