from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from wiki.models.page import WikiPage
from wiki.page_ids import canonical_page_id
from wiki.store import files

PAGE_INDEX_FILE = "pages.jsonl"
TERMS_INDEX_FILE = "terms.json"
LINKS_INDEX_FILE = "links.json"
SOURCES_INDEX_FILE = "sources.jsonl"


def build_index(*, pages: list[WikiPage] | None = None, index_dir: Path | None = None) -> dict[str, Path]:
    pages = files.load_all_pages() if pages is None else pages
    target_dir = _index_dir(index_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    page_entries = [_page_entry(page) for page in pages]
    terms = _build_terms_index(page_entries)
    links = _build_links_index(pages)
    source_entries = _build_sources_index(pages)

    page_index_path = target_dir / PAGE_INDEX_FILE
    page_index_path.write_text(
        "".join(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n" for entry in page_entries),
        encoding="utf-8",
    )
    (target_dir / TERMS_INDEX_FILE).write_text(
        json.dumps(terms, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (target_dir / LINKS_INDEX_FILE).write_text(
        json.dumps(links, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (target_dir / SOURCES_INDEX_FILE).write_text(
        "".join(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n" for entry in source_entries),
        encoding="utf-8",
    )

    return {
        "pages": page_index_path,
        "terms": target_dir / TERMS_INDEX_FILE,
        "links": target_dir / LINKS_INDEX_FILE,
        "sources": target_dir / SOURCES_INDEX_FILE,
    }


def ensure_index(*, index_dir: Path | None = None) -> Path:
    target_dir = _index_dir(index_dir)
    page_index_path = target_dir / PAGE_INDEX_FILE
    if not page_index_path.exists() or _index_is_stale(page_index_path):
        build_index(index_dir=target_dir)
    return page_index_path


def load_page_index(*, index_dir: Path | None = None) -> list[dict[str, Any]]:
    path = ensure_index(index_dir=index_dir)
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entries.append(json.loads(line))
    return entries


def rank_page_index(query: str, entries: list[dict[str, Any]], *, limit: int = 5) -> list[dict[str, Any]]:
    keywords = extract_keywords(query)
    scored: list[tuple[float, str, dict[str, Any]]] = []
    for entry in entries:
        score = _score_entry(entry, keywords, query)
        if score > 0:
            scored.append((score, entry.get("page_id", ""), entry))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [dict(entry, relevance_score=score) for score, _, entry in scored[:limit]]


def extract_keywords(query: str) -> list[str]:
    stopwords = {"的", "了", "和", "是", "在", "有", "什么", "如何", "怎么", "吗", "呢", "请", "问"}
    ascii_words = re.findall(r"[a-zA-Z0-9][a-zA-Z0-9_-]{1,}", query)
    normalized = re.sub(r"[，。！？；：、,.!?;:\s]+", "|", query)
    for marker in (
        "关于",
        "对于",
        "有关",
        "什么是",
        "有哪些",
        "有什么",
        "如何",
        "怎么",
        "为什么",
        "是否",
        "扮演什么角色",
        "扮演",
        "作用",
        "角色",
        "要求",
        "流程",
        "职责",
        "里面",
        "当中",
        "其中",
        "里的",
        "中的",
        "在",
        "里",
        "中",
    ):
        normalized = normalized.replace(marker, "|")
    chinese_parts = [part.strip() for part in normalized.split("|") if part.strip()]
    chinese_words = [part for part in chinese_parts if re.search(r"[\u4e00-\u9fa5]", part) and len(part) >= 2]

    result: list[str] = []
    for word in [*chinese_words, *ascii_words]:
        if word in stopwords:
            continue
        if word not in result:
            result.append(word)
    return result


def _index_dir(index_dir: Path | None) -> Path:
    if index_dir is not None:
        return index_dir
    return files.PAGE_DIR.parent / "index"


def _index_is_stale(page_index_path: Path) -> bool:
    if not files.PAGE_DIR.exists():
        return False
    index_mtime = page_index_path.stat().st_mtime
    return any(path.stat().st_mtime > index_mtime for path in files.PAGE_DIR.glob("*.json"))


def _page_entry(page: WikiPage) -> dict[str, Any]:
    refs = _dedupe_refs(page.source_refs)
    section_headings = [section.heading for section in page.sections]
    keywords = _dedupe_texts([page.title, *page.aliases, *page.linked_pages, *section_headings, *_extract_page_terms(page)])
    return {
        "page_id": canonical_page_id(page.page_id),
        "title": page.title,
        "page_type": page.page_type,
        "aliases": list(page.aliases),
        "summary": page.summary,
        "keywords": keywords,
        "linked_pages": [canonical_page_id(page_id) for page_id in page.linked_pages],
        "source_count": len(refs),
        "updated_at": page.updated_at,
        "review_status": page.review_status,
    }


def _build_terms_index(entries: list[dict[str, Any]]) -> dict[str, list[str]]:
    terms: dict[str, list[str]] = {}
    for entry in entries:
        page_id = entry["page_id"]
        for term in _dedupe_texts([entry["title"], *entry.get("aliases", []), *entry.get("keywords", [])]):
            terms.setdefault(term, [])
            if page_id not in terms[term]:
                terms[term].append(page_id)
    return terms


def _build_links_index(pages: list[WikiPage]) -> dict[str, list[str]]:
    return {
        canonical_page_id(page.page_id): [canonical_page_id(page_id) for page_id in page.linked_pages]
        for page in pages
    }


def _build_sources_index(pages: list[WikiPage]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for page in pages:
        page_id = canonical_page_id(page.page_id)
        for ref in _dedupe_refs(page.source_refs):
            key = (page_id, str(ref.get("document_id", "")), str(ref.get("fragment_id", "")))
            if key in seen:
                continue
            seen.add(key)
            entries.append(
                {
                    "page_id": page_id,
                    "title": page.title,
                    "document_id": ref.get("document_id", ""),
                    "fragment_id": ref.get("fragment_id", ""),
                    "file_name": ref.get("file_name", ""),
                    "anchor_label": ref.get("anchor_label", ""),
                }
            )
    entries.sort(key=lambda item: (item["page_id"], item["document_id"], item["fragment_id"]))
    return entries


def _extract_page_terms(page: WikiPage) -> list[str]:
    terms: list[str] = []
    for section in page.sections:
        terms.extend(extract_keywords(section.heading))
    terms.extend(extract_keywords(page.summary))
    return terms[:20]


def _score_entry(entry: dict[str, Any], keywords: list[str], query: str) -> float:
    title = str(entry.get("title", ""))
    aliases = [str(alias) for alias in entry.get("aliases", [])]
    haystacks = {
        "title": title,
        "aliases": " ".join(aliases),
        "summary": str(entry.get("summary", "")),
        "keywords": " ".join(str(keyword) for keyword in entry.get("keywords", [])),
        "page_type": str(entry.get("page_type", "")),
    }

    compact_query = _compact(query)
    score = 0.0
    if compact_query and compact_query == _compact(title):
        score += 10
    if compact_query and any(compact_query == _compact(alias) for alias in aliases):
        score += 8

    for keyword in keywords:
        compact_keyword = _compact(keyword)
        if not compact_keyword:
            continue
        if compact_keyword in _compact(haystacks["title"]):
            score += 5
        if compact_keyword in _compact(haystacks["aliases"]):
            score += 4
        if compact_keyword in _compact(haystacks["keywords"]):
            score += 3
        if compact_keyword in _compact(haystacks["summary"]):
            score += 1
        if compact_keyword in _compact(haystacks["page_type"]):
            score += 0.5
    return score


def _dedupe_refs(refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for ref in refs:
        key = (str(ref.get("document_id", "")), str(ref.get("fragment_id", "")))
        if key in seen:
            continue
        seen.add(key)
        result.append(ref)
    return result


def _dedupe_texts(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = str(value).strip()
        compact = _compact(normalized)
        if not normalized or compact in seen:
            continue
        seen.add(compact)
        result.append(normalized)
    return result


def _compact(value: str) -> str:
    return re.sub(r"[\s:：、，。；（）()【】\[\]“”\"'·\-_/]+", "", value.lower())


def main() -> None:
    parser = argparse.ArgumentParser(description="Build machine indexes for Wiki query.")
    parser.add_argument("--index-dir", help="Optional index output directory.")
    args = parser.parse_args()

    paths = build_index(index_dir=Path(args.index_dir) if args.index_dir else None)
    for name, path in paths.items():
        print(f"INDEX {name} -> {path}")


if __name__ == "__main__":
    main()
