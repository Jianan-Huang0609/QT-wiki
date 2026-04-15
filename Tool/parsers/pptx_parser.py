from __future__ import annotations

import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from Tool.contracts.canonical import CanonicalDocument, DocumentMeta, Fragment, Section
from Tool.normalizers import detect_doc_type, extract_terms, normalize_text


def parse_pptx(file_path: Path, manifest: dict) -> CanonicalDocument:
    with zipfile.ZipFile(file_path) as archive:
        slide_names = sorted(
            name
            for name in archive.namelist()
            if name.startswith("ppt/slides/slide") and name.endswith(".xml")
        )
        if not slide_names:
            raise ValueError("No slide XML found in PPTX.")

        sections: list[Section] = []
        fragments: list[Fragment] = []

        for slide_number, slide_name in enumerate(slide_names, start=1):
            root = ET.fromstring(archive.read(slide_name))
            texts = [
                normalize_text(node.text or "")
                for node in root.iter()
                if node.tag.endswith("}t") and normalize_text(node.text or "")
            ]
            if not texts:
                continue

            title = texts[0]
            section_id = f"sec-{slide_number}"
            sections.append(Section(section_id=section_id, title=title, level=1, page_range=[slide_number, slide_number]))
            for index, text in enumerate(texts, start=1):
                fragments.append(
                    Fragment(
                        fragment_id=f"frag-{slide_number}-{index}",
                        section_id=section_id,
                        fragment_type="paragraph",
                        text=text,
                        anchors={"page": slide_number, "paragraph_index": index},
                    )
                )

    title = sections[0].title if sections else file_path.stem
    meta = DocumentMeta(
        document_id=manifest["document_id"],
        title=title,
        source_path=manifest["stored_path"],
        file_name=file_path.name,
        source_type="pptx",
        doc_type=detect_doc_type(title, file_path.name),
        checksum=manifest.get("checksum", ""),
        metadata={"manifest_path": manifest.get("manifest_path", ""), "slide_count": len(sections)},
    )

    return CanonicalDocument(
        document=meta,
        sections=sections,
        fragments=fragments,
        tables=[],
        figures=[],
        terms=extract_terms([fragment.text for fragment in fragments]),
        entities=[],
        parse_status="parsed" if fragments else "failed",
        source_anchors=[
            {"fragment_id": fragment.fragment_id, "anchors": fragment.anchors}
            for fragment in fragments
        ],
        errors=[] if fragments else ["No text fragments extracted from PPTX."],
    )
