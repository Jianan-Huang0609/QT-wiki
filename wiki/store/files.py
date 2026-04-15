from __future__ import annotations

import json
from pathlib import Path

from wiki.models.page import PageSection, UpdateProposal, WikiPage
from wiki.page_ids import canonical_page_id, is_legacy_page_id

REPO_ROOT = Path(__file__).resolve().parents[2]
PAGE_DIR = REPO_ROOT / "wiki" / "output" / "pages"
PROPOSAL_DIR = REPO_ROOT / "wiki" / "output" / "proposals"
OBSIDIAN_PROPOSAL_DIR = REPO_ROOT / "wiki" / "output" / "obsidian" / "Proposals"


def save_page(page: WikiPage) -> Path:
    PAGE_DIR.mkdir(parents=True, exist_ok=True)
    data = page.to_dict()
    data["page_id"] = canonical_page_id(page.page_id)
    data["linked_pages"] = [canonical_page_id(page_id) for page_id in data.get("linked_pages", [])]
    path = PAGE_DIR / f"{data['page_id']}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_page(page_id: str) -> WikiPage:
    normalized_page_id = canonical_page_id(page_id)
    path = PAGE_DIR / f"{normalized_page_id}.json"
    if not path.exists():
        path = PAGE_DIR / f"{page_id}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return _page_from_data(data)


def load_all_pages() -> list[WikiPage]:
    if not PAGE_DIR.exists():
        return []
    pages_by_id: dict[str, tuple[WikiPage, bool]] = {}
    for path in sorted(PAGE_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        raw_page_id = data["page_id"]
        page = _page_from_data(data)
        existing = pages_by_id.get(page.page_id)
        candidate_is_legacy = is_legacy_page_id(raw_page_id)
        if existing is None or _should_replace_page(existing[0], existing[1], page, candidate_is_legacy):
            pages_by_id[page.page_id] = (page, candidate_is_legacy)
    return [item[0] for item in pages_by_id.values()]


def load_published_pages() -> list[WikiPage]:
    return [page for page in load_all_pages() if page.review_status == "published"]


def save_proposal(proposal: UpdateProposal) -> Path:
    PROPOSAL_DIR.mkdir(parents=True, exist_ok=True)
    path = PROPOSAL_DIR / f"{proposal.proposal_id}.json"
    path.write_text(json.dumps(proposal.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def clear_page_output() -> None:
    if not PAGE_DIR.exists():
        return
    for path in PAGE_DIR.glob("*.json"):
        try:
            path.unlink()
        except PermissionError:
            continue


def clear_proposal_output() -> None:
    _clear_matching_files(PROPOSAL_DIR, "*.json", on_permission_error=_archive_proposal_json)
    _clear_matching_files(OBSIDIAN_PROPOSAL_DIR, "*.md", on_permission_error=_write_archived_markdown_placeholder)


def _clear_matching_files(directory: Path, pattern: str, on_permission_error=None) -> None:
    if not directory.exists():
        return
    for path in directory.glob(pattern):
        try:
            path.unlink()
        except PermissionError:
            if on_permission_error is not None:
                on_permission_error(path)


def _archive_proposal_json(path: Path) -> None:
    proposal_id = path.stem
    archived_data = {
        "proposal_id": proposal_id,
        "target_page_id": "",
        "action": "archived",
        "reason": "历史提案在清理时被占用，已归档忽略",
        "candidate_content": "",
        "evidence_fragment_ids": [],
        "risk_level": "low",
        "status": "archived",
        "archived": True,
    }
    path.write_text(json.dumps(archived_data, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_archived_markdown_placeholder(path: Path) -> None:
    path.write_text(
        "# 已归档\n\n该提案文件在清理时被占用。关闭占用它的程序后，再次同步会自动删除。\n",
        encoding="utf-8",
    )


def _page_from_data(data: dict) -> WikiPage:
    normalized_page_id = canonical_page_id(data["page_id"])
    linked_pages = [canonical_page_id(page_id) for page_id in data.get("linked_pages", [])]
    return WikiPage(
        page_id=normalized_page_id,
        title=data["title"],
        page_type=data["page_type"],
        summary=data["summary"],
        sections=[PageSection(**section) for section in data.get("sections", [])],
        aliases=list(data.get("aliases", [])),
        source_refs=list(data.get("source_refs", [])),
        linked_pages=linked_pages,
        review_status=data.get("review_status", "generated"),
        page_version=int(data.get("page_version", 1)),
        updated_at=data.get("updated_at", ""),
    )


def _should_replace_page(current: WikiPage, current_is_legacy: bool, candidate: WikiPage, candidate_is_legacy: bool) -> bool:
    if current_is_legacy != candidate_is_legacy:
        return not candidate_is_legacy
    return candidate.updated_at >= current.updated_at
