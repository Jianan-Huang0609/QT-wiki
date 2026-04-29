from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from App.agents.ingest_agent import IngestAgent
from App.agents.lint_agent import LintAgent
from App.agents.query_agent import QueryAgent
from App.agents.structured_knowledge import (
    build_mapping_matrix,
    build_slides_outline,
    build_structured_context,
)
from App.schemas import (
    AgentUploadResponse,
    ChatQueryRequest,
    ChatQueryResponse,
    DashboardResponse,
    HealthResponse,
    ReviewPackageDecisionRequest,
    ReviewPackageRelationDecisionRequest,
)
from Tool.document_processor import process_document
from Tool.pipelines.common import PARSED_DIR
from wiki.builders.bootstrap import PAGE_BLUEPRINTS, bootstrap_pages
from wiki.indexing import build_index, load_page_index, rank_page_index
from wiki.models.page import WikiPage
from wiki.store import (
    PAGE_DIR,
    list_review_packages,
    load_all_pages,
    load_page,
    render_page_markdown,
    update_review_package_decision,
    update_review_package_relation_decision,
)

try:
    from fastapi import FastAPI, File, Form, HTTPException, UploadFile
    from fastapi.middleware.cors import CORSMiddleware
except ModuleNotFoundError as exc:  # pragma: no cover - runtime guard
    raise RuntimeError(
        "FastAPI is required to run App.api. Install fastapi, uvicorn, and python-multipart first."
    ) from exc


REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = REPO_ROOT / "Raw"
RUN_DIR = REPO_ROOT / "App" / "output" / "runs"
INDEX_DIR = PAGE_DIR.parent / "index"
INDEX_PAGE_PATH = INDEX_DIR / "pages.jsonl"
INDEX_TERMS_PATH = INDEX_DIR / "terms.json"
INDEX_SOURCES_PATH = INDEX_DIR / "sources.jsonl"
_BOOTSTRAP_LOCK = threading.Lock()

app = FastAPI(title="QT Wiki API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get("/api/dashboard", response_model=DashboardResponse)
def dashboard() -> DashboardResponse:
    ingest_agent = IngestAgent()
    lint_agent = LintAgent()
    pages = _ensure_runtime_ready()
    candidates = ingest_agent.list_candidates()
    review_packages = list_review_packages()
    issues = _lint_items(lint_agent.run_health_check(use_llm=False))
    index_status = _build_index_status()
    return DashboardResponse(
        agents=_agent_summaries(candidates, review_packages, issues),
        index=index_status,
        pages=[_wiki_page_payload(page) for page in pages[:12]],
        issues=issues,
    )


@app.get("/api/ingest/candidates")
def ingest_candidates() -> dict[str, list[dict[str, Any]]]:
    agent = IngestAgent()
    items = [_candidate_payload(candidate) for candidate in agent.list_candidates()]
    items.sort(key=lambda item: (item["status"] != "pending", -item["confidence"], item["title"]))
    return {"items": items}


@app.get("/api/ingest/review-packages")
def ingest_review_packages() -> dict[str, list[dict[str, Any]]]:
    items = [_review_package_payload(item) for item in list_review_packages()]
    items.sort(key=lambda item: (item["status"] != "pending_review", item["title"]))
    return {"items": items}


@app.get("/api/ingest/runs")
def ingest_runs(limit: int = 12) -> dict[str, list[dict[str, Any]]]:
    return {"items": _load_recent_runs(limit=max(1, min(limit, 50)))}


@app.post("/api/ingest/review-packages/{package_id}/decision")
def decide_review_package(package_id: str, payload: ReviewPackageDecisionRequest) -> dict[str, Any]:
    existing = next((item for item in list_review_packages() if item.package_id == package_id), None)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Review package not found: {package_id}")

    reviewed_at = datetime.now().isoformat(timespec="seconds")

    review_package = update_review_package_decision(
        package_id,
        identity_decision=payload.identity_decision.value,
        confirmed_business_type=payload.confirmed_business_type or "",
        confirmed_effective_level=payload.confirmed_effective_level or "",
        confirmed_is_binding=payload.confirmed_is_binding,
        review_notes=payload.review_notes,
        reviewed_by=payload.reviewed_by,
        reviewed_at=reviewed_at,
    )
    return {"ok": True, "item": _review_package_payload(review_package)}


@app.post("/api/ingest/review-packages/{package_id}/relations/decision")
def decide_review_package_relations(package_id: str, payload: ReviewPackageRelationDecisionRequest) -> dict[str, Any]:
    existing = next((item for item in list_review_packages() if item.package_id == package_id), None)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Review package not found: {package_id}")
    if existing.identity_decision != "confirmed":
        raise HTTPException(status_code=409, detail="identity must be confirmed before relation review")
    if not getattr(existing, "extracted_relations", []):
        raise HTTPException(status_code=409, detail="no extracted relations available for review")

    relation_reviewed_at = datetime.now().isoformat(timespec="seconds")

    review_package = update_review_package_relation_decision(
        package_id,
        relation_decision=payload.relation_decision.value,
        relation_review_notes=payload.relation_review_notes,
        relation_reviewed_by=payload.relation_reviewed_by,
        relation_reviewed_at=relation_reviewed_at,
    )
    return {"ok": True, "item": _review_package_payload(review_package)}


@app.post("/api/ingest/candidates/{candidate_id}/approve")
def approve_candidate(candidate_id: str) -> dict[str, Any]:
    agent = IngestAgent()
    if not agent.can_approve_candidate(candidate_id):
        raise HTTPException(
            status_code=409,
            detail=f"Candidate cannot be published before identity and relation review gates are satisfied: {candidate_id}",
        )
    if not agent.approve_candidate(candidate_id):
        raise HTTPException(status_code=404, detail=f"Candidate not found or not pending: {candidate_id}")
    return {"ok": True, "candidate_id": candidate_id}


@app.post("/api/ingest/candidates/{candidate_id}/reject")
def reject_candidate(candidate_id: str) -> dict[str, Any]:
    agent = IngestAgent()
    if not agent.reject_candidate(candidate_id):
        raise HTTPException(status_code=404, detail=f"Candidate not found: {candidate_id}")
    return {"ok": True, "candidate_id": candidate_id}


@app.get("/api/wiki/pages")
def wiki_pages() -> dict[str, list[dict[str, Any]]]:
    pages = [_wiki_page_payload(page) for page in _ensure_runtime_ready()]
    pages.sort(key=lambda item: item["title"])
    return {"items": pages}


@app.post("/chat/reindex")
def reindex() -> dict[str, Any]:
    pages = _ensure_runtime_ready(force_bootstrap_if_empty=True)
    if pages:
        build_index(pages=pages, index_dir=INDEX_DIR)
    return _build_index_status()


@app.post("/chat/query", response_model=ChatQueryResponse)
def chat_query(payload: ChatQueryRequest) -> ChatQueryResponse:
    question = payload.question
    use_llm = payload.use_llm
    top_k_pages = payload.top_k_pages
    top_k_citations = payload.top_k_citations

    pages = _ensure_runtime_ready()
    entries = load_page_index()
    if not entries and pages:
        build_index(pages=pages, index_dir=INDEX_DIR)
        entries = load_page_index()

    ranked_entries = rank_page_index(question, entries, limit=top_k_pages)
    matched_pages_data = _pages_from_ranked_entries(ranked_entries)
    structured_context = build_structured_context(question, package_limit=min(top_k_pages, 4), relation_limit=8)
    citations = _collect_citations(matched_pages_data, limit=top_k_citations)
    citations = _append_structured_citations(citations, structured_context, limit=top_k_citations)
    matched_pages = [
        {
            "page_id": entry.get("page_id", ""),
            "title": entry.get("title", ""),
            "page_type": entry.get("page_type", ""),
            "summary": entry.get("summary", ""),
            "score": float(entry.get("relevance_score", 0.0)),
        }
        for entry in ranked_entries
    ]

    if use_llm:
        answer_result = QueryAgent().query(question, use_llm=True, interactive=False)
        answer_text = answer_result.answer_text
        confidence_value = answer_result.confidence
        used_llm = answer_result.used_llm
    else:
        answer_text = _deterministic_answer(question, matched_pages_data, citations, structured_context)
        confidence_value = 0.72 if structured_context.get("relations") else (
            min(1.0, sum(item["score"] for item in matched_pages[:3]) / 18) if matched_pages else 0.0
        )
        used_llm = False

    return ChatQueryResponse(
        answer=answer_text,
        confidence=_confidence_label(confidence_value),
        used_llm=used_llm,
        matched_pages=matched_pages,
        citations=citations,
        structured_matches=structured_context["packages"],
        trace=[
            f"wiki pages ready: {len(pages)}",
            "load pages.jsonl",
            f"rank top {len(matched_pages)} pages",
            f"load {len(matched_pages_data)} wiki pages",
            f"load {len(structured_context['packages'])} approved review packages",
            f"attach {len(structured_context['relations'])} structured relations",
            f"collect {len(citations)} citations",
        ],
    )


@app.get("/api/exports/mapping-matrix")
def export_mapping_matrix() -> dict[str, Any]:
    return build_mapping_matrix()


@app.get("/api/exports/slides-outline")
def export_slides_outline() -> dict[str, Any]:
    return build_slides_outline()


@app.post("/api/lint/scan")
def lint_scan() -> dict[str, list[dict[str, Any]]]:
    report = LintAgent().run_health_check(use_llm=False)
    return {"items": _lint_items(report)}


@app.post("/agent/upload", response_model=AgentUploadResponse)
async def agent_upload(
    file: UploadFile = File(...),
    use_llm: bool = Form(False),
) -> AgentUploadResponse:
    if not file.filename:
        raise HTTPException(status_code=400, detail="file is required")

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    safe_name = f"{timestamp}-{Path(file.filename).name}"
    target = RAW_DIR / safe_name
    target.write_bytes(await file.read())

    processed = process_document(target)
    candidates = IngestAgent().ingest(processed.document_id, use_llm=use_llm)
    run_id = datetime.now().strftime("%Y%m%d%H%M%S")
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    run_path = RUN_DIR / f"{run_id}.json"
    pending_count = len([item for item in candidates if item.status == "pending"])
    review_package_id = f"review-{processed.document_id}"
    candidate_ids = [item.candidate_id for item in candidates]
    run_path.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "file_name": file.filename,
                "document_id": processed.document_id,
                "review_package_id": review_package_id,
                "candidate_ids": candidate_ids,
                "documents_parsed": 1,
                "proposals_created": len(candidates),
                "pages_published": 0,
                "pending_review_count": pending_count,
                "workflow_engine": "IngestAgent",
                "use_llm": use_llm,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return AgentUploadResponse(
        run_id=run_id,
        document_id=processed.document_id,
        file_name=file.filename,
        review_package_id=review_package_id,
        candidate_ids=candidate_ids,
        documents_parsed=1,
        proposals_created=len(candidates),
        pending=pending_count,
        pending_review_count=pending_count,
        workflow_engine="IngestAgent",
    )


def _agent_summaries(candidates: list[Any], review_packages: list[Any], issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pending_candidates = len([item for item in candidates if item.status == "pending"])
    pending_packages = len([item for item in review_packages if item.status == "pending_review"])
    open_issues = len([item for item in issues if item["status"] != "resolved"])
    index_status = _build_index_status()
    return [
        {
            "key": "ingest",
            "name": "IngestAgent",
            "status": "ready" if pending_packages == 0 and pending_candidates == 0 else "running",
            "headline": f"{pending_packages} 个审批包待确认，{pending_candidates} 个候选页待发布",
            "queue": max(pending_packages, pending_candidates),
            "lastRun": index_status["lastBuilt"],
            "accent": "teal",
        },
        {
            "key": "query",
            "name": "QueryAgent",
            "status": "ready",
            "headline": f"索引已覆盖 {index_status['pages']} 个页面",
            "queue": 0,
            "lastRun": index_status["lastBuilt"],
            "accent": "blue",
        },
        {
            "key": "lint",
            "name": "LintAgent",
            "status": "blocked" if open_issues else "ready",
            "headline": f"{open_issues} 个健康问题待处理",
            "queue": open_issues,
            "lastRun": index_status["lastBuilt"],
            "accent": "amber",
        },
    ]


def _candidate_payload(candidate: Any) -> dict[str, Any]:
    return {
        "candidate_id": candidate.candidate_id,
        "document_ids": list(candidate.source_doc_ids),
        "page_type": candidate.page_type,
        "title": candidate.title,
        "status": candidate.status,
        "confidence": candidate.confidence,
        "summary": candidate.content.get("summary", ""),
        "keywords": candidate.content.get("keywords", []),
        "related_titles": candidate.content.get("related_titles", []),
        "source_refs": [{"document_id": item} for item in candidate.source_doc_ids],
    }


def _load_recent_runs(limit: int = 12) -> list[dict[str, Any]]:
    if not RUN_DIR.exists():
        return []

    runs: list[dict[str, Any]] = []
    for path in sorted(RUN_DIR.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            print(f"[App.api] skip invalid run file {path.name}: {exc}")
            continue

        document_id = str(data.get("document_id", "")).strip()
        run_id = str(data.get("run_id", path.stem)).strip() or path.stem
        if not document_id:
            continue
        runs.append(
            {
                "run_id": run_id,
                "document_id": document_id,
                "file_name": str(data.get("file_name", "")),
                "review_package_id": str(data.get("review_package_id", f"review-{document_id}")),
                "candidate_ids": list(data.get("candidate_ids", [])),
                "pending_review_count": int(data.get("pending_review_count", 0)),
                "proposals_created": int(data.get("proposals_created", 0)),
                "use_llm": bool(data.get("use_llm", False)),
                "created_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
            }
        )
        if len(runs) >= limit:
            break
    return runs


def _review_package_payload(review_package: Any) -> dict[str, Any]:
    identity = review_package.document_identity
    return {
        "package_id": review_package.package_id,
        "document_id": review_package.document_id,
        "status": review_package.status,
        "identity_decision": review_package.identity_decision,
        "title": identity.title or review_package.document_id,
        "business_type": identity.business_type,
        "effective_level": identity.effective_level,
        "version": identity.version,
        "scope": identity.scope,
        "is_binding": identity.is_binding,
        "confidence": identity.confidence,
        "notes": list(identity.notes),
        "confirmed_business_type": review_package.confirmed_business_type,
        "confirmed_effective_level": review_package.confirmed_effective_level,
        "confirmed_is_binding": review_package.confirmed_is_binding,
        "review_notes": review_package.review_notes,
        "reviewed_at": review_package.reviewed_at,
        "reviewed_by": review_package.reviewed_by,
        "relation_decision": getattr(review_package, "relation_decision", "pending"),
        "relation_review_notes": getattr(review_package, "relation_review_notes", ""),
        "relation_reviewed_at": getattr(review_package, "relation_reviewed_at", ""),
        "relation_reviewed_by": getattr(review_package, "relation_reviewed_by", ""),
        "source_refs": review_package.evidence_refs,
        "issues": [
            {
                "issue_id": issue.issue_id,
                "issue_type": issue.issue_type,
                "detail": issue.detail,
                "severity": issue.severity,
            }
            for issue in getattr(review_package, "issues", [])
        ],
        "human_questions": [
            {
                "question_id": question.question_id,
                "question": question.question,
                "rationale": question.rationale,
                "target": question.target,
            }
            for question in getattr(review_package, "human_questions", [])
        ],
        "extracted_objects": [
            {
                "object_id": item.object_id,
                "object_type": item.object_type,
                "name": item.name,
                "confidence": item.confidence,
                "review_risk": item.review_risk,
                "evidence_refs": list(item.evidence_refs),
            }
            for item in getattr(review_package, "extracted_objects", [])
        ],
        "extracted_relations": [
            {
                "relation_id": item.relation_id,
                "relation_type": item.relation_type,
                "from_object_id": item.from_object_id,
                "to_object_id": item.to_object_id,
                "claim_type": item.claim_type,
                "direction": item.direction,
                "confidence": item.confidence,
                "human_required": item.human_required,
                "evidence_refs": list(item.evidence_refs),
            }
            for item in getattr(review_package, "extracted_relations", [])
        ],
        "candidate_page_titles": list(getattr(review_package, "candidate_page_titles", [])),
        "tool_trace": list(getattr(review_package, "tool_trace", [])),
    }


def _wiki_page_payload(page: WikiPage) -> dict[str, Any]:
    return {
        "page_id": page.page_id,
        "title": page.title,
        "page_type": page.page_type,
        "review_status": page.review_status,
        "summary": page.summary,
        "aliases": page.aliases,
        "linked_pages": page.linked_pages,
        "updated_at": page.updated_at,
        "source_refs": page.source_refs,
        "markdown": render_page_markdown(page),
    }


def _build_index_status() -> dict[str, Any]:
    ready_pages = _ensure_runtime_ready()
    pages = _count_lines(INDEX_PAGE_PATH)
    terms = len(json.loads(INDEX_TERMS_PATH.read_text(encoding="utf-8"))) if INDEX_TERMS_PATH.exists() else 0
    sources = _count_lines(INDEX_SOURCES_PATH)
    state = "fresh" if INDEX_PAGE_PATH.exists() and pages > 0 else "missing"
    last_built = (
        datetime.fromtimestamp(INDEX_PAGE_PATH.stat().st_mtime).isoformat(timespec="seconds")
        if INDEX_PAGE_PATH.exists()
        else ""
    )
    return {
        "state": state,
        "pages": max(pages, len(ready_pages)),
        "terms": terms,
        "sources": sources,
        "lastBuilt": last_built,
    }


def _ensure_runtime_ready(*, force_bootstrap_if_empty: bool = False) -> list[WikiPage]:
    pages = load_all_pages()
    needs_bootstrap = force_bootstrap_if_empty or not pages or _missing_core_pages(pages)
    bootstrapped_now = False
    if needs_bootstrap and PARSED_DIR.exists():
        with _BOOTSTRAP_LOCK:
            pages = load_all_pages()
            if force_bootstrap_if_empty or not pages or _missing_core_pages(pages):
                bootstrapped = bootstrap_pages(use_llm=False)
                if bootstrapped:
                    pages = load_all_pages()
                    bootstrapped_now = True
    if pages and (bootstrapped_now or not INDEX_PAGE_PATH.exists() or _count_lines(INDEX_PAGE_PATH) == 0):
        build_index(pages=pages, index_dir=INDEX_DIR)
    return pages


def _missing_core_pages(pages: list[WikiPage]) -> bool:
    if not pages:
        return True
    existing_ids = {page.page_id for page in pages}
    core_ids = {str(item.get("page_id", "")).strip() for item in PAGE_BLUEPRINTS if item.get("page_id")}
    return not core_ids.issubset(existing_ids)


def _count_lines(path: Path) -> int:
    if not path.exists():
        return 0
    return len([line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()])


def _pages_from_ranked_entries(ranked_entries: list[dict[str, Any]]) -> list[WikiPage]:
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


def _collect_citations(pages: list[WikiPage], *, limit: int) -> list[dict[str, Any]]:
    citations: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    counter = 1
    for page in pages:
        refs = list(page.source_refs)
        for section in page.sections:
            refs.extend(section.source_refs)
        for ref in refs:
            key = (
                str(ref.get("document_id", "")),
                str(ref.get("fragment_id", "")),
                str(ref.get("anchor_label", "")),
            )
            if key in seen:
                continue
            seen.add(key)
            citations.append(
                {
                    "citation_id": f"c{counter}",
                    "page_title": page.title,
                    "file_name": ref.get("file_name", ref.get("document_id", "")),
                    "anchor_label": ref.get("anchor_label", "source"),
                    "quote": ref.get("quote", "") or _ref_quote_from_page(page, ref),
                    "document_id": ref.get("document_id", ""),
                    "fragment_id": ref.get("fragment_id", ""),
                }
            )
            counter += 1
            if len(citations) >= limit:
                return citations
    return citations


def _append_structured_citations(
    citations: list[dict[str, Any]],
    structured_context: dict[str, Any],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    if len(citations) >= limit:
        return citations

    seen = {
        (
            str(item.get("document_id", "")),
            str(item.get("fragment_id", "")),
            str(item.get("anchor_label", "")),
        )
        for item in citations
    }
    next_index = len(citations) + 1
    for relation in structured_context.get("relations", []):
        for ref in relation.get("evidence_refs", []):
            key = (
                str(ref.get("document_id", "")),
                str(ref.get("fragment_id", "")),
                str(ref.get("anchor_label", "")),
            )
            if key in seen:
                continue
            seen.add(key)
            citations.append(
                {
                    "citation_id": f"c{next_index}",
                    "page_title": relation.get("title", relation.get("package_id", "review-package")),
                    "file_name": ref.get("file_name", ref.get("document_id", "")),
                    "anchor_label": ref.get("anchor_label", "source"),
                    "quote": ref.get("quote", ""),
                    "document_id": ref.get("document_id", ""),
                    "fragment_id": ref.get("fragment_id", ""),
                }
            )
            next_index += 1
            if len(citations) >= limit:
                return citations
    return citations


def _ref_quote_from_page(page: WikiPage, ref: dict[str, Any]) -> str:
    for section in page.sections:
        if ref in section.source_refs:
            return section.content[:200]
    return page.summary[:200]


def _deterministic_answer(
    question: str,
    pages: list[WikiPage],
    citations: list[dict[str, Any]],
    structured_context: dict[str, Any],
) -> str:
    structured_relations = structured_context.get("relations", [])
    if not pages and not structured_relations:
        return "根据现有 Wiki 内容，无法回答此问题。"

    lines = [f"针对问题“{question}”，当前可复用的已审批知识如下：", ""]
    if structured_relations:
        lines.append("结构化映射：")
        for index, relation in enumerate(structured_relations[:5], 1):
            citation_label = f"[c{index}]" if index <= len(citations) else ""
            lines.append(
                f"{index}. {relation['from_object_name']} -> {relation['to_object_name']} "
                f"({relation['relation_type']} / {relation['claim_type']}){citation_label}"
            )
        lines.append("")
    if pages:
        lines.append("相关 Wiki 页面：")
        for index, page in enumerate(pages[:3], 1):
            citation_offset = len(structured_relations[:5]) + index
            citation_label = f"[c{citation_offset}]" if citation_offset <= len(citations) else ""
            lines.append(f"{index}. {page.title}：{page.summary}{citation_label}")
    if citations:
        lines.extend(["", "优先证据："])
        for citation in citations[:4]:
            lines.append(f"- [{citation['citation_id']}] {citation['quote']}")
    return "\n".join(lines)


def _confidence_label(value: float) -> str:
    if value >= 0.75:
        return "high"
    if value >= 0.35:
        return "medium"
    return "low"


def _lint_items(report: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for index, issue in enumerate(report.issues, 1):
        items.append(
            {
                "issue_id": f"lint-{index:03d}",
                "type": issue.issue_type,
                "title": issue.description.split("，")[0][:60],
                "target": issue.page_id,
                "severity": issue.severity,
                "detail": issue.description,
                "suggestion": issue.suggestion,
                "status": "proposed" if issue.auto_fixable else "open",
            }
        )
    return items


if __name__ == "__main__":  # pragma: no cover - manual run
    import uvicorn

    uvicorn.run("App.api:app", host="127.0.0.1", port=8000, reload=False)
