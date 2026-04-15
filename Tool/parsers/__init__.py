from __future__ import annotations

from pathlib import Path

from Tool.contracts.canonical import CanonicalDocument, DocumentMeta
from Tool.normalizers import detect_doc_type
from Tool.parsers.docx_parser import parse_docx
from Tool.parsers.pdf_parser import parse_pdf
from Tool.parsers.pptx_parser import parse_pptx
from Tool.parsers.xlsx_parser import parse_xlsx

SUPPORTED_SUFFIXES = {".docx", ".pdf", ".pptx", ".xlsx"}


def parse_document(file_path: str | Path, manifest: dict) -> CanonicalDocument:
    path = Path(file_path)
    suffix = path.suffix.lower()
    parser_map = {
        ".docx": parse_docx,
        ".pdf": parse_pdf,
        ".pptx": parse_pptx,
        ".xlsx": parse_xlsx,
    }
    parser = parser_map.get(suffix)
    if parser is None:
        return _failed_document(path, manifest, f"Unsupported file type: {suffix}")

    try:
        return parser(path, manifest)
    except Exception as exc:
        return _failed_document(path, manifest, str(exc))


def _failed_document(path: Path, manifest: dict, error: str) -> CanonicalDocument:
    meta = DocumentMeta(
        document_id=manifest["document_id"],
        title=manifest.get("title", path.stem),
        source_path=manifest["stored_path"],
        file_name=path.name,
        source_type=path.suffix.lower().lstrip("."),
        doc_type=detect_doc_type(manifest.get("title", path.stem), path.name),
        checksum=manifest.get("checksum", ""),
        metadata={"manifest_path": manifest.get("manifest_path", "")},
    )
    return CanonicalDocument(document=meta, parse_status="failed", errors=[error])
