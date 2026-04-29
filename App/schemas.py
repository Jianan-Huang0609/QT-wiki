from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class DecisionType(str, Enum):
    """审批决策类型"""
    CONFIRMED = "confirmed"
    NEEDS_REVISION = "needs_revision"


class RelationDecisionType(str, Enum):
    """关系审批决策类型"""
    CONFIRMED = "confirmed"
    NEEDS_REVISION = "needs_revision"


class BusinessType(str, Enum):
    """业务类型"""
    REGULATION = "regulation"
    POLICY = "policy"
    GUIDELINE = "guideline"
    EXTERNAL_REFERENCE = "external_reference"
    TEMPLATE = "template"


class EffectiveLevel(str, Enum):
    """效力级别"""
    BINDING = "binding"
    RECOMMENDED = "recommended"
    REFERENCE_ONLY = "reference_only"


class PageType(str, Enum):
    """Wiki 页面类型"""
    OVERVIEW = "overview"
    ENTITY = "entity"
    CONCEPT = "concept"
    COMPARISON = "comparison"
    INDEX = "index"


class ReviewStatus(str, Enum):
    """审核状态"""
    GENERATED = "generated"
    PENDING_REVIEW = "pending_review"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class SeverityLevel(str, Enum):
    """问题严重程度"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SourceRef(BaseModel):
    """来源引用"""
    document_id: str = Field(..., min_length=1, description="文档ID")
    fragment_id: str | None = Field(None, description="片段ID")
    file_name: str | None = Field(None, description="文件名")
    anchor_label: str | None = Field(None, description="锚点标签")
    quote: str | None = Field(None, max_length=2000, description="引用内容")

    @field_validator("document_id")
    @classmethod
    def validate_document_id(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("document_id 不能为空")
        return v.strip()


class ReviewPackageDecisionRequest(BaseModel):
    """审批包决策请求"""
    identity_decision: DecisionType = Field(..., description="身份审批决策")
    confirmed_business_type: str | None = Field(None, description="确认的业务类型")
    confirmed_effective_level: str | None = Field(None, description="确认的效力级别")
    confirmed_is_binding: bool = Field(False, description="是否为强制性")
    review_notes: str = Field(default="", max_length=2000, description="审批备注")
    reviewed_by: str = Field(default="", max_length=100, description="审批人")

    @field_validator("confirmed_business_type")
    @classmethod
    def validate_business_type_on_confirm(cls, v: str | None, info: Any) -> str | None:
        values = info.data
        if values.get("identity_decision") == DecisionType.CONFIRMED and not v:
            raise ValueError("确认决策时，confirmed_business_type 必填")
        return v

    @field_validator("review_notes")
    @classmethod
    def validate_review_notes(cls, v: str) -> str:
        return v.strip()

    @field_validator("reviewed_by")
    @classmethod
    def validate_reviewed_by(cls, v: str) -> str:
        return v.strip()


class ReviewPackageRelationDecisionRequest(BaseModel):
    """审批包关系决策请求"""
    relation_decision: RelationDecisionType = Field(..., description="关系审批决策")
    relation_review_notes: str = Field(default="", max_length=2000, description="关系审批备注")
    relation_reviewed_by: str = Field(default="", max_length=100, description="关系审批人")

    @field_validator("relation_review_notes")
    @classmethod
    def validate_notes(cls, v: str) -> str:
        return v.strip()

    @field_validator("relation_reviewed_by")
    @classmethod
    def validate_reviewer(cls, v: str) -> str:
        return v.strip()


class ChatQueryRequest(BaseModel):
    """聊天查询请求"""
    question: str = Field(..., min_length=1, max_length=500, description="问题内容")
    use_llm: bool = Field(default=False, description="是否使用LLM")
    top_k_pages: int = Field(default=5, ge=1, le=20, description="返回页面数量")
    top_k_citations: int = Field(default=8, ge=1, le=50, description="返回引用数量")

    @field_validator("question")
    @classmethod
    def validate_question(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 2:
            raise ValueError("问题至少需要2个字符")
        return v


class AgentUploadResponse(BaseModel):
    """Agent上传响应"""
    run_id: str = Field(..., description="运行ID")
    document_id: str | None = Field(None, description="文档ID")
    file_name: str | None = Field(None, description="文件名")
    documents_parsed: int = Field(default=0, ge=0, description="解析文档数")
    proposals_created: int = Field(default=0, ge=0, description="创建提案数")
    pending: int = Field(default=0, ge=0, description="待处理数")
    pending_review_count: int = Field(default=0, ge=0, description="待审核数")
    review_package_id: str | None = Field(None, description="本次审批包ID")
    candidate_ids: list[str] = Field(default_factory=list, description="本次生成的候选页ID")
    workflow_engine: str = Field(default="IngestAgent", description="工作流引擎")


class DashboardResponse(BaseModel):
    """仪表板响应"""
    agents: list[dict[str, Any]] = Field(default_factory=list)
    index: dict[str, Any] = Field(default_factory=dict)
    pages: list[dict[str, Any]] = Field(default_factory=list)
    issues: list[dict[str, Any]] = Field(default_factory=list)


class HealthResponse(BaseModel):
    """健康检查响应"""
    status: Literal["ok", "error", "degraded"] = Field(default="ok")


class PageSectionSchema(BaseModel):
    """页面章节模式"""
    heading: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., max_length=50000)
    source_refs: list[SourceRef] = Field(default_factory=list)


class WikiPageSchema(BaseModel):
    """Wiki页面模式"""
    page_id: str = Field(..., min_length=1, max_length=100, pattern=r"^[\w\-\u4e00-\u9fa5]+$")
    title: str = Field(..., min_length=1, max_length=200)
    page_type: PageType = Field(..., description="页面类型")
    summary: str = Field(..., max_length=2000)
    sections: list[PageSectionSchema] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    source_refs: list[SourceRef] = Field(default_factory=list)
    linked_pages: list[str] = Field(default_factory=list)
    review_status: ReviewStatus = Field(default=ReviewStatus.GENERATED)
    page_version: int = Field(default=1, ge=1)
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())

    @field_validator("aliases")
    @classmethod
    def validate_aliases(cls, v: list[str]) -> list[str]:
        return [alias.strip() for alias in v if alias.strip()]

    @field_validator("linked_pages")
    @classmethod
    def validate_linked_pages(cls, v: list[str]) -> list[str]:
        return [page.strip() for page in v if page.strip()]


class CandidatePayload(BaseModel):
    """候选负载"""
    candidate_id: str = Field(..., min_length=1)
    document_ids: list[str] = Field(default_factory=list)
    page_type: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1, max_length=200)
    status: str = Field(...)
    confidence: float = Field(..., ge=0.0, le=1.0)
    summary: str = Field(default="", max_length=2000)
    keywords: list[str] = Field(default_factory=list)
    related_titles: list[str] = Field(default_factory=list)
    source_refs: list[dict[str, Any]] = Field(default_factory=list)


class ReviewPackagePayload(BaseModel):
    """审批包负载"""
    package_id: str = Field(..., min_length=1)
    document_id: str = Field(..., min_length=1)
    status: str = Field(...)
    identity_decision: str = Field(default="pending")
    title: str = Field(..., min_length=1)
    business_type: str = Field(default="")
    effective_level: str = Field(default="")
    version: str = Field(default="")
    scope: str = Field(default="")
    is_binding: bool = Field(default=False)
    confidence: float = Field(..., ge=0.0, le=1.0)
    notes: list[str] = Field(default_factory=list)
    confirmed_business_type: str | None = Field(None)
    confirmed_effective_level: str | None = Field(None)
    confirmed_is_binding: bool | None = Field(None)
    review_notes: str = Field(default="")
    reviewed_at: str = Field(default="")
    reviewed_by: str = Field(default="")
    relation_decision: str = Field(default="pending")
    relation_review_notes: str = Field(default="")
    relation_reviewed_at: str = Field(default="")
    relation_reviewed_by: str = Field(default="")
    source_refs: list[dict[str, Any]] = Field(default_factory=list)
    issues: list[dict[str, Any]] = Field(default_factory=list)
    human_questions: list[dict[str, Any]] = Field(default_factory=list)
    extracted_objects: list[dict[str, Any]] = Field(default_factory=list)
    extracted_relations: list[dict[str, Any]] = Field(default_factory=list)
    candidate_page_titles: list[str] = Field(default_factory=list)
    tool_trace: list[str] = Field(default_factory=list)


class LintIssuePayload(BaseModel):
    """Lint问题负载"""
    issue_id: str = Field(..., min_length=1)
    type: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1, max_length=100)
    target: str = Field(default="")
    severity: SeverityLevel = Field(default=SeverityLevel.MEDIUM)
    detail: str = Field(default="", max_length=2000)
    suggestion: str = Field(default="", max_length=1000)
    status: str = Field(default="open")


class CitationPayload(BaseModel):
    """引用负载"""
    citation_id: str = Field(..., min_length=1)
    page_title: str = Field(..., min_length=1)
    file_name: str = Field(..., min_length=1)
    anchor_label: str = Field(default="source")
    quote: str = Field(default="", max_length=2000)
    document_id: str = Field(..., min_length=1)
    fragment_id: str | None = Field(None)


class ChatQueryResponse(BaseModel):
    """聊天查询响应"""
    answer: str = Field(..., max_length=10000)
    confidence: str = Field(..., pattern=r"^(high|medium|low)$")
    used_llm: bool = Field(...)
    matched_pages: list[dict[str, Any]] = Field(default_factory=list)
    citations: list[CitationPayload] = Field(default_factory=list)
    structured_matches: list[dict[str, Any]] = Field(default_factory=list)
    trace: list[str] = Field(default_factory=list)
