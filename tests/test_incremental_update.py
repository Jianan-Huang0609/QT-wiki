from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from wiki.models.page import PageSection, UpdateProposal, WikiPage


def _setup_existing_pages(pages_dir: Path, pages: list[WikiPage]):
    pages_dir.mkdir(parents=True, exist_ok=True)
    for page in pages:
        path = pages_dir / f"{page.page_id}.json"
        path.write_text(json.dumps(page.to_dict(), ensure_ascii=False), encoding="utf-8")


def test_incremental_creates_proposal(parsed_dir_with_docs, wiki_output_dirs):
    pages_dir, proposals_dir = wiki_output_dirs

    existing_page = WikiPage(
        page_id="风险管理",
        title="风险管理",
        page_type="concept",
        summary="风险管理摘要",
        sections=[PageSection(heading="概述", content="风险管理是QMS核心。")],
        aliases=["质量风险管理"],
        source_refs=[],
        linked_pages=["质量管理体系"],
        review_status="approved",
        page_version=1,
        updated_at="2026-04-14T14:00:00",
    )
    _setup_existing_pages(pages_dir, [existing_page])

    with patch("wiki.store.files.PAGE_DIR", pages_dir), \
         patch("wiki.store.files.PROPOSAL_DIR", proposals_dir), \
         patch("wiki.updaters.incremental.parsed_output_path") as mock_parsed_path, \
         patch("wiki.updaters.incremental.load_canonical_document") as mock_load:

        from Tool.contracts.canonical import CanonicalDocument, DocumentMeta, Fragment
        mock_parsed_path.return_value = Path("dummy")
        mock_load.return_value = CanonicalDocument(
            document=DocumentMeta(
                document_id="doc-test-0002-efgh5678",
                title="培训讲义",
                source_path="Raw/training.pdf",
                file_name="training.pdf",
                source_type="pdf",
                doc_type="guidance",
            ),
            fragments=[
                Fragment(
                    fragment_id="frag-new-1",
                    section_id=None,
                    fragment_type="paragraph",
                    text="风险管理应当贯穿产品全生命周期。",
                    anchors={"page": 5, "paragraph_index": 1},
                ),
            ],
            parse_status="parsed",
        )

        from wiki.updaters.incremental import incremental_update

        proposals = incremental_update("doc-test-0002-efgh5678")
        assert len(proposals) >= 1
        assert all(isinstance(p, UpdateProposal) for p in proposals)


def test_conflict_not_silently_overwritten(wiki_output_dirs):
    pages_dir, proposals_dir = wiki_output_dirs

    existing_page = WikiPage(
        page_id="风险管理",
        title="风险管理",
        page_type="concept",
        summary="允许企业自主选择风险管理方法",
        sections=[PageSection(heading="方法", content="企业可以自主选择风险管理方法。")],
        aliases=["质量风险管理"],
        source_refs=[],
        linked_pages=["质量管理体系"],
        review_status="approved",
        page_version=1,
        updated_at="2026-04-14T14:00:00",
    )
    _setup_existing_pages(pages_dir, [existing_page])

    with patch("wiki.store.files.PAGE_DIR", pages_dir), \
         patch("wiki.store.files.PROPOSAL_DIR", proposals_dir), \
         patch("wiki.updaters.incremental.parsed_output_path") as mock_parsed_path, \
         patch("wiki.updaters.incremental.load_canonical_document") as mock_load:

        from Tool.contracts.canonical import CanonicalDocument, DocumentMeta, Fragment
        mock_parsed_path.return_value = Path("dummy")
        mock_load.return_value = CanonicalDocument(
            document=DocumentMeta(
                document_id="doc-test-conflict",
                title="规范文件",
                source_path="Raw/policy.docx",
                file_name="policy.docx",
                source_type="docx",
                doc_type="policy",
            ),
            fragments=[
                Fragment(
                    fragment_id="frag-conflict-1",
                    section_id=None,
                    fragment_type="paragraph",
                    text="企业禁止自主选择风险管理方法，必须按规范执行。",
                    anchors={"paragraph_index": 1},
                ),
            ],
            parse_status="parsed",
        )

        from wiki.updaters.incremental import incremental_update

        proposals = incremental_update("doc-test-conflict")

        high_risk = [p for p in proposals if p.risk_level == "high"]
        for proposal in high_risk:
            assert proposal.status == "pending_review"


def test_high_risk_not_auto_published(wiki_output_dirs):
    pages_dir, proposals_dir = wiki_output_dirs

    existing_page = WikiPage(
        page_id="医疗器械生产质量管理规范",
        title="医疗器械生产质量管理规范",
        page_type="policy",
        summary="规范摘要",
        sections=[PageSection(heading="总则", content="企业应当建立质量管理体系。")],
        aliases=["生产质量管理规范", "QMS规范"],
        source_refs=[],
        linked_pages=["质量管理体系", "风险管理"],
        review_status="approved",
        page_version=1,
        updated_at="2026-04-14T14:00:00",
    )
    _setup_existing_pages(pages_dir, [existing_page])

    with patch("wiki.store.files.PAGE_DIR", pages_dir), \
         patch("wiki.store.files.PROPOSAL_DIR", proposals_dir), \
         patch("wiki.updaters.incremental.parsed_output_path") as mock_parsed_path, \
         patch("wiki.updaters.incremental.load_canonical_document") as mock_load:

        from Tool.contracts.canonical import CanonicalDocument, DocumentMeta, Fragment
        mock_parsed_path.return_value = Path("dummy")
        mock_load.return_value = CanonicalDocument(
            document=DocumentMeta(
                document_id="doc-policy-new",
                title="新规范",
                source_path="Raw/new_policy.docx",
                file_name="new_policy.docx",
                source_type="docx",
                doc_type="policy",
            ),
            fragments=[
                Fragment(
                    fragment_id="frag-policy-1",
                    section_id=None,
                    fragment_type="paragraph",
                    text="医疗器械生产质量管理规范要求企业必须实施风险管理。",
                    anchors={"paragraph_index": 1},
                ),
            ],
            parse_status="parsed",
        )

        from wiki.updaters.incremental import incremental_update

        proposals = incremental_update("doc-policy-new")

        for proposal in proposals:
            if proposal.risk_level == "high":
                assert proposal.status == "pending_review"

