from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from wiki.models.page import PageSection, WikiPage
from wiki.page_ids import canonical_page_id, is_legacy_page_id
from wiki.store import files as file_store
from wiki.store.files import load_all_pages, load_published_pages

REPO_ROOT = Path(__file__).resolve().parents[2]
PAGE_DIR = REPO_ROOT / "wiki" / "output" / "pages"
PROPOSAL_DIR = REPO_ROOT / "wiki" / "output" / "proposals"
EXPORT_DIR = REPO_ROOT / "wiki" / "output" / "obsidian"
LOGGER = logging.getLogger(__name__)


def convert_page_to_markdown(page_data: dict, page_name_map: dict[str, str]) -> str:
    lines = [
        f"# {page_data['title']}",
        "",
        "---",
        f"page_id: {page_data['page_id']}",
        f"page_type: {page_data['page_type']}",
        f"review_status: {page_data.get('review_status', 'unknown')}",
        f"page_version: {page_data.get('page_version', 1)}",
        f"updated_at: {page_data.get('updated_at', '')}",
    ]
    if page_data.get("aliases"):
        lines.append(f"aliases: {page_data['aliases']}")
    lines.extend(["---", "", "## 摘要", page_data.get("summary", "暂无摘要"), ""])

    if page_data.get("linked_pages"):
        lines.append("## 关联页面")
        for linked in page_data["linked_pages"]:
            lines.append(f"- [[{page_name_map.get(linked, linked)}]]")
        lines.append("")

    for section in page_data.get("sections", []):
        lines.append(f"## {section.get('heading', '')}")
        lines.append(section.get("content", ""))
        lines.append("")

    if page_data.get("source_refs"):
        lines.append("## 来源引用")
        for ref in page_data["source_refs"][:10]:
            doc = ref.get("file_name", "未知文档")
            anchor = ref.get("anchor_label", "")
            quote = ref.get("quote", "")[:100]
            lines.append(f"> **{doc}** {anchor}")
            lines.append(f"> {quote}...")
            lines.append("")

    return "\n".join(lines)


def convert_proposal_to_markdown(proposal_data: dict, page_name_map: dict[str, str]) -> str:
    target_page_name = page_name_map.get(proposal_data["target_page_id"], proposal_data["target_page_id"])
    lines = [
        f"# 提案: {proposal_data['proposal_id']}",
        "",
        "---",
        f"target_page: [[{target_page_name}]]",
        f"action: {proposal_data['action']}",
        f"risk_level: {proposal_data.get('risk_level', 'medium')}",
        f"change_scope: {proposal_data.get('change_scope', 'medium')}",
        f"review_mode: {proposal_data.get('review_mode', 'human_required')}",
        f"status: {proposal_data.get('status', 'pending')}",
        "---",
        "",
        "## 原因",
        proposal_data.get("reason", ""),
        "",
    ]

    if proposal_data.get("candidate_content"):
        lines.extend(["## 建议内容", proposal_data["candidate_content"], ""])

    if proposal_data.get("evidence_fragment_ids"):
        lines.append("## 证据片段")
        for fragment_id in proposal_data["evidence_fragment_ids"]:
            lines.append(f"- {fragment_id}")
        lines.append("")

    return "\n".join(lines)


def sync_to_obsidian(output_dir: str | Path | None = None) -> Path:
    target_dir = Path(output_dir) if output_dir else EXPORT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    proposals_dir = target_dir / "Proposals"
    proposals_dir.mkdir(exist_ok=True)

    page_records: list[tuple[dict, str]] = []
    page_name_map: dict[str, str] = {}
    for page in _load_export_pages():
        page_data = page.to_dict()
        export_name = _safe_page_name(page_data["title"], page_data["page_id"])
        page_records.append((page_data, export_name))
        page_name_map[page_data["page_id"]] = export_name

    expected_files: set[Path] = set()
    for page_data, export_name in page_records:
        markdown = convert_page_to_markdown(page_data, page_name_map)
        target_file = target_dir / f"{export_name}.md"
        target_file.write_text(markdown, encoding="utf-8")
        expected_files.add(target_file.resolve())
        LOGGER.info("已导出页面：%s", target_file.name)

    if PROPOSAL_DIR.exists():
        for json_file in sorted(PROPOSAL_DIR.glob("*.json")):
            proposal_data = json.loads(json_file.read_text(encoding="utf-8"))
            if proposal_data.get("status") == "archived" or proposal_data.get("archived") is True:
                continue
            markdown = convert_proposal_to_markdown(proposal_data, page_name_map)
            target_file = proposals_dir / f"{json_file.stem}.md"
            target_file.write_text(markdown, encoding="utf-8")
            expected_files.add(target_file.resolve())
            LOGGER.info("已导出提案：%s", target_file.name)

    _cleanup_stale_markdown(target_dir, expected_files)
    return target_dir


def _cleanup_stale_markdown(target_dir: Path, expected_files: set[Path]) -> None:
    for file_path in sorted(target_dir.rglob("*.md")):
        resolved = file_path.resolve()
        if resolved in expected_files:
            continue
        try:
            file_path.unlink()
            LOGGER.info("已删除旧导出文件：%s", file_path.name)
        except PermissionError:
            LOGGER.warning("无法删除旧导出文件（可能正被 Obsidian 或编辑器占用）：%s", file_path)

    stale_dirs = [path for path in sorted(target_dir.rglob("*"), reverse=True) if path.is_dir()]
    for directory in stale_dirs:
        if directory == target_dir:
            continue
        try:
            next(directory.iterdir())
        except StopIteration:
            try:
                directory.rmdir()
            except OSError:
                pass


def _safe_page_name(title: str, page_id: str) -> str:
    sanitized = "".join("_" if ch in '<>:"/\\|?*' else ch for ch in title).strip().rstrip(".")
    return sanitized or page_id


def _load_export_pages() -> list[WikiPage]:
    if PAGE_DIR == file_store.PAGE_DIR:
        return load_published_pages()

    pages_by_id: dict[str, tuple[WikiPage, bool]] = {}
    for path in sorted(PAGE_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        raw_page_id = data["page_id"]
        page = WikiPage(
            page_id=canonical_page_id(raw_page_id),
            title=data["title"],
            page_type=data["page_type"],
            summary=data.get("summary", ""),
            sections=[PageSection(**section) for section in data.get("sections", [])],
            aliases=list(data.get("aliases", [])),
            source_refs=list(data.get("source_refs", [])),
            linked_pages=[canonical_page_id(page_id) for page_id in data.get("linked_pages", [])],
            review_status=data.get("review_status", "generated"),
            page_version=int(data.get("page_version", 1)),
            updated_at=data.get("updated_at", ""),
        )
        candidate_is_legacy = is_legacy_page_id(raw_page_id)
        existing = pages_by_id.get(page.page_id)
        if existing is None or _should_replace_page(existing[0], existing[1], page, candidate_is_legacy):
            pages_by_id[page.page_id] = (page, candidate_is_legacy)
    return [item[0] for item in pages_by_id.values() if item[0].review_status == "published"]


def _should_replace_page(current: WikiPage, current_is_legacy: bool, candidate: WikiPage, candidate_is_legacy: bool) -> bool:
    if current_is_legacy != candidate_is_legacy:
        return not candidate_is_legacy
    return candidate.updated_at >= current.updated_at


def main() -> None:
    parser = argparse.ArgumentParser(description="Export wiki pages and proposals as Obsidian-compatible markdown.")
    parser.add_argument(
        "--output-dir",
        default=str(EXPORT_DIR),
        help="Optional export directory. Defaults to wiki/output/obsidian.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s：%(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        force=True,
    )
    target = sync_to_obsidian(args.output_dir)
    print(f"导出完成 -> {target}")


if __name__ == "__main__":
    main()
