from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class DocumentMeta:
    document_id: str
    title: str
    source_path: str
    file_name: str
    source_type: str
    doc_type: str
    language: str = "zh-CN"
    checksum: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Section:
    section_id: str
    title: str
    level: int
    page_range: list[int] = field(default_factory=list)
    parent_id: str | None = None


@dataclass(slots=True)
class Fragment:
    fragment_id: str
    section_id: str | None
    fragment_type: str
    text: str
    anchors: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class TableData:
    table_id: str
    section_id: str | None
    page: int | None
    rows: list[list[str]] = field(default_factory=list)
    anchors: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class FigureData:
    figure_id: str
    section_id: str | None
    page: int | None
    caption: str = ""
    anchors: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CanonicalDocument:
    document: DocumentMeta
    sections: list[Section] = field(default_factory=list)
    fragments: list[Fragment] = field(default_factory=list)
    tables: list[TableData] = field(default_factory=list)
    figures: list[FigureData] = field(default_factory=list)
    terms: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    parse_status: str = "parsed"
    source_anchors: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def save(self, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def load_canonical_document(path: str | Path) -> CanonicalDocument:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return CanonicalDocument(
        document=DocumentMeta(**data["document"]),
        sections=[Section(**item) for item in data.get("sections", [])],
        fragments=[Fragment(**item) for item in data.get("fragments", [])],
        tables=[TableData(**item) for item in data.get("tables", [])],
        figures=[FigureData(**item) for item in data.get("figures", [])],
        terms=list(data.get("terms", [])),
        entities=list(data.get("entities", [])),
        parse_status=data.get("parse_status", "parsed"),
        source_anchors=list(data.get("source_anchors", [])),
        errors=list(data.get("errors", [])),
    )
