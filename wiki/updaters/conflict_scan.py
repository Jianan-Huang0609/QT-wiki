from __future__ import annotations

import argparse
from datetime import datetime

from wiki.models.page import UpdateProposal
from wiki.store.files import load_all_pages, save_proposal

MANDATORY_MARKERS = ("应当", "必须", "应", "须")
PROHIBITIVE_MARKERS = ("禁止", "不得", "不应", "严禁")
PERMISSIVE_MARKERS = ("允许", "可以", "可")


def conflict_scan() -> list[UpdateProposal]:
    pages = load_all_pages()
    proposals: list[UpdateProposal] = []

    for page in pages:
        section_texts = [section.content for section in page.sections]
        conflicts = _detect_conflicts(section_texts)
        for conflict in conflicts:
            proposal = UpdateProposal(
                proposal_id=f"conflict-{datetime.now().strftime('%Y%m%d%H%M%S')}-{page.page_id}",
                target_page_id=page.page_id,
                action="flag_conflict",
                reason=conflict["reason"],
                candidate_content="",
                evidence_fragment_ids=[],
                risk_level="high",
                status="pending_review",
            )
            save_proposal(proposal)
            proposals.append(proposal)

    return proposals


def _detect_conflicts(section_texts: list[str]) -> list[dict]:
    conflicts: list[dict] = []
    mandatory_clauses: list[tuple[int, str]] = []
    prohibitive_clauses: list[tuple[int, str]] = []
    permissive_clauses: list[tuple[int, str]] = []

    for index, text in enumerate(section_texts):
        for marker in MANDATORY_MARKERS:
            if marker in text:
                mandatory_clauses.append((index, text))
                break
        for marker in PROHIBITIVE_MARKERS:
            if marker in text:
                prohibitive_clauses.append((index, text))
                break
        for marker in PERMISSIVE_MARKERS:
            if marker in text:
                permissive_clauses.append((index, text))
                break

    for p_idx, p_text in prohibitive_clauses:
        for m_idx, m_text in permissive_clauses:
            if p_idx != m_idx and _overlap_topic(p_text, m_text):
                conflicts.append({
                    "reason": (
                        f"条款冲突：第{p_idx + 1}节含禁止性表述（{p_text[:60]}…），"
                        f"第{m_idx + 1}节含允许性表述（{m_text[:60]}…），"
                        "需人工审核确认适用范围"
                    ),
                })

    for m_idx, m_text in mandatory_clauses:
        for p_idx, p_text in prohibitive_clauses:
            if m_idx != p_idx and _overlap_topic(m_text, p_text):
                conflicts.append({
                    "reason": (
                        f"解释冲突：第{m_idx + 1}节含义务性表述（{m_text[:60]}…），"
                        f"第{p_idx + 1}节含禁止性表述（{p_text[:60]}…），"
                        "同一主题存在矛盾指令，需人工裁定"
                    ),
                })

    return conflicts


def _overlap_topic(text_a: str, text_b: str) -> bool:
    from Tool.normalizers import extract_terms

    terms_a = set(extract_terms([text_a], limit=5))
    terms_b = set(extract_terms([text_b], limit=5))
    return bool(terms_a & terms_b)


def main() -> None:
    parser = argparse.ArgumentParser(description="Scan Wiki pages for clause conflicts and interpretation conflicts.")
    args = parser.parse_args()

    proposals = conflict_scan()
    if not proposals:
        print("NO CONFLICTS FOUND")
    for proposal in proposals:
        print(f"CONFLICT {proposal.proposal_id} -> {proposal.target_page_id} ({proposal.reason[:80]})")


if __name__ == "__main__":
    main()
