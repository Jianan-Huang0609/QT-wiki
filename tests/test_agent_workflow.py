from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from wiki.models.page import PageSection, UpdateProposal, WikiPage


def test_agent_bootstraps_when_pages_do_not_exist(tmp_dir):
    state_path = tmp_dir / "agent_state.json"
    run_log_dir = tmp_dir / "runs"
    manifest = {
        "document_id": "doc-new-1",
        "file_name": "policy.docx",
        "checksum": "abc123",
        "parse_status": "pending",
        "parsed_output": None,
    }
    parsed_manifest = {
        **manifest,
        "parse_status": "parsed",
        "parsed_output": "Tool/output/parsed/doc-new-1.json",
    }
    with patch("App.agent.ingest", return_value=[manifest]), \
         patch("App.agent.parse_one") as mock_parse_one, \
         patch("App.agent.load_manifest", return_value=parsed_manifest), \
         patch("App.agent.load_all_pages", return_value=[]), \
         patch(
             "App.agent.run_agent_workflow",
             return_value={
                 "bootstrap_performed": True,
                 "pages_created": 1,
                 "proposals_created": 1,
                 "pages_published": 0,
                 "per_document_proposals": {"doc-new-1": 1},
             },
         ) as mock_workflow, \
         patch("App.agent.conflict_scan", return_value=[]), \
         patch("App.agent.sync_to_obsidian") as mock_sync:

        from App.agent import maintain_wiki

        report = maintain_wiki(
            input_path="Raw/",
            state_path=state_path,
            run_log_dir=run_log_dir,
        )

    assert mock_parse_one.call_count == 1
    assert mock_workflow.call_count == 1
    assert mock_sync.call_count == 1
    assert report.bootstrap_performed is True
    assert report.pages_created == 1
    assert report.proposals_created == 1
    assert report.documents_parsed == ["doc-new-1"]
    assert report.documents[0].action == "bootstrapped"

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["documents"]["doc-new-1"]["last_action"] == "bootstrap"
    run_reports = list(run_log_dir.glob("*.json"))
    assert len(run_reports) == 1


def test_agent_skips_repeated_incremental_updates_for_same_checksum(tmp_dir):
    state_path = tmp_dir / "agent_state.json"
    run_log_dir = tmp_dir / "runs"
    manifest = {
        "document_id": "doc-existing-1",
        "file_name": "guidance.pdf",
        "checksum": "same-checksum",
        "parse_status": "parsed",
        "parsed_output": "Tool/output/parsed/doc-existing-1.json",
    }
    page = WikiPage(
        page_id="质量管理体系",
        title="质量管理体系",
        page_type="concept",
        summary="summary",
    )
    with patch("App.agent.ingest", return_value=[manifest]), \
         patch("App.agent.load_all_pages", return_value=[page]), \
         patch(
             "App.agent.run_agent_workflow",
             side_effect=[
                 {
                     "bootstrap_performed": False,
                     "pages_created": 0,
                     "proposals_created": 1,
                     "pages_published": 1,
                     "per_document_proposals": {"doc-existing-1": 1},
                 },
                 {
                     "bootstrap_performed": False,
                     "pages_created": 0,
                     "proposals_created": 0,
                     "pages_published": 0,
                     "per_document_proposals": {},
                 },
             ],
         ) as mock_workflow, \
         patch("App.agent.conflict_scan", return_value=[]), \
         patch("App.agent.sync_to_obsidian"):

        from App.agent import maintain_wiki

        first_report = maintain_wiki(
            input_path="Raw/",
            state_path=state_path,
            run_log_dir=run_log_dir,
        )
        second_report = maintain_wiki(
            input_path="Raw/",
            state_path=state_path,
            run_log_dir=run_log_dir,
        )

    assert mock_workflow.call_count == 1
    assert first_report.proposals_created == 1
    assert first_report.documents[0].action == "incremental_update"
    assert second_report.proposals_created == 0
    assert second_report.documents[0].action == "up_to_date"


def test_agent_clean_rebuild_clears_outputs_and_bootstraps(tmp_dir):
    state_path = tmp_dir / "agent_state.json"
    run_log_dir = tmp_dir / "runs"
    manifest = {
        "document_id": "doc-clean-1",
        "file_name": "policy.docx",
        "checksum": "clean123",
        "parse_status": "parsed",
        "parsed_output": "Tool/output/parsed/doc-clean-1.json",
    }
    with patch("App.agent.ingest", return_value=[manifest]), \
         patch("App.agent.load_all_pages", return_value=[]), \
         patch("App.agent.clear_page_output") as mock_clear_pages, \
         patch("App.agent.clear_proposal_output") as mock_clear_proposals, \
         patch(
             "App.agent.run_agent_workflow",
             return_value={
                 "bootstrap_performed": True,
                 "pages_created": 1,
                 "proposals_created": 1,
                 "pages_published": 0,
                 "per_document_proposals": {"doc-clean-1": 1},
             },
         ) as mock_workflow, \
         patch("App.agent.conflict_scan", return_value=[]), \
         patch("App.agent.sync_to_obsidian"):

        from App.agent import maintain_wiki

        report = maintain_wiki(
            input_path="Raw/",
            clean_rebuild=True,
            state_path=state_path,
            run_log_dir=run_log_dir,
        )

    assert mock_clear_pages.call_count == 1
    assert mock_clear_proposals.call_count == 1
    assert mock_workflow.call_count == 1
    assert report.bootstrap_performed is True
    assert report.pages_created == 1
    assert report.proposals_created == 1


def test_agent_clean_rebuild_forces_bootstrap_even_if_locked_pages_remain(tmp_dir):
    state_path = tmp_dir / "agent_state.json"
    run_log_dir = tmp_dir / "runs"
    state_path.write_text(
        json.dumps(
            {
                "documents": {
                    "legacy-doc": {
                        "last_action": "incremental_update",
                        "last_maintained_checksum": "old",
                        "last_parse_status": "parsed",
                    }
                },
                "last_run": None,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    manifest = {
        "document_id": "doc-clean-2",
        "file_name": "policy.docx",
        "checksum": "clean456",
        "parse_status": "parsed",
        "parsed_output": "Tool/output/parsed/doc-clean-2.json",
    }
    locked_page = WikiPage(
        page_id="locked-page",
        title="旧页面",
        page_type="concept",
        summary="legacy",
    )

    with patch("App.agent.ingest", return_value=[manifest]), \
         patch("App.agent.load_all_pages", return_value=[locked_page]), \
         patch("App.agent.clear_page_output"), \
         patch("App.agent.clear_proposal_output"), \
         patch(
             "App.agent.run_agent_workflow",
             return_value={
                 "bootstrap_performed": True,
                 "pages_created": 1,
                 "proposals_created": 1,
                 "pages_published": 0,
                 "per_document_proposals": {"doc-clean-2": 1},
             },
         ) as mock_workflow, \
         patch("App.agent.conflict_scan", return_value=[]), \
         patch("App.agent.sync_to_obsidian"):

        from App.agent import maintain_wiki

        report = maintain_wiki(
            input_path="Raw/",
            clean_rebuild=True,
            state_path=state_path,
            run_log_dir=run_log_dir,
        )

    assert mock_workflow.call_count == 1
    assert report.bootstrap_performed is True
    assert report.proposals_created == 1

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert "legacy-doc" not in state["documents"]
    assert state["documents"]["doc-clean-2"]["last_action"] == "bootstrap"


def test_bootstrap_candidates_require_human_review_by_default():
    from wiki.models.page import PageChangeCandidate
    from wiki.review import evaluate_change_candidate

    candidate = PageChangeCandidate(
        page=WikiPage(
            page_id="文件和数据管理",
            title="文件和数据管理",
            page_type="process",
            summary="这是摘要",
            sections=[PageSection(heading="关键依据", content="这是证据")],
        ),
        action="bootstrap_page",
        candidate_content="# 文件和数据管理\n\n## 摘要\n这是摘要",
        source_refs=[{"fragment_id": "frag-1"}],
        evidence_fragment_ids=["frag-1"],
        source_document_ids=["doc-1"],
    )

    decision = evaluate_change_candidate(candidate, use_llm=False)

    assert decision.review_mode == "human_required"
    assert decision.auto_publish is False
    assert decision.change_scope == "large"

