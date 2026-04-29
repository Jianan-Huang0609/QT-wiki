from __future__ import annotations

import json
from json import JSONDecodeError
from pathlib import Path

from wiki.models.page import DocumentIdentity, HumanReviewQuestion, PageSection, ReviewIssue, ReviewObject, ReviewPackage, ReviewRelation, UpdateProposal, WikiPage
from wiki.page_ids import canonical_page_id, is_legacy_page_id
from wiki.store.markdown import save_page_markdown, save_proposal_markdown, save_review_package_markdown

REPO_ROOT = Path(__file__).resolve().parents[2]
PAGE_DIR = REPO_ROOT / "wiki" / "output" / "pages"
PROPOSAL_DIR = REPO_ROOT / "wiki" / "output" / "proposals"
REVIEW_PACKAGE_DIR = REPO_ROOT / "wiki" / "output" / "review_packages"
OBSIDIAN_PROPOSAL_DIR = REPO_ROOT / "wiki" / "output" / "obsidian" / "Proposals"
OBSIDIAN_PAGE_DIR = REPO_ROOT / "wiki" / "output" / "obsidian" / "Pages"
OBSIDIAN_REVIEW_PACKAGE_DIR = REPO_ROOT / "wiki" / "output" / "obsidian" / "ReviewPackages"


def save_page(page: WikiPage) -> Path:
    PAGE_DIR.mkdir(parents=True, exist_ok=True)
    data = page.to_dict()
    data["page_id"] = canonical_page_id(page.page_id)
    data["linked_pages"] = [canonical_page_id(page_id) for page_id in data.get("linked_pages", [])]
    path = PAGE_DIR / f"{data['page_id']}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    save_page_markdown(_page_from_data(data), _obsidian_page_dir())
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
        try:
            raw_text = path.read_text(encoding="utf-8").strip()
            if not raw_text:
                print(f"[wiki.store] skip empty page json: {path.name}")
                continue
            data = json.loads(raw_text)
        except (OSError, JSONDecodeError, UnicodeDecodeError, KeyError) as exc:
            print(f"[wiki.store] skip invalid page json {path.name}: {exc}")
            continue
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
    save_proposal_markdown(proposal, _obsidian_proposal_dir())
    return path


def save_review_package(review_package: ReviewPackage) -> Path:
    REVIEW_PACKAGE_DIR.mkdir(parents=True, exist_ok=True)
    path = REVIEW_PACKAGE_DIR / f"{review_package.package_id}.json"
    path.write_text(json.dumps(review_package.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    save_review_package_markdown(review_package, _obsidian_review_package_dir())
    return path


def update_review_package_decision(
    package_id: str,
    *,
    identity_decision: str,
    confirmed_business_type: str,
    confirmed_effective_level: str,
    confirmed_is_binding: bool,
    review_notes: str,
    reviewed_by: str,
    reviewed_at: str,
) -> ReviewPackage:
    review_package = load_review_package(package_id)
    review_package.identity_decision = identity_decision
    review_package.confirmed_business_type = confirmed_business_type
    review_package.confirmed_effective_level = confirmed_effective_level
    review_package.confirmed_is_binding = confirmed_is_binding
    review_package.review_notes = review_notes
    review_package.reviewed_by = reviewed_by
    review_package.reviewed_at = reviewed_at
    review_package.status = _review_package_status(review_package, identity_decision=identity_decision)
    review_package.updated_at = reviewed_at
    save_review_package(review_package)
    return review_package


def update_review_package_relation_decision(
    package_id: str,
    *,
    relation_decision: str,
    relation_review_notes: str,
    relation_reviewed_by: str,
    relation_reviewed_at: str,
) -> ReviewPackage:
    review_package = load_review_package(package_id)
    review_package.relation_decision = relation_decision
    review_package.relation_review_notes = relation_review_notes
    review_package.relation_reviewed_by = relation_reviewed_by
    review_package.relation_reviewed_at = relation_reviewed_at
    review_package.status = _review_package_status(review_package, relation_decision=relation_decision)
    review_package.updated_at = relation_reviewed_at
    save_review_package(review_package)
    return review_package


def load_review_package(package_id: str) -> ReviewPackage:
    path = REVIEW_PACKAGE_DIR / f"{package_id}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return _review_package_from_data(data)


def list_review_packages() -> list[ReviewPackage]:
    if not REVIEW_PACKAGE_DIR.exists():
        return []
    packages: list[ReviewPackage] = []
    for path in sorted(REVIEW_PACKAGE_DIR.glob("*.json")):
        try:
            raw_text = path.read_text(encoding="utf-8").strip()
            if not raw_text:
                print(f"[wiki.store] skip empty review package json: {path.name}")
                continue
            packages.append(_review_package_from_data(json.loads(raw_text)))
        except (OSError, JSONDecodeError, UnicodeDecodeError, KeyError, TypeError) as exc:
            print(f"[wiki.store] skip invalid review package json {path.name}: {exc}")
    return packages


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
    _clear_matching_files(_obsidian_proposal_dir(), "*.md", on_permission_error=_write_archived_markdown_placeholder)


def _obsidian_page_dir() -> Path:
    if PAGE_DIR == REPO_ROOT / "wiki" / "output" / "pages":
        return OBSIDIAN_PAGE_DIR
    return PAGE_DIR.parent / "obsidian" / "Pages"


def _obsidian_proposal_dir() -> Path:
    if PROPOSAL_DIR == REPO_ROOT / "wiki" / "output" / "proposals":
        return OBSIDIAN_PROPOSAL_DIR
    return PROPOSAL_DIR.parent / "obsidian" / "Proposals"


def _obsidian_review_package_dir() -> Path:
    if REVIEW_PACKAGE_DIR == REPO_ROOT / "wiki" / "output" / "review_packages":
        return OBSIDIAN_REVIEW_PACKAGE_DIR
    return REVIEW_PACKAGE_DIR.parent / "obsidian" / "ReviewPackages"


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


def _review_package_from_data(data: dict) -> ReviewPackage:
    identity_data = data["document_identity"]
    return ReviewPackage(
        package_id=data["package_id"],
        document_id=data["document_id"],
        status=data.get("status", "pending_review"),
        document_identity=DocumentIdentity(**identity_data),
        identity_decision=data.get("identity_decision", "pending"),
        confirmed_business_type=data.get("confirmed_business_type", ""),
        confirmed_effective_level=data.get("confirmed_effective_level", ""),
        confirmed_is_binding=data.get("confirmed_is_binding"),
        review_notes=data.get("review_notes", ""),
        reviewed_at=data.get("reviewed_at", ""),
        reviewed_by=data.get("reviewed_by", ""),
        relation_decision=data.get("relation_decision", "pending"),
        relation_review_notes=data.get("relation_review_notes", ""),
        relation_reviewed_at=data.get("relation_reviewed_at", ""),
        relation_reviewed_by=data.get("relation_reviewed_by", ""),
        evidence_refs=list(data.get("evidence_refs", [])),
        extracted_objects=[ReviewObject(**item) for item in data.get("extracted_objects", [])],
        extracted_relations=[ReviewRelation(**item) for item in data.get("extracted_relations", [])],
        issues=[ReviewIssue(**item) for item in data.get("issues", [])],
        human_questions=[HumanReviewQuestion(**item) for item in data.get("human_questions", [])],
        candidate_page_titles=list(data.get("candidate_page_titles", [])),
        created_at=data.get("created_at", ""),
        updated_at=data.get("updated_at", ""),
        tool_trace=list(data.get("tool_trace", [])),
    )


def _should_replace_page(current: WikiPage, current_is_legacy: bool, candidate: WikiPage, candidate_is_legacy: bool) -> bool:
    if current_is_legacy != candidate_is_legacy:
        return not candidate_is_legacy
    return candidate.updated_at >= current.updated_at


def _review_package_status(
    review_package: ReviewPackage,
    *,
    identity_decision: str | None = None,
    relation_decision: str | None = None,
) -> str:
    next_identity = identity_decision if identity_decision is not None else review_package.identity_decision
    next_relation = relation_decision if relation_decision is not None else review_package.relation_decision

    if next_identity != "confirmed":
        return "pending_revision" if next_identity == "needs_revision" else "pending_review"
    if next_relation == "needs_revision":
        return "pending_revision"
    if next_relation in {"confirmed", "not_applicable"}:
        return "ready_to_publish"
    return "identity_confirmed"
