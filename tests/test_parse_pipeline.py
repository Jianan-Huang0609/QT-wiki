from __future__ import annotations

import json
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch
from xml.etree.ElementTree import Element, SubElement, tostring

import pytest

from Tool.contracts.canonical import (
    CanonicalDocument,
    DocumentMeta,
    Fragment,
    Section,
    load_canonical_document,
)
from Tool.parsers import parse_document

NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _make_docx_zip(tmp_dir: Path, paragraphs: list[str], tables: list[list[list[str]]] | None = None) -> Path:
    doc_path = tmp_dir / "test.docx"

    body = Element(f"{{{NS}}}body")
    for para_text in paragraphs:
        p = SubElement(body, f"{{{NS}}}p")
        r = SubElement(p, f"{{{NS}}}r")
        t = SubElement(r, f"{{{NS}}}t")
        t.text = para_text

    if tables:
        for table_rows in tables:
            tbl = SubElement(body, f"{{{NS}}}tbl")
            for row_cells in table_rows:
                tr = SubElement(tbl, f"{{{NS}}}tr")
                for cell_text in row_cells:
                    tc = SubElement(tr, f"{{{NS}}}tc")
                    p = SubElement(tc, f"{{{NS}}}p")
                    r = SubElement(p, f"{{{NS}}}r")
                    t = SubElement(r, f"{{{NS}}}t")
                    t.text = cell_text

    doc_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        + tostring(body, encoding="unicode")
        + "</w:document>"
    )

    with zipfile.ZipFile(doc_path, "w") as zf:
        zf.writestr("word/document.xml", doc_xml)

    return doc_path


def test_docx_extracts_sections_and_fragments(tmp_dir, sample_manifest):
    paragraphs = [
        "医疗器械生产质量管理规范",
        "第一章 总则",
        "企业应当建立质量管理体系并保持其有效性。",
        "风险管理应当贯穿产品全生命周期。",
    ]
    docx_path = _make_docx_zip(tmp_dir, paragraphs)
    sample_manifest["stored_path"] = str(docx_path)

    result = parse_document(docx_path, sample_manifest)

    assert result.parse_status == "parsed"
    assert len(result.sections) >= 1
    assert any("总则" in s.title for s in result.sections)
    assert len(result.fragments) >= 2
    assert any("质量管理体系" in f.text for f in result.fragments)


def test_docx_extracts_tables(tmp_dir, sample_manifest):
    paragraphs = ["测试文档"]
    tables = [[["列A", "列B"], ["值1", "值2"]]]
    docx_path = _make_docx_zip(tmp_dir, paragraphs, tables)
    sample_manifest["stored_path"] = str(docx_path)

    result = parse_document(docx_path, sample_manifest)

    assert result.parse_status == "parsed"
    assert len(result.tables) >= 1
    assert result.tables[0].rows[0] == ["列A", "列B"]


def test_docx_fragments_have_paragraph_index(tmp_dir, sample_manifest):
    paragraphs = ["第一章 总则", "企业应当建立质量管理体系。"]
    docx_path = _make_docx_zip(tmp_dir, paragraphs)
    sample_manifest["stored_path"] = str(docx_path)

    result = parse_document(docx_path, sample_manifest)

    for fragment in result.fragments:
        assert "paragraph_index" in fragment.anchors


def test_pdf_extracts_page_level_fragments(tmp_dir, sample_manifest):
    from Tool.parsers.pdf_parser import parse_pdf

    mock_reader = MagicMock()
    mock_page = MagicMock()
    mock_page.extract_text.return_value = "第一章 总则\n企业应当建立质量管理体系。"
    mock_reader.pages = [mock_page]

    with patch("Tool.parsers.pdf_parser.pypdf.PdfReader", return_value=mock_reader):
        result = parse_pdf(tmp_dir / "test.pdf", sample_manifest)

    assert result.parse_status in ("parsed", "partially_parsed")
    assert len(result.fragments) >= 1
    for fragment in result.fragments:
        assert "page" in fragment.anchors


def test_pdf_splits_long_page_into_multiple_fragments(tmp_dir, sample_manifest):
    from Tool.parsers.pdf_parser import parse_pdf

    mock_reader = MagicMock()
    mock_page = MagicMock()
    mock_page.extract_text.return_value = (
        "2026/4/7 14 “规范”框架结构 第五章设备 第三十六条企业应当配备适宜资源。"
        "第三十七条企业应当建立档案。第六章文件和数据管理 第四十二条企业应当建立文件控制程序。"
    )
    mock_reader.pages = [mock_page]

    with patch("Tool.parsers.pdf_parser.pypdf.PdfReader", return_value=mock_reader):
        result = parse_pdf(tmp_dir / "test.pdf", sample_manifest)

    assert result.parse_status in ("parsed", "partially_parsed")
    assert len(result.fragments) >= 3
    assert any("第五章设备" in fragment.text for fragment in result.fragments)
    assert any(fragment.section_id for fragment in result.fragments)


def test_pdf_detects_slide_like_pdf_and_skips_structural_pages(tmp_dir, sample_manifest):
    from Tool.parsers.pdf_parser import parse_pdf

    sample_manifest["title"] = "新版《医疗器械生产质量管理规范》的理解和实施（最新）"
    mock_reader = MagicMock()
    page_intro = MagicMock()
    page_intro.extract_text.return_value = (
        "2026/4/7\n1\n分享人：张三\n医疗器械生产质量管理规范（2025版）\n—理解和实施\n教师简介"
    )
    page_toc = MagicMock()
    page_toc.extract_text.return_value = (
        "2026/4/7\n2\n目录\n01 质量管理体系基础知识\n② QMS相关标准和法规\n03 新版“规范”的理解和实施要点"
    )
    page_content = MagicMock()
    page_content.extract_text.return_value = (
        "2026/4/7\n35\n设备（“规范”第五章）\n理解要点\n"
        "第三十六条 企业应当配备与所生产产品和规模相匹配的生产设备\n"
        "并确保有效运行。\n"
        "• 设备的总要求\n"
        "• 设备维护和维修\n"
        "第三十八条 企业应当建立主要设备和仪器的使用、维护和维修操作规程"
    )
    mock_reader.pages = [page_intro, page_toc, page_content]

    with patch("Tool.parsers.pdf_parser.pypdf.PdfReader", return_value=mock_reader), \
         patch("Tool.parsers.pdf_parser._looks_like_slide_pdf", return_value=True):
        result = parse_pdf(tmp_dir / "deck.pdf", sample_manifest)

    assert result.parse_status in ("parsed", "partially_parsed")
    assert result.document.doc_type == "presentation"
    assert result.document.metadata.get("pdf_layout") == "slides"
    assert result.document.metadata.get("skipped_pages") == [1, 2]
    assert len(result.sections) == 1
    assert "设备" in result.sections[0].title
    assert len(result.fragments) >= 1
    assert all("目录" not in fragment.text and "分享人" not in fragment.text for fragment in result.fragments)


def test_slide_title_picker_prefers_page_theme_over_body_sentence():
    from Tool.parsers.pdf_parser import _pick_slide_page_title

    title, source = _pick_slide_page_title(
        [
            "⚫ 当前医疗器械监管形式",
            "——监管目的性越来越强（重点是合规性和产品质量）",
            "——监管能力和水平越来越高",
        ],
        fallback="第5页",
    )

    assert title == "当前医疗器械监管形式"
    assert source == "⚫ 当前医疗器械监管形式"


def test_slide_title_picker_prefers_short_heading_over_following_detail():
    from Tool.parsers.pdf_parser import _pick_slide_page_title

    title, _ = _pick_slide_page_title(
        [
            "可视化的证据",
            "检查是为了判断符合性",
            "— QA/审批人进行事后/放行前审查",
        ],
        fallback="第12页",
    )

    assert title == "可视化的证据"


def test_slide_title_picker_prefers_thematic_heading_over_noise_and_body_sentence():
    from Tool.parsers.pdf_parser import _pick_slide_page_title

    title, _ = _pick_slide_page_title(
        [
            "下面引自ISO13485",
            "4.1.4 过程的管理和更改控制",
            "4.1.4 组织应按照本标准要求和适用的法规要求管理这些质量管理体系过程。",
        ],
        fallback="第10页",
    )

    assert title == "过程的管理和更改控制"


def test_slide_title_picker_prefers_page_topic_over_generic_clause_label():
    from Tool.parsers.pdf_parser import _pick_slide_page_title

    title, _ = _pick_slide_page_title(
        [
            "（1）总则：",
            "• 将ISO13485、GMP及其他相关法规的要求融入本公司的QMS文件中。",
            "3. QMS文件的编写（plan）",
        ],
        fallback="第11页",
    )

    assert title == "QMS文件的编写"


def test_slide_title_picker_prefers_timeline_topic_over_generic_new_version_label():
    from Tool.parsers.pdf_parser import _pick_slide_page_title

    title, _ = _pick_slide_page_title(
        [
            "新版“规范”",
            "理解和实施",
            "2009年 医疗器械生产质量管理规范（试行）(第一版)",
            "“规范”发展历程",
        ],
        fallback="第13页",
    )

    assert title == "“规范”发展历程"


def test_parse_failure_returns_failed_status(tmp_dir, sample_manifest):
    unsupported_file = tmp_dir / "test.unsupported"
    unsupported_file.write_text("dummy", encoding="utf-8")
    sample_manifest["stored_path"] = str(unsupported_file)

    result = parse_document(unsupported_file, sample_manifest)

    assert result.parse_status == "failed"
    assert len(result.errors) > 0


def test_canonical_document_save_and_load(tmp_dir, sample_canonical_dict):
    doc = CanonicalDocument(
        document=DocumentMeta(**sample_canonical_dict["document"]),
        sections=[Section(**s) for s in sample_canonical_dict["sections"]],
        fragments=[Fragment(**f) for f in sample_canonical_dict["fragments"]],
        parse_status=sample_canonical_dict["parse_status"],
    )
    save_path = tmp_dir / "canonical.json"
    doc.save(save_path)

    loaded = load_canonical_document(save_path)
    assert loaded.document.document_id == "doc-test-0001-abcd1234"
    assert len(loaded.fragments) == 2
    assert loaded.parse_status == "parsed"


def test_canonical_document_to_dict(sample_canonical_dict):
    doc = CanonicalDocument(
        document=DocumentMeta(**sample_canonical_dict["document"]),
        sections=[Section(**s) for s in sample_canonical_dict["sections"]],
        fragments=[Fragment(**f) for f in sample_canonical_dict["fragments"]],
        parse_status=sample_canonical_dict["parse_status"],
    )
    d = doc.to_dict()
    assert d["document"]["document_id"] == "doc-test-0001-abcd1234"
    assert len(d["fragments"]) == 2
