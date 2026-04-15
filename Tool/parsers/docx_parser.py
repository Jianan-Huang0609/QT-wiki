from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from Tool.contracts.canonical import CanonicalDocument, DocumentMeta, Fragment, Section, TableData
from Tool.normalizers import detect_doc_type, extract_terms, normalize_text

NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
SECTION_RE = re.compile(r"^第[一二三四五六七八九十百零〇\d]+章")


def parse_docx(file_path: Path, manifest: dict) -> CanonicalDocument:
    with zipfile.ZipFile(file_path) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))

    sections: list[Section] = []
    fragments: list[Fragment] = []
    tables: list[TableData] = []
    current_section_id: str | None = None
    section_index = 0
    paragraph_index = 0
    table_index = 0

    body = root.find("w:body", NS)
    if body is None:
        raise ValueError("DOCX body not found")

    for child in body:
        if child.tag.endswith("}p"):
            text = _paragraph_text(child)
            if not text:
                continue
            paragraph_index += 1
            if SECTION_RE.match(text):
                section_index += 1
                current_section_id = f"sec-{section_index}"
                sections.append(
                    Section(
                        section_id=current_section_id,
                        title=text,
                        level=1,
                        page_range=[],
                    )
                )
            fragments.append(
                Fragment(
                    fragment_id=f"frag-{paragraph_index}",
                    section_id=current_section_id,
                    fragment_type="paragraph",
                    text=text,
                    anchors={"paragraph_index": paragraph_index},
                )
            )
        elif child.tag.endswith("}tbl"):
            rows = _table_rows(child)
            if not rows:
                continue
            table_index += 1
            tables.append(
                TableData(
                    table_id=f"tbl-{table_index}",
                    section_id=current_section_id,
                    page=None,
                    rows=rows,
                    anchors={"table_index": table_index},
                )
            )

    title = _pick_title(fragments, file_path.stem)
    meta = DocumentMeta(
        document_id=manifest["document_id"],
        title=title,
        source_path=manifest["stored_path"],
        file_name=file_path.name,
        source_type="docx",
        doc_type=detect_doc_type(title, file_path.name),
        checksum=manifest.get("checksum", ""),
        metadata={"manifest_path": manifest.get("manifest_path", "")},
    )

    source_anchors = [
        {"fragment_id": fragment.fragment_id, "anchors": fragment.anchors}
        for fragment in fragments
    ]

    parse_status = "parsed" if fragments else "failed"
    errors = [] if fragments else ["No text fragments extracted from DOCX."]
    return CanonicalDocument(
        document=meta,
        sections=sections,
        fragments=fragments,
        tables=tables,
        figures=[],
        terms=extract_terms([fragment.text for fragment in fragments]),
        entities=[],
        parse_status=parse_status,
        source_anchors=source_anchors,
        errors=errors,
    )


def _paragraph_text(paragraph: ET.Element) -> str:
    texts = [
        normalize_text(node.text or "")
        for node in paragraph.findall(".//w:t", NS)
        if normalize_text(node.text or "")
    ]
    return normalize_text("".join(texts))


def _table_rows(table: ET.Element) -> list[list[str]]:
    rows: list[list[str]] = []
    for row in table.findall("w:tr", NS):
        cells = []
        for cell in row.findall("w:tc", NS):
            text = normalize_text(" ".join(_paragraph_text(p) for p in cell.findall(".//w:p", NS)))
            cells.append(text)
        if any(cells):
            rows.append(cells)
    return rows


def _pick_title(fragments: list[Fragment], fallback: str) -> str:
    for fragment in fragments[:8]:
        text = fragment.text
        if text and len(text) >= 6 and text != "附件":
            return text
    return fallback
