from __future__ import annotations

import argparse
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from App.agent_graph import run_agent_workflow
from Tool.pipelines.common import load_manifest, purge_temporary_office_artifacts
from Tool.pipelines.ingest import ingest
from Tool.pipelines.parse import parse_one
from wiki.exporters.obsidian import sync_to_obsidian
from wiki.store.files import clear_page_output, clear_proposal_output, load_all_pages
from wiki.updaters.conflict_scan import conflict_scan

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_PATH = REPO_ROOT / "Raw"
APP_OUTPUT_DIR = REPO_ROOT / "App" / "output"
DEFAULT_STATE_PATH = APP_OUTPUT_DIR / "agent_state.json"
DEFAULT_RUN_LOG_DIR = APP_OUTPUT_DIR / "runs"
SUCCESS_PARSE_STATUSES = {"parsed", "partially_parsed"}
LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class DocumentRunResult:
    document_id: str
    file_name: str
    checksum: str
    parse_status: str
    parsed_output: str | None
    action: str
    proposals_created: int = 0
    published_immediately: int = 0
    note: str = ""


@dataclass(slots=True)
class AgentRunReport:
    run_id: str
    input_path: str
    started_at: str
    completed_at: str = ""
    manifests_seen: int = 0
    documents_parsed: list[str] = field(default_factory=list)
    documents: list[DocumentRunResult] = field(default_factory=list)
    bootstrap_performed: bool = False
    pages_created: int = 0
    proposals_created: int = 0
    conflicts_found: int = 0
    pages_published: int = 0
    pending_review_count: int = 0
    workflow_engine: str = "auto"
    obsidian_synced: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def maintain_wiki(
    *,
    input_path: str | Path = DEFAULT_INPUT_PATH,
    use_llm: bool = False,
    auto_publish_low_risk: bool = True,
    auto_approve_small_changes: bool = True,
    scan_conflicts: bool = True,
    sync_obsidian_output: bool = True,
    force_reparse: bool = False,
    force_reconcile: bool = False,
    clean_rebuild: bool = False,
    workflow_engine: str = "auto",
    state_path: str | Path = DEFAULT_STATE_PATH,
    run_log_dir: str | Path = DEFAULT_RUN_LOG_DIR,
) -> AgentRunReport:
    run_id = datetime.now().strftime("%Y%m%d%H%M%S")
    report = AgentRunReport(
        run_id=run_id,
        input_path=str(input_path),
        started_at=_now_iso(),
        workflow_engine=workflow_engine,
    )
    LOGGER.info(
        "Agent 任务开始：run_id=%s，输入=%s，启用LLM=%s，自动发布低风险=%s，自动放行小改动=%s，工作流=%s",
        run_id,
        input_path,
        use_llm,
        auto_publish_low_risk,
        auto_approve_small_changes,
        workflow_engine,
    )

    state_file = Path(state_path)
    run_log_path = Path(run_log_dir)
    state = _load_state(state_file)

    purged_temp = purge_temporary_office_artifacts()
    if any(purged_temp.values()):
        LOGGER.info(
            "已清理 Office 临时文件残留：Raw=%s，manifest=%s，parsed=%s",
            purged_temp["raw_files"],
            purged_temp["manifests"],
            purged_temp["parsed_outputs"],
        )

    manifests = ingest(str(input_path))
    report.manifests_seen = len(manifests)
    LOGGER.info("文档入库完成：发现 %s 份文档", report.manifests_seen)

    if clean_rebuild:
        LOGGER.info("启用干净重建：清空页面与提案输出，并重置 Agent 状态")
        clear_page_output()
        clear_proposal_output()
        state["documents"] = {}
        pages_exist = False
    else:
        pages_exist = bool(load_all_pages())
    LOGGER.info("当前是否已有 Wiki 页面：%s", pages_exist)

    parsed_manifests: list[dict[str, Any]] = []
    docs_to_incrementally_maintain: list[dict[str, Any]] = []

    for manifest in manifests:
        latest_manifest = manifest
        document_id = manifest["document_id"]
        parse_required = (
            force_reparse
            or not manifest.get("parsed_output")
            or manifest.get("parse_status") not in SUCCESS_PARSE_STATUSES
        )
        parsed_now = False
        LOGGER.info(
            "发现文档：document_id=%s，文件=%s，需要解析=%s",
            document_id,
            manifest.get("file_name", ""),
            parse_required,
        )

        if parse_required:
            LOGGER.info("开始解析文档：document_id=%s", document_id)
            parse_one(document_id)
            latest_manifest = load_manifest(document_id)
            parsed_now = True
            report.documents_parsed.append(document_id)
            LOGGER.info(
                "文档解析完成：document_id=%s，状态=%s",
                document_id,
                latest_manifest.get("parse_status", "pending"),
            )

        parse_status = latest_manifest.get("parse_status", "pending")
        document_result = DocumentRunResult(
            document_id=document_id,
            file_name=latest_manifest.get("file_name", ""),
            checksum=latest_manifest.get("checksum", ""),
            parse_status=parse_status,
            parsed_output=latest_manifest.get("parsed_output"),
            action="parsed" if parsed_now else "observed",
        )

        if parse_status in SUCCESS_PARSE_STATUSES and latest_manifest.get("parsed_output"):
            parsed_manifests.append(latest_manifest)
            tracked = state["documents"].get(document_id, {})
            needs_maintenance = force_reconcile or not pages_exist or _needs_maintenance(latest_manifest, tracked)
            if needs_maintenance:
                docs_to_incrementally_maintain.append(latest_manifest)
                document_result.action = "queued_for_maintenance"
                LOGGER.info("文档已加入 Wiki 维护队列：document_id=%s", document_id)
            else:
                document_result.action = "up_to_date"
                document_result.note = "checksum unchanged and already maintained"
                LOGGER.info("文档跳过维护：内容未变化且已处理过，document_id=%s", document_id)
        else:
            document_result.action = "parse_failed"
            document_result.note = "document could not enter wiki maintenance flow"
            LOGGER.warning("文档未进入 Wiki 维护流程：document_id=%s，解析状态=%s", document_id, parse_status)

        report.documents.append(document_result)

    return _complete_workflow_maintenance(
        report=report,
        state=state,
        state_file=state_file,
        run_log_dir=run_log_path,
        run_id=run_id,
        pages_exist=pages_exist,
        parsed_manifests=parsed_manifests,
        docs_to_incrementally_maintain=docs_to_incrementally_maintain,
        use_llm=use_llm,
        auto_publish_low_risk=auto_publish_low_risk,
        auto_approve_small_changes=auto_approve_small_changes,
        workflow_engine=workflow_engine,
        scan_conflicts=scan_conflicts,
        sync_obsidian_output=sync_obsidian_output,
    )


def _complete_workflow_maintenance(
    *,
    report: AgentRunReport,
    state: dict[str, Any],
    state_file: Path,
    run_log_dir: Path,
    run_id: str,
    pages_exist: bool,
    parsed_manifests: list[dict[str, Any]],
    docs_to_incrementally_maintain: list[dict[str, Any]],
    use_llm: bool,
    auto_publish_low_risk: bool,
    auto_approve_small_changes: bool,
    workflow_engine: str,
    scan_conflicts: bool,
    sync_obsidian_output: bool,
) -> AgentRunReport:
    should_bootstrap = not pages_exist and bool(parsed_manifests)
    should_run_workflow = should_bootstrap or bool(docs_to_incrementally_maintain)
    workflow_result: dict[str, Any] = {}

    if should_run_workflow:
        workflow_result = run_agent_workflow(
            bootstrap=should_bootstrap,
            parsed_manifests=parsed_manifests,
            docs_to_incrementally_maintain=docs_to_incrementally_maintain,
            use_llm=use_llm,
            auto_approve_small_changes=auto_publish_low_risk and auto_approve_small_changes,
            workflow_engine=workflow_engine,
        )
    else:
        LOGGER.info("本次没有需要维护的页面变更，跳过工作流执行")

    report.bootstrap_performed = bool(workflow_result.get("bootstrap_performed", False))
    report.pages_created = int(workflow_result.get("pages_created", 0))
    report.proposals_created += int(workflow_result.get("proposals_created", 0))
    report.pages_published = int(workflow_result.get("pages_published", 0))
    report.pending_review_count = int(workflow_result.get("pending_review_count", 0))

    per_document_proposals = workflow_result.get("per_document_proposals", {})
    maintained_document_ids = {manifest["document_id"] for manifest in docs_to_incrementally_maintain}

    for item in report.documents:
        if item.parse_status not in SUCCESS_PARSE_STATUSES:
            continue

        if report.bootstrap_performed:
            item.action = "bootstrapped"
            item.proposals_created = int(per_document_proposals.get(item.document_id, 0))
            item.published_immediately = item.proposals_created if report.pages_published else 0
            if item.proposals_created == 0:
                item.note = "bootstrap candidate did not cite this document"
            _record_document_state(
                state,
                document_id=item.document_id,
                checksum=item.checksum,
                parse_status=item.parse_status,
                parsed_output=item.parsed_output,
                action="bootstrap",
                run_id=run_id,
            )
            continue

        if item.document_id in maintained_document_ids:
            item.action = "incremental_update"
            item.proposals_created = int(per_document_proposals.get(item.document_id, 0))
            item.published_immediately = item.proposals_created if report.pages_published else 0
            if item.proposals_created == 0:
                item.note = "no new evidence matched existing pages"
            _record_document_state(
                state,
                document_id=item.document_id,
                checksum=item.checksum,
                parse_status=item.parse_status,
                parsed_output=item.parsed_output,
                action="incremental_update",
                run_id=run_id,
            )

    if scan_conflicts and report.proposals_created > 0:
        LOGGER.info("开始冲突扫描")
        conflicts = conflict_scan()
        report.conflicts_found = len(conflicts)
        LOGGER.info("冲突扫描完成：发现 %s 个冲突", report.conflicts_found)

    if sync_obsidian_output:
        LOGGER.info("开始导出 Markdown 到 wiki/output/obsidian")
        sync_to_obsidian()
        report.obsidian_synced = True
        LOGGER.info("Markdown 导出完成")

    report.completed_at = _now_iso()
    state["last_run"] = report.to_dict()
    _save_state(state_file, state)
    _save_run_report(run_log_dir, report)
    LOGGER.info(
        "Agent 任务完成：run_id=%s，新增页面=%s，新增提案=%s，待人工审核=%s，冲突=%s，已发布=%s",
        report.run_id,
        report.pages_created,
        report.proposals_created,
        report.pending_review_count,
        report.conflicts_found,
        report.pages_published,
    )
    if report.pending_review_count > 0:
        LOGGER.info(
            "本次有 %s 个提案待人工审核。命令行可执行：python -m wiki.updaters.review_publish --approve-all",
            report.pending_review_count,
        )
        LOGGER.info(
            "或调用 API：POST /agent/proposals/approve-all（也可逐个批准 /agent/proposals/{proposal_id}/approve）"
        )
    return report


def _needs_maintenance(manifest: dict[str, Any], tracked: dict[str, Any]) -> bool:
    if not tracked:
        return True
    return (
        tracked.get("last_maintained_checksum") != manifest.get("checksum")
        or tracked.get("last_parse_status") != manifest.get("parse_status")
        or tracked.get("last_action") == "parse_failed"
    )


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        LOGGER.debug("未找到 Agent 状态文件，将创建新状态：%s", path)
        return {"documents": {}, "last_run": None}
    LOGGER.debug("加载 Agent 状态文件：%s", path)
    return json.loads(path.read_text(encoding="utf-8"))


def _save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    LOGGER.debug("Agent 状态已保存：%s", path)


def _save_run_report(run_log_dir: Path, report: AgentRunReport) -> None:
    run_log_dir.mkdir(parents=True, exist_ok=True)
    run_path = run_log_dir / f"{report.run_id}.json"
    run_path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    LOGGER.debug("运行摘要已保存：%s", run_path)


def _record_document_state(
    state: dict[str, Any],
    *,
    document_id: str,
    checksum: str,
    parse_status: str,
    parsed_output: str | None,
    action: str,
    run_id: str,
) -> None:
    state.setdefault("documents", {})
    state["documents"][document_id] = {
        "last_maintained_at": _now_iso(),
        "last_maintained_checksum": checksum,
        "last_parse_status": parse_status,
        "parsed_output": parsed_output,
        "last_action": action,
        "last_run_id": run_id,
    }


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def configure_logging(level: str = "INFO") -> None:
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s [%(levelname)s] %(name)s：%(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        force=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Agent 入口：入库上传文件、解析文档、维护 Wiki、导出 Obsidian。",
    )
    parser.add_argument(
        "--input",
        default=str(DEFAULT_INPUT_PATH),
        help="输入文件或目录路径。默认扫描 Raw/。",
    )
    parser.add_argument("--use-llm", action="store_true", help="启用大模型参与摘要和审核。")
    parser.add_argument("--force-reparse", action="store_true", help="即使已有解析结果也重新解析。")
    parser.add_argument(
        "--force-reconcile",
        action="store_true",
        help="即使 checksum 未变化，也重新执行 Wiki 维护。",
    )
    parser.add_argument(
        "--clean-rebuild",
        action="store_true",
        help="清空已生成页面和提案，然后基于已解析文档重建。",
    )
    parser.add_argument(
        "--no-auto-publish-low-risk",
        action="store_true",
        help="低风险变更不自动落盘发布，进入人工审核。",
    )
    parser.add_argument(
        "--no-auto-approve-small-changes",
        action="store_true",
        help="即使是小改动，也要求人工审核。",
    )
    parser.add_argument(
        "--workflow-engine",
        default="auto",
        choices=["auto", "langgraph", "builtin"],
        help="工作流引擎。auto 优先使用 LangGraph。",
    )
    parser.add_argument(
        "--skip-conflict-scan",
        action="store_true",
        help="跳过冲突扫描。",
    )
    parser.add_argument(
        "--skip-sync",
        action="store_true",
        help="跳过 Obsidian Markdown 导出。",
    )
    parser.add_argument(
        "--state-path",
        default=str(DEFAULT_STATE_PATH),
        help="Agent 状态文件路径，默认是 App/output/agent_state.json。",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="日志级别。DEBUG 可查看更详细的工作流与 LLM 调用过程。",
    )
    args = parser.parse_args()
    configure_logging(args.log_level)

    report = maintain_wiki(
        input_path=args.input,
        use_llm=args.use_llm,
        auto_publish_low_risk=not args.no_auto_publish_low_risk,
        auto_approve_small_changes=not args.no_auto_approve_small_changes,
        scan_conflicts=not args.skip_conflict_scan,
        sync_obsidian_output=not args.skip_sync,
        force_reparse=args.force_reparse,
        force_reconcile=args.force_reconcile,
        clean_rebuild=args.clean_rebuild,
        workflow_engine=args.workflow_engine,
        state_path=args.state_path,
    )
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
