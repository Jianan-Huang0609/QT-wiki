from __future__ import annotations

import argparse
import logging
import re
from datetime import datetime

from Tool.contracts.canonical import CanonicalDocument, Fragment, load_canonical_document
from Tool.llm.client import ask_llm
from Tool.llm.prompts import build_summary_prompt
from Tool.pipelines.common import PARSED_DIR
from wiki.models.page import PageChangeCandidate, PageSection, WikiPage
from wiki.store.files import save_page

LOGGER = logging.getLogger(__name__)
SUCCESS_PARSE_STATUSES = {"parsed", "partially_parsed"}

PAGE_BLUEPRINTS = [
    {
        "page_id": "医疗器械生产质量管理规范",
        "title": "医疗器械生产质量管理规范",
        "page_type": "policy",
        "aliases": ["生产质量管理规范", "QMS规范"],
        "keywords": ["医疗器械生产质量管理规范", "规范", "质量管理规范"],
        "section_keywords": ["第一章总则", "第二章质量保证", "第十五章附则"],
        "linked_pages": ["质量管理体系", "风险管理"],
    },
    {
        "page_id": "质量管理体系",
        "title": "质量管理体系",
        "page_type": "concept",
        "aliases": ["QMS"],
        "keywords": ["质量管理体系", "质量目标", "质量保证系统", "持续改进"],
        "section_keywords": ["第一章总则", "第二章质量保证"],
        "linked_pages": ["风险管理", "机构与人员职责"],
    },
    {
        "page_id": "风险管理",
        "title": "风险管理",
        "page_type": "concept",
        "aliases": ["质量风险管理"],
        "keywords": ["风险管理", "质量风险", "风险控制"],
        "section_keywords": ["第二章质量保证", "第十四章分析与改进"],
        "linked_pages": ["质量管理体系"],
    },
    {
        "page_id": "机构与人员职责",
        "title": "机构与人员职责",
        "page_type": "role",
        "aliases": ["岗位职责"],
        "keywords": ["管理者代表", "质量管理部门", "生产管理部门", "产品放行", "职责"],
        "section_keywords": ["第三章机构与人员"],
        "linked_pages": ["质量管理体系", "产品放行"],
    },
    {
        "page_id": "文件和数据管理",
        "title": "文件和数据管理",
        "page_type": "process",
        "aliases": ["文件控制", "电子记录"],
        "keywords": ["文件和数据管理", "文件控制", "记录控制", "电子记录", "电子签名"],
        "section_keywords": ["第六章文件和数据管理", "文件和数据管理"],
        "linked_pages": ["质量管理体系"],
    },
    {
        "page_id": "设备管理",
        "title": "设备管理",
        "page_type": "process",
        "aliases": ["设备与仪器"],
        "keywords": ["设备", "仪器", "校准", "检定", "维护和维修"],
        "section_keywords": ["第五章设备", "设备"],
        "linked_pages": ["质量管理体系"],
    },
    {
        "page_id": "采购与原材料管理",
        "title": "采购与原材料管理",
        "page_type": "process",
        "aliases": ["供应商管理"],
        "keywords": ["采购", "原材料", "供应商", "关键供应商", "验收准则"],
        "section_keywords": ["第八章采购与原材料管理"],
        "linked_pages": ["质量管理体系"],
    },
    {
        "page_id": "产品放行",
        "title": "产品放行",
        "page_type": "process",
        "aliases": ["放行审核"],
        "keywords": ["产品放行", "放行审核", "放行审核人"],
        "section_keywords": ["第十一章质量控制与产品放行"],
        "linked_pages": ["机构与人员职责", "质量管理体系"],
    },
]

ARTICLE_RE = re.compile(r"^第[一二三四五六七八九十百零〇\d]+条")
SECTION_HEADING_RE = re.compile(r"^第[一二三四五六七八九十百零〇\d]+章")
PAGE_HEADER_RE = re.compile(r"^\d{4}/\d{1,2}/\d{1,2}\s+\d+\s+")
ARTICLE_HEADING_RE = re.compile(r"^第[一二三四五六七八九十百零〇\d]+条[）)]")
NOISE_MARKERS = ("目录", "本章要点", "理解要点", "分享人", "教师简介", "本资料仅限于内部研讨使用")
SUBSTANTIVE_MARKERS = ("应当", "应", "不得", "可以", "负责", "建立", "保存", "记录", "校准", "检定", "放行")


def build_page_candidates(*, use_llm: bool = False) -> list[PageChangeCandidate]:
    parsed_docs = _load_parsed_documents()
    LOGGER.info("开始首次建库：已解析文档数=%s，启用LLM=%s", len(parsed_docs), use_llm)
    candidates: list[PageChangeCandidate] = []
    for blueprint in PAGE_BLUEPRINTS:
        refs = _collect_refs(parsed_docs, blueprint)
        summary = _build_summary(blueprint["title"], refs, use_llm=use_llm)
        sections = []
        if refs:
            evidence_lines = [
                f"- {ref['quote']} ({ref['file_name']} {ref['anchor_label']})"
                for ref in refs[:8]
            ]
            sections.append(PageSection(heading="关键依据", content="\n".join(evidence_lines), source_refs=refs[:8]))
        page = WikiPage(
            page_id=blueprint["page_id"],
            title=blueprint["title"],
            page_type=blueprint["page_type"],
            summary=summary,
            sections=sections,
            aliases=blueprint["aliases"],
            source_refs=refs,
            linked_pages=blueprint["linked_pages"],
            review_status="approved" if refs else "needs_review",
            page_version=1,
            updated_at=datetime.now().isoformat(timespec="seconds"),
        )
        candidates.append(
            PageChangeCandidate(
                page=page,
                action="bootstrap_page",
                candidate_content=_render_candidate_content(page),
                source_refs=refs,
                evidence_fragment_ids=[ref["fragment_id"] for ref in refs if ref.get("fragment_id")],
                source_document_ids=sorted({ref["document_id"] for ref in refs if ref.get("document_id")}),
                tool_trace=["wiki.builders.bootstrap.build_page_candidates"],
            )
        )
    return candidates


def bootstrap_pages(*, use_llm: bool = False) -> list[WikiPage]:
    pages: list[WikiPage] = []
    for candidate in build_page_candidates(use_llm=use_llm):
        page = candidate.page
        save_page(page)
        pages.append(page)
        LOGGER.info("页面已生成：page_id=%s，证据数=%s", page.page_id, len(page.source_refs))
    return pages


def _load_parsed_documents() -> list[CanonicalDocument]:
    if not PARSED_DIR.exists():
        return []
    documents: list[CanonicalDocument] = []
    for path in sorted(PARSED_DIR.glob("*.json")):
        document = load_canonical_document(path)
        if document.parse_status not in SUCCESS_PARSE_STATUSES:
            continue
        documents.append(document)
    return documents


def _collect_refs(parsed_docs: list[CanonicalDocument], blueprint: dict) -> list[dict]:
    scored_refs: list[tuple[int, str, dict]] = []
    seen: set[tuple[str, str]] = set()
    for document in parsed_docs:
        for score, ref in _collect_refs_for_document(document, blueprint):
            key = (ref["document_id"], ref["fragment_id"])
            if key in seen:
                continue
            seen.add(key)
            scored_refs.append((score, ref["fragment_id"], ref))

    scored_refs.sort(key=lambda item: (-item[0], item[1]))
    return [ref for _, _, ref in scored_refs[:20]]


def _collect_refs_for_document(document: CanonicalDocument, blueprint: dict) -> list[tuple[int, dict]]:
    refs: list[dict] = []
    section_titles = {section.section_id: _compact_text(section.title) for section in document.sections}
    for fragment in document.fragments:
        section_title = section_titles.get(fragment.section_id, "")
        score = _fragment_match_score(fragment, blueprint, section_title=section_title)
        if score > 0 and document.document.doc_type == "policy":
            score += 3
        elif score > 0 and document.document.doc_type == "presentation":
            score -= 2
        elif score > 0 and document.document.doc_type == "guidance" and not ARTICLE_RE.match(normalize_fragment_text(fragment.text)):
            score -= 1
        if score <= 0:
            continue
        refs.append((score, _fragment_ref(document, fragment)))
    return refs


def _matches(fragment: Fragment, keywords: set[str]) -> bool:
    text = fragment.text
    return any(keyword in text for keyword in keywords)


def _fragment_match_score(fragment: Fragment, blueprint: dict, *, section_title: str = "") -> int:
    text = normalize_fragment_text(fragment.text)
    compact_text = _compact_text(text)
    compact_section = _compact_text(section_title)
    if _is_noise_fragment(text):
        return 0

    score = 0
    for marker in blueprint.get("section_keywords", []):
        compact_marker = _compact_text(marker)
        if compact_marker and compact_marker in compact_section:
            score += 8

    title_terms = [blueprint["title"], *blueprint.get("aliases", [])]
    for term in title_terms:
        compact_term = _compact_text(term)
        if compact_term and compact_term in compact_text:
            score += 4
        if compact_term and compact_term in compact_section:
            score += 4

    for keyword in blueprint.get("keywords", []):
        compact_keyword = _compact_text(keyword)
        if compact_keyword and compact_keyword in compact_text:
            score += 2
        if compact_keyword and compact_keyword in compact_section:
            score += 2

    if score > 0 and any(marker in text for marker in SUBSTANTIVE_MARKERS):
        score += 3
    if score > 0 and ARTICLE_RE.match(text):
        score += 1
    if score > 0 and fragment.section_id:
        score += 1
    return score


def normalize_fragment_text(text: str) -> str:
    return " ".join(text.split())


def _compact_text(text: str) -> str:
    return re.sub(r"[\s:：、，。；（）()【】\[\]“”\"'·\-_/]+", "", text)


def _is_noise_fragment(text: str) -> bool:
    normalized = normalize_fragment_text(text)
    if len(normalized) < 8:
        return True
    if any(marker in normalized for marker in NOISE_MARKERS):
        return True
    if PAGE_HEADER_RE.match(normalized):
        return True
    if SECTION_HEADING_RE.match(normalized) and len(normalized) <= 40:
        return True
    if "章节条款数对比" in normalized or "变化率" in normalized:
        return True
    if ARTICLE_HEADING_RE.match(normalized) and "（总" in normalized and not any(marker in normalized for marker in SUBSTANTIVE_MARKERS):
        return True
    return normalized.endswith("（“规范”")


def _fragment_ref(document: CanonicalDocument, fragment: Fragment) -> dict:
    anchors = fragment.anchors
    if "page" in anchors:
        anchor_label = f"p.{anchors['page']}"
    elif "paragraph_index" in anchors:
        anchor_label = f"para.{anchors['paragraph_index']}"
    else:
        anchor_label = "source"
    return {
        "document_id": document.document.document_id,
        "fragment_id": fragment.fragment_id,
        "file_name": document.document.file_name,
        "anchor_label": anchor_label,
        "anchors": anchors,
        "quote": fragment.text[:200],
    }


def _build_summary(title: str, refs: list[dict], *, use_llm: bool) -> str:
    snippets = [ref["quote"] for ref in refs[:6]]
    if not snippets:
        LOGGER.info("页面《%s》没有匹配到足够证据，使用空摘要回退", title)
        return f"页面《{title}》尚未匹配到足够来源，等待后续文档补充。"
    if use_llm:
        try:
            LOGGER.info("页面《%s》开始调用 LLM 生成摘要，证据片段数=%s", title, len(snippets))
            return ask_llm(build_summary_prompt(title, snippets), temperature=0.2, max_tokens=400)
        except Exception:
            LOGGER.exception("页面《%s》调用 LLM 失败，回退到抽取式摘要", title)
    LOGGER.info("页面《%s》未启用 LLM，使用抽取式摘要", title)
    return "；".join(snippets[:3])[:300]


def _render_candidate_content(page: WikiPage) -> str:
    lines = [f"# {page.title}", "", "## 摘要", page.summary or "暂无摘要"]
    for section in page.sections:
        lines.extend(["", f"## {section.heading}", section.content])
    return "\n".join(lines).strip()


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap Wiki pages from parsed documents.")
    parser.add_argument("--use-llm", action="store_true", help="Use configured LLM to generate page summaries.")
    args = parser.parse_args()

    pages = bootstrap_pages(use_llm=args.use_llm)
    for page in pages:
        print(f"PAGE {page.page_id} -> refs={len(page.source_refs)}")


if __name__ == "__main__":
    main()

