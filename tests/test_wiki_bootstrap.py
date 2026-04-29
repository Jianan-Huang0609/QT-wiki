from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from wiki.models.page import UpdateProposal


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
        from wiki.builders.bootstrap import bootstrap_pages

        pages = bootstrap_pages(use_llm=False)
        page_types = {p.page_type for p in pages}
        assert page_types.issubset({"policy", "concept", "process", "role"})


def test_bootstrap_discovers_topics_from_section_titles(tmp_dir):
    parsed_dir = tmp_dir / "parsed"
    parsed_dir.mkdir()
    (parsed_dir / "doc-section.json").write_text(
        json.dumps(
            {
                "document": {
                    "document_id": "doc-section",
                    "title": "质量管理规范",
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
                        "title": "第五章 设备管理",
                        "level": 1,
                        "page_range": [],
                        "parent_id": None,
                    },
                    {
                        "section_id": "sec-2",
                        "title": "第六章 文件和数据管理",
                        "level": 1,
                        "page_range": [],
                        "parent_id": None,
                    },
                ],
                "fragments": [
                    {
                        "fragment_id": "frag-1",
                        "section_id": "sec-1",
                        "fragment_type": "paragraph",
                        "text": "企业应当建立设备台账、维护计划和校准记录。",
                        "anchors": {"paragraph_index": 1},
                    },
                    {
                        "fragment_id": "frag-2",
                        "section_id": "sec-2",
                        "fragment_type": "paragraph",
                        "text": "企业应当建立文件控制程序，并保存电子记录。",
                        "anchors": {"paragraph_index": 2},
                    },
                ],
                "tables": [],
                "figures": [],
                "terms": ["设备管理", "文件和数据管理"],
                "entities": [],
                "parse_status": "parsed",
                "source_anchors": [],
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

    page_ids = {page.page_id for page in pages}
    assert "设备管理" in page_ids
    assert "文件和数据管理" in page_ids


def test_bootstrap_llm_discovery_returns_dynamic_topics(tmp_dir):
    parsed_dir = tmp_dir / "parsed"
    parsed_dir.mkdir()
    (parsed_dir / "doc-llm.json").write_text(
        json.dumps(
            {
                "document": {
                    "document_id": "doc-llm",
                    "title": "产品放行培训材料",
                    "source_path": "Raw/training.pdf",
                    "file_name": "training.pdf",
                    "source_type": "pdf",
                    "doc_type": "guidance",
                    "language": "zh-CN",
                    "checksum": "llm-test",
                    "metadata": {},
                },
                "sections": [
                    {
                        "section_id": "sec-1",
                        "title": "产品放行",
                        "level": 1,
                        "page_range": [1],
                        "parent_id": None,
                    }
                ],
                "fragments": [
                    {
                        "fragment_id": "frag-1",
                        "section_id": "sec-1",
                        "fragment_type": "paragraph",
                        "text": "放行审核人应当确认检验记录和偏差处置结果。",
                        "anchors": {"page": 1, "paragraph_index": 1},
                    }
                ],
                "tables": [],
                "figures": [],
                "terms": ["产品放行", "放行审核人"],
                "entities": [],
                "parse_status": "parsed",
                "source_anchors": [],
                "errors": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    llm_payload = json.dumps(
        {
            "pages": [
                {
                    "title": "产品放行",
                    "page_type": "process",
                    "aliases": ["放行审核"],
                    "keywords": ["产品放行", "放行审核人"],
                    "section_keywords": ["产品放行"],
                    "related_titles": [],
                }
            ]
        },
        ensure_ascii=False,
    )

    with patch("wiki.builders.bootstrap.PARSED_DIR", parsed_dir), \
         patch("wiki.builders.bootstrap.ask_llm", return_value=llm_payload), \
         patch("wiki.builders.bootstrap.save_page"):
        from wiki.builders.bootstrap import build_page_candidates

        candidates = build_page_candidates(use_llm=True)

    assert len(candidates) >= 1
    assert any(c.page.page_id == "产品放行" for c in candidates)
    assert any("wiki.builders.bootstrap._llm_discover_page_blueprints" in c.tool_trace for c in candidates)


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
