from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class PageSection:
    heading: str
    content: str
    source_refs: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class WikiPage:
    page_id: str
    title: str
    page_type: str
    summary: str
    sections: list[PageSection] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    source_refs: list[dict[str, Any]] = field(default_factory=list)
    linked_pages: list[str] = field(default_factory=list)
    review_status: str = "generated"
    page_version: int = 1
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PageChangeCandidate:
    page: WikiPage
    action: str
    candidate_content: str
    document_type: str = ""
    source_file_name: str = ""
    source_refs: list[dict[str, Any]] = field(default_factory=list)
    evidence_fragment_ids: list[str] = field(default_factory=list)
    source_document_ids: list[str] = field(default_factory=list)
    tool_trace: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["page"] = self.page.to_dict()
        return data


@dataclass(slots=True)
class ReviewDecision:
    risk_level: str = "medium"
    change_scope: str = "medium"
    review_mode: str = "human_required"
    auto_publish: bool = False
    reasoning: str = ""
    tool_trace: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class UpdateProposal:
    proposal_id: str
    target_page_id: str
    action: str
    reason: str
    candidate_content: str
    evidence_fragment_ids: list[str] = field(default_factory=list)
    source_refs: list[dict[str, Any]] = field(default_factory=list)
    risk_level: str = "medium"
    status: str = "pending_review"
    change_scope: str = "medium"
    review_mode: str = "human_required"
    review_notes: str = ""
    source_document_ids: list[str] = field(default_factory=list)
    tool_trace: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
