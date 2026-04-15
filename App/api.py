from __future__ import annotations

import logging
import shutil
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from App.agent import maintain_wiki
from App.chat import ChatbotService
from Tool.parsers import SUPPORTED_SUFFIXES
from wiki.store.files import PROPOSAL_DIR
from wiki.updaters.review_publish import approve_all_pending_proposals, approve_proposal

LOGGER = logging.getLogger(__name__)
APP_DIR = Path(__file__).resolve().parent
REPO_ROOT = APP_DIR.parent
RAW_DIR = REPO_ROOT / "Raw"
WEB_DIR = APP_DIR / "web"
ASSET_DIR = WEB_DIR / "assets"
INDEX_FILE = WEB_DIR / "index.html"


class ChatQueryRequest(BaseModel):
    question: str = Field(..., min_length=1, description="用户问题")
    use_llm: bool = Field(default=False, description="是否调用大语言模型生成最终回答")
    top_k_pages: int = Field(default=5, ge=1, le=10, description="页面召回数量")
    top_k_citations: int = Field(default=8, ge=1, le=20, description="证据片段召回数量")


class ChatQueryResponse(BaseModel):
    answer: str
    citations: list[dict]
    matched_pages: list[dict]
    confidence: str
    used_llm: bool
    question: str


class ReindexResponse(BaseModel):
    status: str
    pages: int
    documents: int
    fragments: int


class UploadResponse(BaseModel):
    status: str
    file_name: str
    stored_path: str
    run_id: str
    manifests_seen: int
    documents_parsed: int
    proposals_created: int
    pages_published: int
    pending_review_count: int
    workflow_engine: str


class PendingProposalItem(BaseModel):
    proposal_id: str
    target_page_id: str
    action: str
    risk_level: str = "medium"
    change_scope: str = "medium"
    review_mode: str = "human_required"
    status: str = "pending_review"
    reason: str = ""
    review_notes: str = ""
    candidate_content: str = ""
    source_document_ids: list[str] = []
    tool_trace: list[str] = []


class PendingProposalListResponse(BaseModel):
    status: str
    items: list[PendingProposalItem]


class ProposalApprovalResponse(BaseModel):
    status: str
    proposal_id: str
    target_page_id: str
    review_mode: str
    review_notes: str


class ProposalApprovalBatchResponse(BaseModel):
    status: str
    approved_count: int
    proposal_ids: list[str]


def create_app(chat_service: ChatbotService | None = None) -> FastAPI:
    service = chat_service or ChatbotService()
    app = FastAPI(title="QT Wiki Chat API", version="0.2.0")

    if ASSET_DIR.exists():
        app.mount("/assets", StaticFiles(directory=str(ASSET_DIR)), name="assets")

    @app.get("/")
    def frontend() -> FileResponse:
        return FileResponse(INDEX_FILE)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/chat/reindex", response_model=ReindexResponse)
    def reindex() -> ReindexResponse:
        LOGGER.info("收到重建聊天索引请求")
        summary = service.reindex()
        return ReindexResponse(status="ok", **summary)

    @app.post("/chat/query", response_model=ChatQueryResponse)
    def chat_query(request: ChatQueryRequest) -> ChatQueryResponse:
        LOGGER.info("收到聊天查询请求：%s", request.question)
        answer = service.answer_question(
            request.question,
            use_llm=request.use_llm,
            top_k_pages=request.top_k_pages,
            top_k_citations=request.top_k_citations,
        )
        return ChatQueryResponse(**answer.to_dict())

    @app.post("/agent/upload", response_model=UploadResponse)
    def upload_and_maintain(
        file: UploadFile = File(..., description="待上传的原始文档"),
        use_llm: bool = Form(False, description="是否启用 LLM 参与 Wiki 建库/更新摘要"),
        auto_publish_low_risk: bool = Form(True, description="是否自动发布低风险变更"),
        auto_approve_small_changes: bool = Form(True, description="是否自动推进小范围低风险改动"),
        workflow_engine: str = Form("auto", description="工作流引擎，可选 auto、langgraph、builtin"),
    ) -> UploadResponse:
        original_name = (file.filename or "").strip()
        if not original_name:
            raise HTTPException(status_code=400, detail="上传文件名不能为空")

        suffix = Path(original_name).suffix.lower()
        if suffix not in SUPPORTED_SUFFIXES:
            allowed = ", ".join(sorted(SUPPORTED_SUFFIXES))
            raise HTTPException(status_code=400, detail=f"不支持的文件类型：{suffix or '无后缀'}，仅支持：{allowed}")

        stored_file = _save_upload_file(file, RAW_DIR)
        LOGGER.info("文件上传成功：file=%s，stored=%s", original_name, stored_file)

        try:
            report = maintain_wiki(
                input_path=stored_file,
                use_llm=use_llm,
                auto_publish_low_risk=auto_publish_low_risk,
                auto_approve_small_changes=auto_approve_small_changes,
                workflow_engine=workflow_engine,
            )
            LOGGER.info("上传后自动维护完成：run_id=%s，file=%s", report.run_id, stored_file.name)
            service.reindex()
        except Exception as exc:
            LOGGER.exception("上传后自动维护失败：file=%s", stored_file)
            raise HTTPException(status_code=500, detail=f"上传成功，但自动维护失败：{exc}") from exc

        return UploadResponse(
            status="ok",
            file_name=stored_file.name,
            stored_path=stored_file.relative_to(REPO_ROOT).as_posix(),
            run_id=report.run_id,
            manifests_seen=report.manifests_seen,
            documents_parsed=len(report.documents_parsed),
            proposals_created=report.proposals_created,
            pages_published=report.pages_published,
            pending_review_count=report.pending_review_count,
            workflow_engine=report.workflow_engine,
        )

    @app.get("/agent/proposals/pending", response_model=PendingProposalListResponse)
    def list_pending_proposals() -> PendingProposalListResponse:
        LOGGER.info("收到待审核提案列表请求")
        return PendingProposalListResponse(status="ok", items=_load_pending_proposals())

    @app.post("/agent/proposals/{proposal_id}/approve", response_model=ProposalApprovalResponse)
    def approve_pending_proposal(proposal_id: str) -> ProposalApprovalResponse:
        LOGGER.info("收到提案审核通过请求：proposal_id=%s", proposal_id)
        proposal = approve_proposal(proposal_id)
        if proposal is None:
            raise HTTPException(status_code=404, detail=f"提案不存在：{proposal_id}")
        service.reindex()
        return ProposalApprovalResponse(
            status="ok",
            proposal_id=proposal.proposal_id,
            target_page_id=proposal.target_page_id,
            review_mode=proposal.review_mode,
            review_notes=proposal.review_notes,
        )

    @app.post("/agent/proposals/approve-all", response_model=ProposalApprovalBatchResponse)
    def approve_all_pending() -> ProposalApprovalBatchResponse:
        LOGGER.info("收到批量审核通过请求：approve_all_pending")
        approved = approve_all_pending_proposals()
        if approved:
            service.reindex()
        return ProposalApprovalBatchResponse(
            status="ok",
            approved_count=len(approved),
            proposal_ids=[proposal.proposal_id for proposal in approved],
        )

    return app


app = create_app()


def _save_upload_file(upload_file: UploadFile, target_dir: Path) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    safe_name = Path(upload_file.filename or "upload.bin").name
    target = target_dir / safe_name
    if target.exists():
        stamp = datetime.now().strftime("%Y%m%d%H%M%S")
        target = target_dir / f"{target.stem}_{stamp}{target.suffix}"

    with target.open("wb") as handle:
        shutil.copyfileobj(upload_file.file, handle)
    upload_file.file.close()
    return target.resolve()


def _load_pending_proposals() -> list[PendingProposalItem]:
    items: list[PendingProposalItem] = []
    if not PROPOSAL_DIR.exists():
        return items
    for path in sorted(PROPOSAL_DIR.glob("*.json")):
        payload = path.read_text(encoding="utf-8")
        data = PendingProposalItem.model_validate_json(payload)
        if data.status != "pending_review":
            continue
        items.append(data)
    return items


def main() -> None:
    import uvicorn

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s：%(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        force=True,
    )
    uvicorn.run("App.api:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()
