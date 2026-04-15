from __future__ import annotations

import json

from wiki.models.page import UpdateProposal


def test_list_pending_proposal_ids_filters_by_status(tmp_dir, monkeypatch):
    proposals_dir = tmp_dir / "proposals"
    proposals_dir.mkdir(parents=True, exist_ok=True)
    (proposals_dir / "proposal-a.json").write_text(
        json.dumps({"proposal_id": "proposal-a", "status": "pending_review"}, ensure_ascii=False),
        encoding="utf-8",
    )
    (proposals_dir / "proposal-b.json").write_text(
        json.dumps({"proposal_id": "proposal-b", "status": "published"}, ensure_ascii=False),
        encoding="utf-8",
    )

    monkeypatch.setattr("wiki.updaters.review_publish.PROPOSAL_DIR", proposals_dir)

    from wiki.updaters.review_publish import list_pending_proposal_ids

    assert list_pending_proposal_ids() == ["proposal-a"]


def test_approve_all_pending_proposals_uses_single_approve_path(monkeypatch):
    monkeypatch.setattr("wiki.updaters.review_publish.list_pending_proposal_ids", lambda: ["proposal-a", "proposal-b"])

    def fake_approve(proposal_id: str):
        return UpdateProposal(
            proposal_id=proposal_id,
            target_page_id="页面",
            action="append_evidence",
            reason="ok",
            candidate_content="content",
            status="published",
        )

    monkeypatch.setattr("wiki.updaters.review_publish.approve_proposal", fake_approve)

    from wiki.updaters.review_publish import approve_all_pending_proposals

    result = approve_all_pending_proposals()
    assert [item.proposal_id for item in result] == ["proposal-a", "proposal-b"]
