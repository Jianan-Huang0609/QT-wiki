from __future__ import annotations

import argparse
import json
import logging
import re
from collections import Counter
from copy import deepcopy
from datetime import datetime

from Tool.contracts.canonical import CanonicalDocument, Fragment, load_canonical_document
from Tool.llm.client import ask_llm
from Tool.llm.prompts import build_page_discovery_prompt, build_summary_prompt
from Tool.pipelines.common import PARSED_DIR
from wiki.models.page import PageChangeCandidate, PageSection, WikiPage
from wiki.store.files import save_page

LOGGER = logging.getLogger(__name__)
SUCCESS_PARSE_STATUSES = {"parsed", "partially_parsed"}

# 保留静态蓝图作为兜底，但不再作为首次建库的主路径。
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
DISCOVERY_JSON_RE = re.compile(r"\{.*\}|\[.*\]", re.DOTALL)
SECTION_PREFIX_RE = re.compile(r"^(第[一二三四五六七八九十百零〇\d]+[章节篇部分卷]|附录\s*[A-Z一二三四五六七八九十\d]+)\s*")
LIST_PREFIX_RE = re.compile(r"^[（(]?[0-9一二三四五六七八九十]+[)）.．、]\s*")
NOISE_MARKERS = ("目录", "本章要点", "理解要点", "分享人", "教师简介", "本资料仅限于内部研讨使用")
SUBSTANTIVE_MARKERS = ("应当", "应", "不得", "可以", "负责", "建立", "保存", "记录", "校准", "检定", "放行")
TOPIC_NOISE_MARKERS = {
    "目录",
    "前言",
    "总则",
    "附则",
    "概述",
    "结语",
    "封面",
    "本页要点",
    "课程目标",
    "培训讲义",
    "培训材料",
    "学习目标",
    "变化率",
    "章节条款数对比",
}
GENERIC_DOCUMENT_MARKERS = ("培训", "讲义", "课件", "分享", "汇报", "解读", "理解和实施", "最新")
VALID_PAGE_TYPES = {"policy", "concept", "process", "role"}
DISCOVERY_LIMIT = 12


def build_page_candidates(*, use_llm: bool = False) -> list[PageChangeCandidate]:
    parsed_docs = _load_parsed_documents()
    LOGGER.info("开始首次建库：已解析文档数=%s，启用LLM=%s", len(parsed_docs), use_llm)
    blueprints = discover_page_blueprints(parsed_docs, use_llm=use_llm)
    LOGGER.info("建库主题发现完成：候选主题数=%s", len(blueprints))
    candidates = _build_candidates_from_blueprints(parsed_docs, blueprints, use_llm=use_llm)
    if candidates:
        return candidates
    if blueprints != PAGE_BLUEPRINTS:
        LOGGER.warning("动态主题发现未能生成可用页面，回退到静态蓝图")
        return _build_candidates_from_blueprints(parsed_docs, _clone_blueprints(PAGE_BLUEPRINTS), use_llm=use_llm)
    return []


def discover_page_blueprints(parsed_docs: list[CanonicalDocument], *, use_llm: bool = False) -> list[dict]:
    heuristic_blueprints = _heuristic_discover_page_blueprints(parsed_docs)
    seed_blueprints = _seed_blueprints()
    if use_llm and parsed_docs:
        try:
            llm_blueprints = _llm_discover_page_blueprints(parsed_docs)
            merged = _merge_blueprints(llm_blueprints, heuristic_blueprints)
            merged = _merge_blueprints(merged, seed_blueprints)
            if merged:
                LOGGER.info("LLM 主题发现成功：LLM=%s，启发式补充后=%s", len(llm_blueprints), len(merged))
                return merged
        except Exception:
            LOGGER.exception("LLM 主题发现失败，回退到启发式主题发现")
    if heuristic_blueprints:
        return _merge_blueprints(heuristic_blueprints, seed_blueprints)
    LOGGER.warning("未能从文档中发现有效主题，回退到静态蓝图")
    return seed_blueprints


def bootstrap_pages(*, use_llm: bool = False) -> list[WikiPage]:
    pages: list[WikiPage] = []
    for candidate in build_page_candidates(use_llm=use_llm):
        page = candidate.page
        save_page(page)
        pages.append(page)
        LOGGER.info("页面已生成：page_id=%s，证据数=%s", page.page_id, len(page.source_refs))
    return pages


def _build_candidates_from_blueprints(
    parsed_docs: list[CanonicalDocument],
    blueprints: list[dict],
    *,
    use_llm: bool,
) -> list[PageChangeCandidate]:
    candidates: list[PageChangeCandidate] = []
    for blueprint in blueprints:
        refs = _collect_refs(parsed_docs, blueprint)
        if not refs:
            LOGGER.info("主题《%s》未匹配到有效证据，跳过页面候选", blueprint["title"])
            continue
        summary = _build_summary(blueprint["title"], refs, use_llm=use_llm)
        evidence_lines = [
            f"- {ref['quote']} ({ref['file_name']} {ref['anchor_label']})"
            for ref in refs[:8]
        ]
        page = WikiPage(
            page_id=blueprint["page_id"],
            title=blueprint["title"],
            page_type=blueprint["page_type"],
            summary=summary,
            sections=[PageSection(heading="关键依据", content="\n".join(evidence_lines), source_refs=refs[:8])],
            aliases=list(blueprint.get("aliases", [])),
            source_refs=refs,
            linked_pages=list(blueprint.get("linked_pages", [])),
            review_status="approved",
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
                tool_trace=[*blueprint.get("_tool_trace", []), "wiki.builders.bootstrap.build_page_candidates"],
            )
        )
    return candidates


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


def _heuristic_discover_page_blueprints(parsed_docs: list[CanonicalDocument]) -> list[dict]:
    buckets: list[dict] = []
    for document in parsed_docs:
        doc_title = _clean_topic_title(document.document.title)
        if _should_use_document_title(document, doc_title):
            _register_topic_candidate(
                buckets,
                title=doc_title,
                score=7 if document.document.doc_type == "policy" else 4,
                page_type=_infer_page_type(doc_title, [doc_title]),
                aliases=[],
                keywords=[doc_title],
                section_keywords=[],
                related_titles=[],
                source_document_id=document.document.document_id,
            )

        for section in document.sections:
            section_title = _clean_topic_title(section.title)
            if not _is_valid_topic_title(section_title):
                continue
            _register_topic_candidate(
                buckets,
                title=section_title,
                score=8,
                page_type=_infer_page_type(section_title, [section_title]),
                aliases=[],
                keywords=[section_title],
                section_keywords=[section.title],
                related_titles=[],
                source_document_id=document.document.document_id,
            )

        for term in document.terms[:30]:
            topic = _clean_topic_title(term)
            if not _is_valid_topic_title(topic):
                continue
            _register_topic_candidate(
                buckets,
                title=topic,
                score=4,
                page_type=_infer_page_type(topic, [topic]),
                aliases=[],
                keywords=[topic],
                section_keywords=[],
                related_titles=[],
                source_document_id=document.document.document_id,
            )

    return _finalize_blueprints(buckets)


def _llm_discover_page_blueprints(parsed_docs: list[CanonicalDocument]) -> list[dict]:
    contexts = _build_discovery_contexts(parsed_docs)
    LOGGER.info("开始调用 LLM 做建库主题发现：文档上下文数=%s", len(contexts))
    raw = ask_llm(
        build_page_discovery_prompt(contexts),
        temperature=0.2,
        max_tokens=1800,
    )
    blueprints = _parse_discovery_response(raw)
    if not blueprints:
        raise ValueError("LLM 未返回可用的页面主题")
    return _finalize_blueprints(blueprints)


def _build_discovery_contexts(parsed_docs: list[CanonicalDocument]) -> list[str]:
    contexts: list[str] = []
    for document in parsed_docs[:8]:
        section_titles = [
            _clean_topic_title(section.title) or normalize_fragment_text(section.title)
            for section in document.sections[:10]
            if normalize_fragment_text(section.title)
        ]
        fragment_lines = [
            normalize_fragment_text(fragment.text)[:120]
            for fragment in document.fragments
            if not _is_noise_fragment(fragment.text)
        ][:8]
        terms = [_clean_topic_title(term) for term in document.terms[:12]]
        terms = [term for term in terms if term]
        contexts.append(
            "\n".join(
                [
                    f"标题: {document.document.title}",
                    f"文档类型: {document.document.doc_type}",
                    f"章节: {'；'.join(section_titles[:8]) or '无'}",
                    f"术语: {'；'.join(terms[:10]) or '无'}",
                    "证据片段:",
                    *[f"- {line}" for line in fragment_lines],
                ]
            ).strip()
        )
    return contexts


def _parse_discovery_response(raw: str) -> list[dict]:
    match = DISCOVERY_JSON_RE.search(raw)
    if match is None:
        raise ValueError("LLM 返回中未找到 JSON")
    payload = json.loads(match.group(0))
    if isinstance(payload, dict):
        items = payload.get("pages", [])
    elif isinstance(payload, list):
        items = payload
    else:
        items = []

    blueprints: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        blueprint = _sanitize_blueprint(
            {
                "page_id": item.get("page_id") or item.get("title"),
                "title": item.get("title") or item.get("page_id"),
                "page_type": item.get("page_type"),
                "aliases": item.get("aliases", []),
                "keywords": item.get("keywords", []),
                "section_keywords": item.get("section_keywords", []),
                "related_titles": item.get("related_titles", []),
                "_tool_trace": ["wiki.builders.bootstrap._llm_discover_page_blueprints"],
            }
        )
        if blueprint is not None:
            blueprints.append(blueprint)
    return blueprints


def _merge_blueprints(primary: list[dict], secondary: list[dict]) -> list[dict]:
    merged: list[dict] = []
    for blueprint in primary + secondary:
        _merge_or_append_blueprint(merged, blueprint)
    return _finalize_blueprints(merged)


def _register_topic_candidate(
    buckets: list[dict],
    *,
    title: str,
    score: int,
    page_type: str,
    aliases: list[str],
    keywords: list[str],
    section_keywords: list[str],
    related_titles: list[str],
    source_document_id: str,
) -> None:
    blueprint = {
        "page_id": title,
        "title": title,
        "page_type": page_type,
        "aliases": aliases,
        "keywords": keywords,
        "section_keywords": section_keywords,
        "related_titles": related_titles,
        "_source_document_ids": [source_document_id],
        "_score": score,
        "_tool_trace": ["wiki.builders.bootstrap._heuristic_discover_page_blueprints"],
    }
    _merge_or_append_blueprint(buckets, blueprint)


def _merge_or_append_blueprint(blueprints: list[dict], incoming: dict | None) -> None:
    sanitized = _sanitize_blueprint(incoming)
    if sanitized is None:
        return
    for index, existing in enumerate(blueprints):
        if _blueprints_match(existing, sanitized):
            blueprints[index] = _combine_blueprints(existing, sanitized)
            return
    blueprints.append(sanitized)


def _combine_blueprints(left: dict, right: dict) -> dict:
    title = _select_primary_title([left.get("title", ""), right.get("title", "")])
    page_type = _normalize_page_type(
        right.get("page_type") if right.get("page_type") != "concept" else left.get("page_type")
    )
    combined = {
        "page_id": title,
        "title": title,
        "page_type": page_type,
        "aliases": _dedupe_texts([*left.get("aliases", []), left.get("title", ""), *right.get("aliases", []), right.get("title", "")], exclude={title}),
        "keywords": _dedupe_texts([*left.get("keywords", []), *right.get("keywords", []), title]),
        "section_keywords": _dedupe_texts([*left.get("section_keywords", []), *right.get("section_keywords", [])]),
        "related_titles": _dedupe_texts([*left.get("related_titles", []), *right.get("related_titles", [])], exclude={title}),
        "_source_document_ids": sorted({*left.get("_source_document_ids", []), *right.get("_source_document_ids", [])}),
        "_score": int(left.get("_score", 0)) + int(right.get("_score", 0)),
        "_tool_trace": _dedupe_texts([*left.get("_tool_trace", []), *right.get("_tool_trace", [])]),
    }
    return combined


def _sanitize_blueprint(blueprint: dict | None) -> dict | None:
    if not blueprint:
        return None
    title = _clean_topic_title(str(blueprint.get("title") or blueprint.get("page_id") or ""))
    if not _is_valid_topic_title(title):
        return None
    aliases = _dedupe_texts(
        [_clean_topic_title(item) for item in blueprint.get("aliases", []) if isinstance(item, str)],
        exclude={title},
    )
    keywords = _dedupe_texts(
        [_clean_topic_title(item) for item in blueprint.get("keywords", []) if isinstance(item, str)] + [title],
    )
    section_keywords = _dedupe_texts(
        [normalize_fragment_text(item) for item in blueprint.get("section_keywords", []) if isinstance(item, str)],
    )
    related_titles = _dedupe_texts(
        [_clean_topic_title(item) for item in blueprint.get("related_titles", []) if isinstance(item, str)],
        exclude={title},
    )
    page_type = _normalize_page_type(blueprint.get("page_type") or _infer_page_type(title, keywords))
    source_document_ids = sorted({item for item in blueprint.get("_source_document_ids", []) if item})
    return {
        "page_id": title,
        "title": title,
        "page_type": page_type,
        "aliases": aliases[:6],
        "keywords": keywords[:10],
        "section_keywords": section_keywords[:8],
        "related_titles": related_titles[:4],
        "_source_document_ids": source_document_ids,
        "_score": int(blueprint.get("_score", 0)),
        "_tool_trace": _dedupe_texts(list(blueprint.get("_tool_trace", []))),
    }


def _finalize_blueprints(blueprints: list[dict]) -> list[dict]:
    sanitized: list[dict] = []
    for blueprint in blueprints:
        _merge_or_append_blueprint(sanitized, blueprint)
    sanitized.sort(key=lambda item: (-int(item.get("_score", 0)), len(item["title"]), item["title"]))

    protected_page_ids = {item["page_id"] for item in _seed_blueprints()}
    protected = [item for item in sanitized if item["page_id"] in protected_page_ids]
    remaining = [item for item in sanitized if item["page_id"] not in protected_page_ids]
    keep_remaining = max(0, DISCOVERY_LIMIT - len(protected))
    sanitized = [*protected, *remaining[:keep_remaining]]
    if not sanitized:
        return []

    titles = {item["title"] for item in sanitized}
    for blueprint in sanitized:
        explicit_related = [title for title in blueprint.get("related_titles", []) if title in titles and title != blueprint["title"]]
        related_scores: list[tuple[int, str]] = []
        for other in sanitized:
            if other["title"] == blueprint["title"]:
                continue
            score = 0
            if other["title"] in explicit_related:
                score += 10
            shared_docs = len(set(blueprint.get("_source_document_ids", [])) & set(other.get("_source_document_ids", [])))
            shared_keywords = len(
                {_compact_text(item) for item in blueprint.get("keywords", [])}
                & {_compact_text(item) for item in other.get("keywords", [])}
            )
            if shared_docs:
                score += shared_docs
            if shared_keywords:
                score += shared_keywords * 2
            if blueprint["page_type"] == "concept" and other["page_type"] in {"process", "role"}:
                score += 1
            if score > 0:
                related_scores.append((score, other["title"]))
        related_scores.sort(key=lambda item: (-item[0], len(item[1]), item[1]))
        blueprint["linked_pages"] = [title for _, title in related_scores[:3]]
    return sanitized


def _blueprints_match(left: dict, right: dict) -> bool:
    left_titles = {_compact_text(left.get("title", "")), *[_compact_text(item) for item in left.get("aliases", [])]}
    right_titles = {_compact_text(right.get("title", "")), *[_compact_text(item) for item in right.get("aliases", [])]}
    left_titles.discard("")
    right_titles.discard("")
    if left_titles & right_titles:
        return True
    for left_title in left_titles:
        for right_title in right_titles:
            if min(len(left_title), len(right_title)) < 4:
                continue
            if left_title in right_title or right_title in left_title:
                return True
    return False


def _select_primary_title(candidates: list[str]) -> str:
    titles = [title for title in candidates if _is_valid_topic_title(title)]
    if not titles:
        return ""
    counter = Counter(titles)
    return sorted(counter, key=lambda item: (-counter[item], len(item), item))[0]


def _should_use_document_title(document: CanonicalDocument, title: str) -> bool:
    if not _is_valid_topic_title(title):
        return False
    if document.document.doc_type == "policy":
        return True
    return not any(marker in title for marker in GENERIC_DOCUMENT_MARKERS)


def _infer_page_type(title: str, keywords: list[str]) -> str:
    text = "".join([title, *keywords])
    if any(marker in text for marker in ("规范", "法规", "制度", "程序文件")):
        return "policy"
    if any(marker in text for marker in ("职责", "岗位", "人员", "机构", "部门")):
        return "role"
    if any(marker in text for marker in ("管理", "控制", "放行", "采购", "生产", "检验", "验证", "校准")):
        return "process"
    return "concept"


def _normalize_page_type(value: str | None) -> str:
    if value in VALID_PAGE_TYPES:
        return value
    return "concept"


def _clean_topic_title(title: str) -> str:
    normalized = normalize_fragment_text(title)
    normalized = SECTION_PREFIX_RE.sub("", normalized)
    normalized = LIST_PREFIX_RE.sub("", normalized)
    normalized = normalized.strip("：:;；-_- ")
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def _is_valid_topic_title(title: str) -> bool:
    if not title or len(title) < 2 or len(title) > 28:
        return False
    if title in TOPIC_NOISE_MARKERS:
        return False
    if any(marker in title for marker in NOISE_MARKERS):
        return False
    if PAGE_HEADER_RE.match(title) or SECTION_HEADING_RE.match(title) or ARTICLE_RE.match(title):
        return False
    if re.search(r"[。！？；]", title):
        return False
    digits = sum(char.isdigit() for char in title)
    if digits and digits >= max(2, len(title) // 2):
        return False
    return True


def _clone_blueprints(blueprints: list[dict]) -> list[dict]:
    return [deepcopy(blueprint) for blueprint in blueprints]


def _seed_blueprints() -> list[dict]:
    seeded: list[dict] = []
    for blueprint in _clone_blueprints(PAGE_BLUEPRINTS):
        seeded.append(
            {
                **blueprint,
                "_score": max(int(blueprint.get("_score", 0)), 6),
                "_tool_trace": _dedupe_texts(
                    [*list(blueprint.get("_tool_trace", [])), "wiki.builders.bootstrap.PAGE_BLUEPRINTS"]
                ),
            }
        )
    return seeded


def _dedupe_texts(values: list[str], exclude: set[str] | None = None) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    excluded = exclude or set()
    for value in values:
        normalized = value.strip()
        compact = _compact_text(normalized)
        if not normalized or normalized in excluded or compact in seen:
            continue
        seen.add(compact)
        result.append(normalized)
    return result


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
    refs: list[tuple[int, dict]] = []
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
    parser.add_argument("--use-llm", action="store_true", help="Use configured LLM to discover topics and generate summaries.")
    args = parser.parse_args()

    pages = bootstrap_pages(use_llm=args.use_llm)
    for page in pages:
        print(f"PAGE {page.page_id} -> refs={len(page.source_refs)}")


if __name__ == "__main__":
    main()
