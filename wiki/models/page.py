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


@dataclass(slots=True)
class DocumentIdentity:
    business_type: str
    title: str
    version: str = ""
    effective_level: str = ""
    scope: str = ""
    is_binding: bool = False
    confidence: float = 0.0
    source_refs: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ReviewObject:
    object_id: str
    object_type: str
    name: str
    evidence_refs: list[dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.0
    review_risk: str = "medium"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ReviewRelation:
    relation_id: str
    relation_type: str
    from_object_id: str
    to_object_id: str
    claim_type: str
    direction: str = "forward"
    evidence_refs: list[dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.0
    human_required: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ReviewIssue:
    issue_id: str
    issue_type: str
    detail: str
    severity: str = "medium"
    evidence_refs: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class HumanReviewQuestion:
    question_id: str
    question: str
    rationale: str
    target: str = ""
    evidence_refs: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ReviewPackage:
    package_id: str
    document_id: str
    status: str
    document_identity: DocumentIdentity
    identity_decision: str = "pending"
    confirmed_business_type: str = ""
    confirmed_effective_level: str = ""
    confirmed_is_binding: bool | None = None
    review_notes: str = ""
    reviewed_at: str = ""
    reviewed_by: str = ""
    relation_decision: str = "pending"
    relation_review_notes: str = ""
    relation_reviewed_at: str = ""
    relation_reviewed_by: str = ""
    evidence_refs: list[dict[str, Any]] = field(default_factory=list)
    extracted_objects: list[ReviewObject] = field(default_factory=list)
    extracted_relations: list[ReviewRelation] = field(default_factory=list)
    issues: list[ReviewIssue] = field(default_factory=list)
    human_questions: list[HumanReviewQuestion] = field(default_factory=list)
    candidate_page_titles: list[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    tool_trace: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
