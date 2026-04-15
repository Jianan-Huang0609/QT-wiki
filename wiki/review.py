from __future__ import annotations

import json
import logging
import re

from Tool.llm.client import ask_llm
from wiki.models.page import PageChangeCandidate, ReviewDecision

LOGGER = logging.getLogger(__name__)

NORMATIVE_MARKERS = ("应当", "必须", "不得", "禁止", "负责", "记录", "放行")


def evaluate_change_candidate(
    candidate: PageChangeCandidate,
    *,
    use_llm: bool = False,
    auto_approve_small_changes: bool = True,
    llm_config_path: str = "config/azure_gpt4o_config.json",
) -> ReviewDecision:
    heuristic = _heuristic_review(candidate, auto_approve_small_changes=auto_approve_small_changes)
    if not use_llm:
        return heuristic

    try:
        llm_decision = _llm_review(candidate, llm_config_path=llm_config_path)
    except Exception:
        LOGGER.exception("LLM 审核失败，回退到规则审核：page_id=%s", candidate.page.page_id)
        return heuristic

    requires_human = (
        heuristic.review_mode == "human_required"
        or llm_decision.review_mode == "human_required"
    )
    risk_rank = max(_risk_rank(heuristic.risk_level), _risk_rank(llm_decision.risk_level))
    scope_rank = max(_scope_rank(heuristic.change_scope), _scope_rank(llm_decision.change_scope))
    reasoning = "；".join(part for part in [heuristic.reasoning, llm_decision.reasoning] if part)
    return ReviewDecision(
        risk_level=_risk_from_rank(risk_rank),
        change_scope=_scope_from_rank(scope_rank),
        review_mode="human_required" if requires_human else "auto",
        auto_publish=(not requires_human) and auto_approve_small_changes,
        reasoning=reasoning or "规则与 LLM 都认为该变更可以自动推进。",
        tool_trace=[*heuristic.tool_trace, *llm_decision.tool_trace],
    )


def _heuristic_review(candidate: PageChangeCandidate, *, auto_approve_small_changes: bool) -> ReviewDecision:
    text = candidate.candidate_content
    ref_count = len(candidate.source_refs)
    normative_hits = sum(1 for marker in NORMATIVE_MARKERS if marker in text)
    scope = "small" if ref_count <= 2 and len(text) <= 260 else "medium"
    risk = "low"
    review_mode = "auto"
    reasoning = "改动范围较小，可自动推进。"

    if candidate.action == "bootstrap_page":
        scope = "large"
        risk = "medium" if ref_count else "high"
        review_mode = "human_required"
        reasoning = "首次建库属于结构性变更，默认进入人工审核。"
    elif candidate.document_type == "policy" or normative_hits >= 2:
        scope = "medium" if scope == "small" else scope
        risk = "high"
        review_mode = "human_required"
        reasoning = "候选内容包含规范性要求或来自制度类文档，必须人工审核后发布。"
    elif ref_count >= 4 or len(text) > 500:
        scope = "medium"
        risk = "medium"
        review_mode = "human_required"
        reasoning = "本次更新涉及证据较多或文本较长，按中等变更进入人工审核。"

    auto_publish = review_mode == "auto" and auto_approve_small_changes
    return ReviewDecision(
        risk_level=risk,
        change_scope=scope,
        review_mode=review_mode,
        auto_publish=auto_publish,
        reasoning=reasoning,
        tool_trace=["wiki.review._heuristic_review"],
    )


def _llm_review(candidate: PageChangeCandidate, *, llm_config_path: str) -> ReviewDecision:
    prompt = _build_review_prompt(candidate)
    raw = ask_llm(
        prompt,
        config_path=llm_config_path,
        max_tokens=400,
        temperature=0.1,
    )
    data = _parse_json_object(raw)
    review_mode = "human_required" if data.get("requires_human_review", True) else "auto"
    return ReviewDecision(
        risk_level=_normalize_risk(str(data.get("risk_level", "medium"))),
        change_scope=_normalize_scope(str(data.get("change_scope", "medium"))),
        review_mode=review_mode,
        auto_publish=review_mode == "auto",
        reasoning=str(data.get("reason", "")).strip(),
        tool_trace=["wiki.review._llm_review"],
    )


def _build_review_prompt(candidate: PageChangeCandidate) -> str:
    excerpt = candidate.candidate_content[:1200]
    return (
        "你是企业 Wiki 变更审核代理。请判断以下候选变更是否需要人工审核。\n"
        "只输出 JSON，不要输出其他说明。字段格式："
        '{"risk_level":"low|medium|high","change_scope":"small|medium|large","requires_human_review":true,"reason":"..."}'
        "\n\n"
        f"action: {candidate.action}\n"
        f"page_id: {candidate.page.page_id}\n"
        f"page_title: {candidate.page.title}\n"
        f"page_type: {candidate.page.page_type}\n"
        f"document_type: {candidate.document_type or 'unknown'}\n"
        f"source_file_name: {candidate.source_file_name or 'unknown'}\n"
        f"evidence_count: {len(candidate.source_refs)}\n"
        "candidate_content:\n"
        f"{excerpt}"
    )


def _parse_json_object(raw: str) -> dict:
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match is None:
        raise ValueError("No JSON object found in LLM response")
    return json.loads(match.group(0))


def _normalize_risk(value: str) -> str:
    if value in {"low", "medium", "high"}:
        return value
    return "medium"


def _normalize_scope(value: str) -> str:
    if value in {"small", "medium", "large"}:
        return value
    return "medium"


def _risk_rank(value: str) -> int:
    return {"low": 0, "medium": 1, "high": 2}.get(value, 1)


def _risk_from_rank(rank: int) -> str:
    return {0: "low", 1: "medium", 2: "high"}.get(rank, "medium")


def _scope_rank(value: str) -> int:
    return {"small": 0, "medium": 1, "large": 2}.get(value, 1)


def _scope_from_rank(rank: int) -> str:
    return {0: "small", 1: "medium", 2: "large"}.get(rank, "medium")
