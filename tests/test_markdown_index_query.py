from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from wiki.models.page import PageSection, WikiPage


def _sample_page() -> WikiPage:
    ref = {
        "document_id": "doc-test-0001",
        "fragment_id": "frag-1",
        "file_name": "policy.pdf",
        "anchor_label": "p.1",
        "quote": "企业应当建立质量管理体系并保持其有效性。",
    }
    return WikiPage(
        page_id="质量管理体系",
        title="质量管理体系",
        page_type="concept",
        summary="质量管理体系是企业确保产品符合法规要求的核心框架。",
        sections=[PageSection(heading="关键依据", content="企业应当建立质量管理体系。", source_refs=[ref])],
        aliases=["QMS"],
        source_refs=[ref],
        linked_pages=["风险管理"],
        review_status="published",
        page_version=1,
        updated_at="2026-04-27T10:00:00",
    )


def test_save_page_writes_json_and_obsidian_markdown(tmp_dir):
    from wiki.store import files

    pages_dir = tmp_dir / "pages"
    with patch.object(files, "PAGE_DIR", pages_dir):
        files.save_page(_sample_page())

    json_path = pages_dir / "质量管理体系.json"
    markdown_path = tmp_dir / "obsidian" / "Pages" / "质量管理体系.md"

    assert json_path.exists()
    assert markdown_path.exists()

    content = markdown_path.read_text(encoding="utf-8")
    assert 'page_id: "质量管理体系"' in content
    assert "## 引用来源" in content
    assert "doc-test-0001 / frag-1 / p.1 / policy.pdf" in content


def test_build_index_outputs_machine_indexes(tmp_dir):
    from wiki.indexing import build_index

    paths = build_index(pages=[_sample_page()], index_dir=tmp_dir / "index")

    page_lines = paths["pages"].read_text(encoding="utf-8").splitlines()
    page_entry = json.loads(page_lines[0])
    terms = json.loads(paths["terms"].read_text(encoding="utf-8"))
    links = json.loads(paths["links"].read_text(encoding="utf-8"))
    source_lines = paths["sources"].read_text(encoding="utf-8").splitlines()

    assert page_entry["page_id"] == "质量管理体系"
    assert page_entry["source_count"] == 1
    assert terms["QMS"] == ["质量管理体系"]
    assert links["质量管理体系"] == ["风险管理"]
    assert json.loads(source_lines[0])["fragment_id"] == "frag-1"


def test_query_agent_uses_index_retrieval_without_full_wiki_load():
    from App.agents.query_agent import QueryAgent

    page = _sample_page()
    index_entry = {
        "page_id": page.page_id,
        "title": page.title,
        "page_type": page.page_type,
        "aliases": page.aliases,
        "summary": page.summary,
        "keywords": ["质量管理体系", "QMS"],
        "linked_pages": page.linked_pages,
        "source_count": 1,
        "updated_at": page.updated_at,
        "review_status": page.review_status,
    }

    with patch("App.agents.query_agent.load_page_index", return_value=[index_entry]), \
         patch("App.agents.query_agent.load_page", return_value=page), \
         patch("App.agents.query_agent.load_all_pages", side_effect=AssertionError("不应全量加载 Wiki")):
        answer = QueryAgent().query("什么是QMS？", use_llm=False)

    assert answer.sources
    assert answer.sources[0].source_id == "质量管理体系"
    assert "质量管理体系" in answer.answer_text
