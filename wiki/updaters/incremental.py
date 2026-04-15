from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime

from Tool.contracts.canonical import load_canonical_document
from Tool.pipelines.common import parsed_output_path
from wiki.builders.bootstrap import _build_summary, _collect_refs_for_document
from wiki.models.page import PageChangeCandidate, PageSection, UpdateProposal
from wiki.store.files import load_all_pages, save_page, save_proposal

NEGATIVE_MARKERS = ("禁止", "不得", "不应")
POSITIVE_MARKERS = ("允许", "可以")


def incremental_update(document_id: str, *, auto_publish_low_risk: bool = True) -> list[UpdateProposal]:
    candidates = build_incremental_candidates(document_id)
    pages = {page.page_id: page for page in load_all_pages()}
    proposals: list[UpdateProposal] = []

    for candidate in candidates:
        page = pages.get(candidate.page.page_id)
        if page is None:
            continue
        risk_level = _risk_level(candidate.document_type, candidate.candidate_content, page)
        status = "published" if (risk_level == "low" and auto_publish_low_risk) else "pending_review"
        reason = f"文档 {candidate.source_file_name} 为页面《{page.title}》提供了 {len(candidate.source_refs)} 条新证据"
        if risk_level == "high":
            reason += "，包含规范性或冲突风险，需人工审核"

        proposal = UpdateProposal(
            proposal_id=f"proposal-{datetime.now().strftime('%Y%m%d%H%M%S')}-{page.page_id}",
            target_page_id=page.page_id,
            action="append_evidence",
            reason=reason,
            candidate_content=candidate.candidate_content,
            evidence_fragment_ids=list(candidate.evidence_fragment_ids),
            source_refs=list(candidate.source_refs),
            risk_level=risk_level,
            status=status,
            source_document_ids=list(candidate.source_document_ids),
            tool_trace=list(candidate.tool_trace),
        )
        save_proposal(proposal)
        proposals.append(proposal)

        if status == "published":
            save_page(candidate.page)

    return proposals


def build_incremental_candidates(document_id: str, *, use_llm: bool = False) -> list[PageChangeCandidate]:
    parsed = load_canonical_document(parsed_output_path(document_id))
    pages = {page.page_id: page for page in load_all_pages()}
    candidates: list[PageChangeCandidate] = []

    for page in pages.values():
        blueprint = _page_to_blueprint(page)
        refs = [ref for _, ref in _collect_refs_for_document(parsed, blueprint)]
        refs = [ref for ref in refs if (ref["document_id"], ref["fragment_id"]) not in _existing_ref_keys(page)]
        if not refs:
            continue

        candidate_content = _build_summary(page.title, refs, use_llm=use_llm)
        candidate_page = deepcopy(page)
        candidate_page.sections.append(
            PageSection(
                heading=f"增量更新 {parsed.document.file_name}",
                content=candidate_content,
                source_refs=refs,
            )
        )
        candidate_page.source_refs.extend(refs)
        candidate_page.summary = candidate_page.summary if len(candidate_page.summary) >= len(candidate_content) else candidate_content
        candidate_page.page_version += 1
        candidate_page.updated_at = datetime.now().isoformat(timespec="seconds")
        candidates.append(
            PageChangeCandidate(
                page=candidate_page,
                action="append_evidence",
                candidate_content=candidate_content,
                document_type=parsed.document.doc_type,
                source_file_name=parsed.document.file_name,
                source_refs=refs,
                evidence_fragment_ids=[ref["fragment_id"] for ref in refs if ref.get("fragment_id")],
                source_document_ids=sorted({ref["document_id"] for ref in refs if ref.get("document_id")}),
                tool_trace=["wiki.updaters.incremental.build_incremental_candidates"],
            )
        )

    return candidates


def _page_to_blueprint(page) -> dict:
    keywords = [page.title, *page.aliases]
    for linked in page.linked_pages:
        if linked != page.title:
            keywords.append(linked)
    section_keywords = [page.title, *page.aliases]
    return {
        "page_id": page.page_id,
        "title": page.title,
        "page_type": page.page_type,
        "aliases": list(page.aliases),
        "keywords": _dedupe_preserve_order(keywords),
        "section_keywords": _dedupe_preserve_order(section_keywords),
    }


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _existing_ref_keys(page) -> set[tuple[str, str]]:
    keys = set()
    for ref in page.source_refs:
        keys.add((ref.get("document_id", ""), ref.get("fragment_id", "")))
    return keys


def _risk_level(doc_type: str, candidate_content: str, page) -> str:
    existing_text = "\n".join(section.content for section in page.sections)
    has_conflict = any(marker in candidate_content for marker in NEGATIVE_MARKERS) and any(marker in existing_text for marker in POSITIVE_MARKERS)
    if has_conflict or doc_type == "policy" or "应当" in candidate_content or "必须" in candidate_content:
        return "high"
    if doc_type == "guidance":
        return "low"
    return "medium"


def main() -> None:
    parser = argparse.ArgumentParser(description="Create incremental Wiki update proposals for a parsed document.")
    parser.add_argument("--document-id", required=True, help="Document id generated during ingest.")
    parser.add_argument("--no-auto-publish-low-risk", action="store_true", help="Keep low-risk proposals in pending_review.")
    args = parser.parse_args()

    proposals = incremental_update(args.document_id, auto_publish_low_risk=not args.no_auto_publish_low_risk)
    for proposal in proposals:
        print(f"PROPOSAL {proposal.proposal_id} -> {proposal.target_page_id} ({proposal.status})")


if __name__ == "__main__":
    main()
