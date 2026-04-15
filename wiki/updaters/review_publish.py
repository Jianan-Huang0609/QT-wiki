from __future__ import annotations

import argparse
import json
from datetime import datetime

from wiki.models.page import PageSection, UpdateProposal
from wiki.store.files import PROPOSAL_DIR, load_page, save_page


def list_pending_proposal_ids() -> list[str]:
    if not PROPOSAL_DIR.exists():
        return []
    proposal_ids: list[str] = []
    for path in sorted(PROPOSAL_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("status") == "pending_review":
            proposal_ids.append(path.stem)
    return proposal_ids


def approve_proposal(proposal_id: str) -> UpdateProposal | None:
    proposal_path = PROPOSAL_DIR / f"{proposal_id}.json"
    if not proposal_path.exists():
        return None

    data = json.loads(proposal_path.read_text(encoding="utf-8"))
    page = load_page(data["target_page_id"])
    action = data.get("action", "")

    if action == "bootstrap_page":
        page.review_status = "published"
        page.updated_at = datetime.now().isoformat(timespec="seconds")
        save_page(page)
    else:
        page.sections.append(
            PageSection(
                heading="审核通过发布",
                content=data.get("candidate_content", ""),
                source_refs=data.get("source_refs", []),
            )
        )
        page.source_refs.extend(data.get("source_refs", []))
        page.review_status = "published"
        page.page_version += 1
        page.updated_at = datetime.now().isoformat(timespec="seconds")
        save_page(page)

    data["status"] = "published"
    data["review_mode"] = "manual"
    data["review_notes"] = "人工审核通过后发布"
    proposal_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return UpdateProposal(**data)


def approve_all_pending_proposals() -> list[UpdateProposal]:
    approved: list[UpdateProposal] = []
    for proposal_id in list_pending_proposal_ids():
        proposal = approve_proposal(proposal_id)
        if proposal is not None:
            approved.append(proposal)
    return approved


def main() -> None:
    parser = argparse.ArgumentParser(description="批准并发布待审核的 Wiki proposal。")
    parser.add_argument("--proposal-id", help="提案 ID，位于 wiki/output/proposals/")
    parser.add_argument("--approve-all", action="store_true", help="批准并发布全部待审核提案。")
    args = parser.parse_args()

    if args.approve_all:
        approved = approve_all_pending_proposals()
        print(f"APPROVED {len(approved)} PENDING PROPOSALS")
        for proposal in approved:
            print(f"PROPOSAL {proposal.proposal_id} -> {proposal.status}")
        return

    if not args.proposal_id:
        print("ERROR: use --proposal-id <id> or --approve-all")
        return

    result = approve_proposal(args.proposal_id)
    if result is None:
        print(f"PROPOSAL {args.proposal_id} NOT FOUND")
        return
    print(f"PROPOSAL {result.proposal_id} -> {result.status}")


if __name__ == "__main__":
    main()
