from __future__ import annotations

import json


def test_export_writes_markdown_files(tmp_dir):
    pages_dir = tmp_dir / "pages"
    proposals_dir = tmp_dir / "proposals"
    export_dir = tmp_dir / "obsidian"
    pages_dir.mkdir()
    proposals_dir.mkdir()

    (pages_dir / "风险管理.json").write_text(
        json.dumps(
            {
                "page_id": "风险管理",
                "title": "风险管理",
                "page_type": "concept",
                "summary": "summary",
                "sections": [{"heading": "概述", "content": "content", "source_refs": []}],
                "linked_pages": ["质量管理体系"],
                "source_refs": [{"file_name": "training.pdf", "anchor_label": "p.2", "quote": "quote"}],
                "review_status": "published",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (pages_dir / "质量管理体系.json").write_text(
        json.dumps(
            {
                "page_id": "质量管理体系",
                "title": "质量管理体系",
                "page_type": "concept",
                "summary": "summary-2",
                "sections": [],
                "linked_pages": [],
                "source_refs": [],
                "review_status": "published",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (proposals_dir / "proposal-1.json").write_text(
        json.dumps(
            {
                "proposal_id": "proposal-1",
                "target_page_id": "风险管理",
                "action": "append_evidence",
                "reason": "reason",
                "candidate_content": "candidate",
                "evidence_fragment_ids": ["frag-1"],
                "risk_level": "low",
                "status": "published",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    from wiki.exporters import obsidian

    original_page_dir = obsidian.PAGE_DIR
    original_proposal_dir = obsidian.PROPOSAL_DIR
    original_export_dir = obsidian.EXPORT_DIR
    obsidian.PAGE_DIR = pages_dir
    obsidian.PROPOSAL_DIR = proposals_dir
    obsidian.EXPORT_DIR = export_dir
    try:
        target = obsidian.sync_to_obsidian()
    finally:
        obsidian.PAGE_DIR = original_page_dir
        obsidian.PROPOSAL_DIR = original_proposal_dir
        obsidian.EXPORT_DIR = original_export_dir

    assert target == export_dir
    assert (export_dir / "风险管理.md").exists()
    assert (export_dir / "质量管理体系.md").exists()
    assert (export_dir / "Proposals" / "proposal-1.md").exists()

    page_markdown = (export_dir / "风险管理.md").read_text(encoding="utf-8")
    proposal_markdown = (export_dir / "Proposals" / "proposal-1.md").read_text(encoding="utf-8")
    assert "[[质量管理体系]]" in page_markdown
    assert "[[风险管理]]" in proposal_markdown


def test_clear_proposal_output_removes_json_and_obsidian_markdown(tmp_dir):
    proposals_dir = tmp_dir / "proposals"
    obsidian_proposals_dir = tmp_dir / "obsidian" / "Proposals"
    proposals_dir.mkdir(parents=True)
    obsidian_proposals_dir.mkdir(parents=True)

    proposal_json = proposals_dir / "proposal-legacy.json"
    proposal_md = obsidian_proposals_dir / "proposal-legacy.md"
    proposal_json.write_text("{}", encoding="utf-8")
    proposal_md.write_text("# legacy", encoding="utf-8")

    from wiki.store import files

    original_proposal_dir = files.PROPOSAL_DIR
    original_obsidian_dir = files.OBSIDIAN_PROPOSAL_DIR
    files.PROPOSAL_DIR = proposals_dir
    files.OBSIDIAN_PROPOSAL_DIR = obsidian_proposals_dir
    try:
        files.clear_proposal_output()
    finally:
        files.PROPOSAL_DIR = original_proposal_dir
        files.OBSIDIAN_PROPOSAL_DIR = original_obsidian_dir

    assert not proposal_json.exists()
    assert not proposal_md.exists()


def test_export_skips_archived_proposals(tmp_dir):
    pages_dir = tmp_dir / "pages"
    proposals_dir = tmp_dir / "proposals"
    export_dir = tmp_dir / "obsidian"
    pages_dir.mkdir()
    proposals_dir.mkdir()

    (pages_dir / "风险管理.json").write_text(
        json.dumps(
            {
                "page_id": "风险管理",
                "title": "风险管理",
                "page_type": "concept",
                "summary": "summary",
                "sections": [],
                "linked_pages": [],
                "source_refs": [],
                "review_status": "published",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (proposals_dir / "proposal-old.json").write_text(
        json.dumps(
            {
                "proposal_id": "proposal-old",
                "target_page_id": "",
                "action": "archived",
                "reason": "archived",
                "candidate_content": "",
                "evidence_fragment_ids": [],
                "risk_level": "low",
                "status": "archived",
                "archived": True,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    from wiki.exporters import obsidian

    original_page_dir = obsidian.PAGE_DIR
    original_proposal_dir = obsidian.PROPOSAL_DIR
    original_export_dir = obsidian.EXPORT_DIR
    obsidian.PAGE_DIR = pages_dir
    obsidian.PROPOSAL_DIR = proposals_dir
    obsidian.EXPORT_DIR = export_dir
    try:
        obsidian.sync_to_obsidian()
    finally:
        obsidian.PAGE_DIR = original_page_dir
        obsidian.PROPOSAL_DIR = original_proposal_dir
        obsidian.EXPORT_DIR = original_export_dir

    assert not (export_dir / "Proposals" / "proposal-old.md").exists()


def test_export_prefers_canonical_chinese_page_id_when_legacy_json_still_exists(tmp_dir):
    pages_dir = tmp_dir / "pages"
    export_dir = tmp_dir / "obsidian"
    pages_dir.mkdir()

    (pages_dir / "document-and-data-management.json").write_text(
        json.dumps(
            {
                "page_id": "document-and-data-management",
                "title": "文件和数据管理",
                "page_type": "process",
                "summary": "legacy",
                "sections": [],
                "linked_pages": ["quality-management-system"],
                "source_refs": [],
                "updated_at": "2026-04-15T10:00:00",
                "review_status": "pending_review",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (pages_dir / "文件和数据管理.json").write_text(
        json.dumps(
            {
                "page_id": "文件和数据管理",
                "title": "文件和数据管理",
                "page_type": "process",
                "summary": "canonical",
                "sections": [],
                "linked_pages": ["质量管理体系"],
                "source_refs": [],
                "updated_at": "2026-04-15T10:05:00",
                "review_status": "published",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (pages_dir / "质量管理体系.json").write_text(
        json.dumps(
            {
                "page_id": "质量管理体系",
                "title": "质量管理体系",
                "page_type": "concept",
                "summary": "summary",
                "sections": [],
                "linked_pages": [],
                "source_refs": [],
                "updated_at": "2026-04-15T10:05:00",
                "review_status": "published",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    from wiki.exporters import obsidian

    original_page_dir = obsidian.PAGE_DIR
    original_export_dir = obsidian.EXPORT_DIR
    obsidian.PAGE_DIR = pages_dir
    obsidian.EXPORT_DIR = export_dir
    try:
        obsidian.sync_to_obsidian()
    finally:
        obsidian.PAGE_DIR = original_page_dir
        obsidian.EXPORT_DIR = original_export_dir

    page_markdown = (export_dir / "文件和数据管理.md").read_text(encoding="utf-8")
    assert page_markdown.count("# 文件和数据管理") == 1
    assert "page_id: 文件和数据管理" in page_markdown
    assert "page_id: document-and-data-management" not in page_markdown

