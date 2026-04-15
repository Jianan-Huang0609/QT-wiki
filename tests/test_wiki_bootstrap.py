from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from wiki.models.page import PageSection, WikiPage


def test_bootstrap_generates_pages(parsed_dir_with_docs):
    with patch("wiki.builders.bootstrap.PARSED_DIR", parsed_dir_with_docs):
        from wiki.builders.bootstrap import bootstrap_pages

        pages = bootstrap_pages(use_llm=False)
        assert len(pages) >= 1
        for page in pages:
            assert page.page_id
            assert page.title
            assert page.page_type in ("policy", "concept", "process", "role")


def test_bootstrap_pages_have_refs(parsed_dir_with_docs, wiki_output_dirs):
    pages_dir, _ = wiki_output_dirs
    with patch("wiki.builders.bootstrap.PARSED_DIR", parsed_dir_with_docs), \
         patch("wiki.builders.bootstrap.save_page") as mock_save:
        from wiki.builders.bootstrap import bootstrap_pages

        pages = bootstrap_pages(use_llm=False)

        pages_with_refs = [p for p in pages if p.source_refs]
        assert len(pages_with_refs) >= 1

        for page in pages_with_refs:
            for ref in page.source_refs:
                assert "document_id" in ref
                assert "fragment_id" in ref


def test_bootstrap_multi_source_merge(parsed_dir_with_docs):
    with patch("wiki.builders.bootstrap.PARSED_DIR", parsed_dir_with_docs), \
         patch("wiki.builders.bootstrap.save_page"):
        from wiki.builders.bootstrap import bootstrap_pages

        pages = bootstrap_pages(use_llm=False)

        qms_page = next((p for p in pages if p.page_id == "质量管理体系"), None)
        if qms_page is not None:
            doc_ids = {ref["document_id"] for ref in qms_page.source_refs}
            assert len(doc_ids) >= 1


def test_bootstrap_page_structure(parsed_dir_with_docs):
    with patch("wiki.builders.bootstrap.PARSED_DIR", parsed_dir_with_docs), \
         patch("wiki.builders.bootstrap.save_page"):
        from wiki.builders.bootstrap import bootstrap_pages

        pages = bootstrap_pages(use_llm=False)
        assert len(pages) > 0

        page = pages[0]
        assert hasattr(page, "page_id")
        assert hasattr(page, "title")
        assert hasattr(page, "page_type")
        assert hasattr(page, "summary")
        assert hasattr(page, "sections")
        assert hasattr(page, "aliases")
        assert hasattr(page, "source_refs")
        assert hasattr(page, "linked_pages")
        assert hasattr(page, "review_status")
        assert hasattr(page, "page_version")
        assert hasattr(page, "updated_at")


def test_bootstrap_page_types(parsed_dir_with_docs):
    with patch("wiki.builders.bootstrap.PARSED_DIR", parsed_dir_with_docs), \
         patch("wiki.builders.bootstrap.save_page"):
        from wiki.builders.bootstrap import bootstrap_pages, PAGE_BLUEPRINTS

        pages = bootstrap_pages(use_llm=False)
        page_types = {p.page_type for p in pages}
        assert page_types.issubset({"policy", "concept", "process", "role"})


def test_bootstrap_default_pages_exist():
    from wiki.builders.bootstrap import PAGE_BLUEPRINTS

    expected_ids = {
        "医疗器械生产质量管理规范",
        "质量管理体系",
        "风险管理",
        "机构与人员职责",
        "文件和数据管理",
        "设备管理",
        "采购与原材料管理",
        "产品放行",
    }
    actual_ids = {bp["page_id"] for bp in PAGE_BLUEPRINTS}
    assert expected_ids == actual_ids


def test_bootstrap_matches_fragments_by_section_title(tmp_dir):
    parsed_dir = tmp_dir / "parsed"
    parsed_dir.mkdir()
    (parsed_dir / "doc-section.json").write_text(
        json.dumps(
            {
                "document": {
                    "document_id": "doc-section",
                    "title": "医疗器械生产质量管理规范",
                    "source_path": "Raw/policy.docx",
                    "file_name": "policy.docx",
                    "source_type": "docx",
                    "doc_type": "policy",
                    "language": "zh-CN",
                    "checksum": "section-test",
                    "metadata": {},
                },
                "sections": [
                    {
                        "section_id": "sec-1",
                        "title": "第五章设备",
                        "level": 1,
                        "page_range": [],
                        "parent_id": None,
                    }
                ],
                "fragments": [
                    {
                        "fragment_id": "frag-1",
                        "section_id": "sec-1",
                        "fragment_type": "paragraph",
                        "text": "第三十七条企业应当建立主要档案，并保留相关记录。",
                        "anchors": {"paragraph_index": 1},
                    }
                ],
                "tables": [],
                "figures": [],
                "terms": ["设备管理"],
                "entities": [],
                "parse_status": "parsed",
                "source_anchors": [{"fragment_id": "frag-1", "anchors": {"paragraph_index": 1}}],
                "errors": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    with patch("wiki.builders.bootstrap.PARSED_DIR", parsed_dir), \
         patch("wiki.builders.bootstrap.save_page"):
        from wiki.builders.bootstrap import bootstrap_pages

        pages = bootstrap_pages(use_llm=False)

    equipment_page = next(page for page in pages if page.page_id == "设备管理")
    assert len(equipment_page.source_refs) >= 1


def test_bootstrap_filters_pdf_header_and_catalog_noise():
    from wiki.builders.bootstrap import _is_noise_fragment

    assert _is_noise_fragment("2026/4/7 38 文件和数据管理（“规范”") is True
    assert _is_noise_fragment("第六章 文件和数据管理") is True
    assert _is_noise_fragment("第44条） 文件和数据管理 （总5条）") is True
    assert _is_noise_fragment("第45条 企业应当建立文件控制程序，并保存电子记录。") is False


def test_bootstrap_skips_failed_parsed_documents(tmp_dir):
    parsed_dir = tmp_dir / "parsed"
    parsed_dir.mkdir()
    (parsed_dir / "doc-failed.json").write_text(
        json.dumps(
            {
                "document": {
                    "document_id": "doc-failed",
                    "title": "临时文件",
                    "source_path": "Raw/~$draft.docx",
                    "file_name": "~$draft.docx",
                    "source_type": "docx",
                    "doc_type": "general",
                    "language": "zh-CN",
                    "checksum": "failed-test",
                    "metadata": {},
                },
                "sections": [],
                "fragments": [],
                "tables": [],
                "figures": [],
                "terms": [],
                "entities": [],
                "parse_status": "failed",
                "source_anchors": [],
                "errors": ["locked"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    with patch("wiki.builders.bootstrap.PARSED_DIR", parsed_dir):
        from wiki.builders.bootstrap import _load_parsed_documents

        docs = _load_parsed_documents()

    assert docs == []

