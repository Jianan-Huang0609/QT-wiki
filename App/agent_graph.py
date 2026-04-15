from __future__ import annotations

import logging
from copy import deepcopy
from datetime import datetime
from typing import TypedDict

from wiki.builders.bootstrap import build_page_candidates
from wiki.models.page import PageChangeCandidate, ReviewDecision, UpdateProposal
from wiki.review import evaluate_change_candidate
from wiki.store.files import save_page, save_proposal
from wiki.updaters.incremental import build_incremental_candidates

LOGGER = logging.getLogger(__name__)

try:
    from langgraph.graph import END, StateGraph

    LANGGRAPH_AVAILABLE = True
except Exception:  # pragma: no cover
    END = "__end__"
    StateGraph = None
    LANGGRAPH_AVAILABLE = False


class WorkflowState(TypedDict, total=False):
    bootstrap: bool
    parsed_manifests: list[dict]
    docs_to_incrementally_maintain: list[dict]
    use_llm: bool
    llm_config_path: str
    auto_approve_small_changes: bool
    workflow_engine: str
    candidates: list[PageChangeCandidate]
    decisions: list[ReviewDecision]
    proposals_created: int
    pages_created: int
    pages_published: int
    pending_review_count: int
    per_document_proposals: dict[str, int]
    bootstrap_performed: bool


def run_agent_workflow(
    *,
    bootstrap: bool,
    parsed_manifests: list[dict],
    docs_to_incrementally_maintain: list[dict],
    use_llm: bool,
    auto_approve_small_changes: bool = True,
    workflow_engine: str = "auto",
    llm_config_path: str = "config/azure_gpt4o_config.json",
) -> dict:
    initial_state: WorkflowState = {
        "bootstrap": bootstrap,
        "parsed_manifests": parsed_manifests,
        "docs_to_incrementally_maintain": docs_to_incrementally_maintain,
        "use_llm": use_llm,
        "llm_config_path": llm_config_path,
        "auto_approve_small_changes": auto_approve_small_changes,
        "workflow_engine": workflow_engine,
        "proposals_created": 0,
        "pages_created": 0,
        "pages_published": 0,
        "pending_review_count": 0,
        "per_document_proposals": {},
        "bootstrap_performed": False,
    }

    engine = _resolve_engine(workflow_engine)
    LOGGER.info("Agent 工作流开始：engine=%s，bootstrap=%s", engine, bootstrap)
    if engine == "langgraph":
        return _run_langgraph(initial_state)
    return _run_builtin(initial_state)


def _resolve_engine(workflow_engine: str) -> str:
    if workflow_engine == "langgraph" and not LANGGRAPH_AVAILABLE:
        LOGGER.warning("指定使用 LangGraph，但当前环境不可用，回退到内置工作流")
        return "builtin"
    if workflow_engine == "auto":
        return "langgraph" if LANGGRAPH_AVAILABLE else "builtin"
    return workflow_engine


def _run_builtin(state: WorkflowState) -> WorkflowState:
    state = _collect_candidates_node(state)
    state = _review_candidates_node(state)
    state = _apply_candidates_node(state)
    return state


def _run_langgraph(initial_state: WorkflowState) -> WorkflowState:
    workflow = StateGraph(WorkflowState)
    workflow.add_node("collect_candidates", _collect_candidates_node)
    workflow.add_node("review_candidates", _review_candidates_node)
    workflow.add_node("apply_candidates", _apply_candidates_node)
    workflow.set_entry_point("collect_candidates")
    workflow.add_edge("collect_candidates", "review_candidates")
    workflow.add_edge("review_candidates", "apply_candidates")
    workflow.add_edge("apply_candidates", END)
    app = workflow.compile()
    return app.invoke(initial_state)


def _collect_candidates_node(state: WorkflowState) -> WorkflowState:
    candidates: list[PageChangeCandidate] = []
    if state.get("bootstrap"):
        candidates = build_page_candidates(use_llm=state.get("use_llm", False))
        state["bootstrap_performed"] = bool(candidates)
        state["pages_created"] = len(candidates)
    else:
        for manifest in state.get("docs_to_incrementally_maintain", []):
            doc_candidates = build_incremental_candidates(
                manifest["document_id"],
                use_llm=state.get("use_llm", False),
            )
            for candidate in doc_candidates:
                candidate.tool_trace.append(f"manifest:{manifest['document_id']}")
            candidates.extend(doc_candidates)

    state["candidates"] = candidates
    LOGGER.info("候选变更收集完成：候选数=%s", len(candidates))
    return state


def _review_candidates_node(state: WorkflowState) -> WorkflowState:
    decisions: list[ReviewDecision] = []
    for candidate in state.get("candidates", []):
        decision = evaluate_change_candidate(
            candidate,
            use_llm=state.get("use_llm", False),
            auto_approve_small_changes=state.get("auto_approve_small_changes", True),
            llm_config_path=state.get("llm_config_path", "config/azure_gpt4o_config.json"),
        )
        decisions.append(decision)

    state["decisions"] = decisions
    LOGGER.info("候选审核完成：决策数=%s", len(decisions))
    return state


def _apply_candidates_node(state: WorkflowState) -> WorkflowState:
    proposals_created = 0
    pages_published = 0
    pending_review_count = 0
    per_document_proposals = dict(state.get("per_document_proposals", {}))

    for candidate, decision in zip(state.get("candidates", []), state.get("decisions", [])):
        proposal = _proposal_from_candidate(candidate, decision)
        save_proposal(proposal)
        proposals_created += 1
        for document_id in candidate.source_document_ids:
            per_document_proposals[document_id] = per_document_proposals.get(document_id, 0) + 1

        if candidate.action == "bootstrap_page":
            page = deepcopy(candidate.page)
            page.review_status = "published" if decision.auto_publish else "pending_review"
            save_page(page)
            if decision.auto_publish:
                pages_published += 1
            else:
                pending_review_count += 1
            continue

        if decision.auto_publish:
            page = deepcopy(candidate.page)
            page.review_status = "published"
            save_page(page)
            pages_published += 1
        else:
            pending_review_count += 1

    state["proposals_created"] = proposals_created
    state["pages_published"] = pages_published
    state["pending_review_count"] = pending_review_count
    state["per_document_proposals"] = per_document_proposals
    LOGGER.info(
        "候选落盘完成：proposal=%s，published=%s，pending_review=%s",
        proposals_created,
        pages_published,
        pending_review_count,
    )
    return state


def _proposal_from_candidate(candidate: PageChangeCandidate, decision: ReviewDecision) -> UpdateProposal:
    proposal_id = f"proposal-{candidate.action}-{datetime.now().strftime('%Y%m%d%H%M%S')}-{candidate.page.page_id}"
    if candidate.action == "bootstrap_page":
        reason = f"首次建库为页面《{candidate.page.title}》生成候选内容"
    else:
        source_name = candidate.source_file_name or "新文档"
        reason = f"文档 {source_name} 为页面《{candidate.page.title}》提供候选更新"

    if decision.reasoning:
        reason = f"{reason}。审核结论：{decision.reasoning}"

    return UpdateProposal(
        proposal_id=proposal_id,
        target_page_id=candidate.page.page_id,
        action=candidate.action,
        reason=reason,
        candidate_content=candidate.candidate_content,
        evidence_fragment_ids=list(candidate.evidence_fragment_ids),
        source_refs=list(candidate.source_refs),
        risk_level=decision.risk_level,
        status="published" if decision.auto_publish else "pending_review",
        change_scope=decision.change_scope,
        review_mode=decision.review_mode,
        review_notes=decision.reasoning,
        source_document_ids=list(candidate.source_document_ids),
        tool_trace=[*candidate.tool_trace, *decision.tool_trace],
    )
