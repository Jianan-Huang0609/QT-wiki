from __future__ import annotations

import argparse
from datetime import datetime

from wiki.models.page import UpdateProposal
from wiki.store.files import load_all_pages, load_page, save_page


def publish(*, auto_publish_low_risk: bool = True) -> list[UpdateProposal]:
    pages = load_all_pages()
    results: list[UpdateProposal] = []

    for page in pages:
        if page.review_status == "approved":
            page.review_status = "published"
            page.updated_at = datetime.now().isoformat(timespec="seconds")
            save_page(page)
            results.append(UpdateProposal(
                proposal_id=f"publish-{datetime.now().strftime('%Y%m%d%H%M%S')}-{page.page_id}",
                target_page_id=page.page_id,
                action="publish",
                reason="页面审核通过，自动发布",
                candidate_content="",
                evidence_fragment_ids=[],
                risk_level="low",
                status="published",
            ))

    return results


def publish_proposal(proposal_id: str) -> UpdateProposal | None:
    from wiki.store.files import PROPOSAL_DIR

    proposal_path = PROPOSAL_DIR / f"{proposal_id}.json"
    if not proposal_path.exists():
        return None

    import json
    data = json.loads(proposal_path.read_text(encoding="utf-8"))
    if data.get("risk_level") == "high":
        return UpdateProposal(
            proposal_id=proposal_id,
            target_page_id=data["target_page_id"],
            action=data.get("action", ""),
            reason="高风险提案不允许自动发布，需人工审核",
            candidate_content=data.get("candidate_content", ""),
            evidence_fragment_ids=data.get("evidence_fragment_ids", []),
            risk_level="high",
            status="blocked",
        )

    page = load_page(data["target_page_id"])
    from wiki.models.page import PageSection
    page.sections.append(PageSection(
        heading=f"审核通过发布",
        content=data.get("candidate_content", ""),
        source_refs=data.get("evidence_fragment_ids", []),
    ))
    page.review_status = "published"
    page.page_version += 1
    page.updated_at = datetime.now().isoformat(timespec="seconds")
    save_page(page)

    data["status"] = "published"
    proposal_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    return UpdateProposal(
        proposal_id=proposal_id,
        target_page_id=data["target_page_id"],
        action=data.get("action", ""),
        reason="低风险提案自动发布",
        candidate_content=data.get("candidate_content", ""),
        evidence_fragment_ids=data.get("evidence_fragment_ids", []),
        risk_level=data.get("risk_level", "low"),
        status="published",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish approved Wiki pages. High-risk proposals are blocked.")
    parser.add_argument("--no-auto-low-risk", action="store_true", help="Do not auto-publish low-risk proposals.")
    args = parser.parse_args()

    results = publish(auto_publish_low_risk=not args.no_auto_low_risk)
    for result in results:
        print(f"PUBLISH {result.target_page_id} -> {result.status}")


if __name__ == "__main__":
    main()
