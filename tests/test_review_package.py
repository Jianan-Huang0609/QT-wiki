from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from App.agents.ingest_agent import IngestAgent
from Tool.document_processor import ProcessedDocument
from Tool.contracts.canonical import CanonicalDocument, DocumentMeta, Fragment
from wiki.models import DocumentIdentity, ReviewPackage, ReviewRelation


def test_render_and_save_review_package(tmp_dir):
    from wiki.store.files import load_review_package, save_review_package, update_review_package_decision

    package_dir = tmp_dir / "review_packages"
    obsidian_dir = tmp_dir / "obsidian" / "ReviewPackages"
    review_package = ReviewPackage(
        package_id="review-doc-test",
        document_id="doc-test",
        status="pending_review",
        document_identity=DocumentIdentity(
            business_type="external_reference",
            title="质量管理体系培训讲义",
            effective_level="reference_only",
            is_binding=False,
            confidence=0.8,
            source_refs=[
                {
                    "document_id": "doc-test",
                    "fragment_id": "frag-1",
                    "file_name": "training.pdf",
                    "anchor_label": "p.1",
                    "quote": "质量管理体系是企业确保产品符合法规要求的核心框架。",
                }
            ],
        ),
        evidence_refs=[
            {
                "document_id": "doc-test",
                "fragment_id": "frag-1",
                "file_name": "training.pdf",
                "anchor_label": "p.1",
                "quote": "质量管理体系是企业确保产品符合法规要求的核心框架。",
            }
        ],
        human_questions=[],
        issues=[],
        candidate_page_titles=["质量管理体系"],
        created_at="2026-04-29T10:00:00",
        updated_at="2026-04-29T10:00:00",
        tool_trace=["test"],
    )

    with patch("wiki.store.files.REVIEW_PACKAGE_DIR", package_dir), patch(
        "wiki.store.files.OBSIDIAN_REVIEW_PACKAGE_DIR", obsidian_dir
    ):
        save_review_package(review_package)
        update_review_package_decision(
            "review-doc-test",
            identity_decision="confirmed",
            confirmed_business_type="external_reference",
            confirmed_effective_level="reference_only",
            confirmed_is_binding=False,
            review_notes="只可作为解释材料使用。",
            reviewed_by="qa.lead",
            reviewed_at="2026-04-29T10:30:00",
        )
        loaded = load_review_package("review-doc-test")

    assert loaded.document_id == "doc-test"
    assert loaded.document_identity.business_type == "external_reference"
    assert loaded.identity_decision == "confirmed"
    assert loaded.reviewed_by == "qa.lead"
    markdown_path = obsidian_dir / "review-doc-test.md"
    assert markdown_path.exists()
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "## 文档身份" in markdown
    assert "## 人工确认结果" in markdown


def test_ingest_agent_builds_review_package_for_guidance_material():
    canonical = CanonicalDocument(
        document=DocumentMeta(
            document_id="doc-test-guidance",
            title="质量管理体系培训讲义",
            source_path="Raw/training.pdf",
            file_name="training.pdf",
            source_type="pdf",
            doc_type="guidance",
        ),
        fragments=[
            Fragment(
                fragment_id="frag-1",
                section_id="sec-1",
                fragment_type="paragraph",
                text="放行审核人应当确认检验记录和偏差处置结果。",
                anchors={"page": 1, "paragraph_index": 1},
            )
        ],
    )
    doc = ProcessedDocument(
        document_id="doc-test-guidance",
        title="质量管理体系培训讲义",
        file_name="training.pdf",
        doc_type="guidance",
        source_type="pdf",
        content="放行审核人应当确认检验记录和偏差处置结果。",
        sections=[{"type": "paragraph", "text": "放行审核人应当确认检验记录和偏差处置结果。", "anchors": {"page": 1}}],
        metadata={},
    )
    candidate = IngestAgent()._extract_candidates_rule_based(doc)[0]

    with patch.object(IngestAgent, "_load_canonical_document", return_value=canonical):
        review_package = IngestAgent()._build_review_package(doc, [candidate])

    assert review_package.document_identity.business_type == "external_reference"
    assert review_package.document_identity.is_binding is False
    assert len(review_package.human_questions) >= 2
    assert review_package.evidence_refs[0]["anchor_label"] == "p.1"
    object_types = {item.object_type for item in review_package.extracted_objects}
    assert "regulation_clause" in object_types or "requirement" in object_types
    assert "deliverable" in object_types or "record" in object_types
    assert "role" in object_types


def test_candidate_publish_requires_confirmed_identity():
    agent = IngestAgent()
    candidate = agent._extract_candidates_rule_based(
        ProcessedDocument(
            document_id="doc-test-guidance",
            title="质量管理体系培训讲义",
            file_name="training.pdf",
            doc_type="guidance",
            source_type="pdf",
            content="内容",
            sections=[],
            metadata={},
        )
    )[0]

    pending_package = ReviewPackage(
        package_id="review-doc-test-guidance",
        document_id="doc-test-guidance",
        status="pending_review",
        document_identity=DocumentIdentity(business_type="external_reference", title="质量管理体系培训讲义"),
    )

    confirmed_package = ReviewPackage(
        package_id="review-doc-test-guidance",
        document_id="doc-test-guidance",
        status="identity_confirmed",
        document_identity=DocumentIdentity(business_type="external_reference", title="质量管理体系培训讲义"),
        identity_decision="confirmed",
        confirmed_business_type="external_reference",
    )

    with patch("wiki.store.list_review_packages", return_value=[pending_package]):
        assert agent._can_publish_candidate(candidate) is False

    with patch("wiki.store.list_review_packages", return_value=[confirmed_package]):
        assert agent._can_publish_candidate(candidate) is True


def test_candidate_publish_requires_relation_confirmation_when_relations_exist():
    agent = IngestAgent()
    candidate = agent._extract_candidates_rule_based(
        ProcessedDocument(
            document_id="doc-test-guidance",
            title="质量管理体系培训讲义",
            file_name="training.pdf",
            doc_type="guidance",
            source_type="pdf",
            content="内容",
            sections=[],
            metadata={},
        )
    )[0]

    pending_relation_package = ReviewPackage(
        package_id="review-doc-test-guidance",
        document_id="doc-test-guidance",
        status="identity_confirmed",
        document_identity=DocumentIdentity(business_type="external_reference", title="质量管理体系培训讲义"),
        identity_decision="confirmed",
        confirmed_business_type="external_reference",
        relation_decision="pending",
        extracted_relations=[
            ReviewRelation(
                relation_id="rel-1",
                relation_type="requires",
                from_object_id="obj-1",
                to_object_id="obj-2",
                claim_type="mandatory",
            )
        ],
    )
    confirmed_relation_package = ReviewPackage(
        package_id="review-doc-test-guidance",
        document_id="doc-test-guidance",
        status="ready_to_publish",
        document_identity=DocumentIdentity(business_type="external_reference", title="质量管理体系培训讲义"),
        identity_decision="confirmed",
        confirmed_business_type="external_reference",
        relation_decision="confirmed",
        extracted_relations=[
            ReviewRelation(
                relation_id="rel-1",
                relation_type="requires",
                from_object_id="obj-1",
                to_object_id="obj-2",
                claim_type="mandatory",
            )
        ],
    )

    with patch("wiki.store.list_review_packages", return_value=[pending_relation_package]):
        assert agent._can_publish_candidate(candidate) is False

    with patch("wiki.store.list_review_packages", return_value=[confirmed_relation_package]):
        assert agent._can_publish_candidate(candidate) is True


def test_load_all_pages_skips_invalid_json(tmp_dir):
    from wiki.store.files import load_all_pages

    page_dir = tmp_dir / "pages"
    page_dir.mkdir(parents=True, exist_ok=True)
    (page_dir / "valid.json").write_text(
        """
{
  "page_id": "valid-page",
  "title": "Valid Page",
  "page_type": "concept",
  "summary": "ok",
  "sections": [],
  "aliases": [],
  "source_refs": [],
  "linked_pages": [],
  "review_status": "published",
  "page_version": 1,
  "updated_at": "2026-04-29T10:00:00"
}
        """.strip(),
        encoding="utf-8",
    )
    (page_dir / "empty.json").write_text("", encoding="utf-8")
    (page_dir / "broken.json").write_text("{", encoding="utf-8")

    with patch("wiki.store.files.PAGE_DIR", page_dir):
        pages = load_all_pages()

    assert len(pages) == 1
    assert pages[0].page_id == "valid-page"
