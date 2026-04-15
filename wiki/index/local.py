from __future__ import annotations

import logging
import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from Tool.contracts.canonical import CanonicalDocument, Fragment, load_canonical_document
from Tool.normalizers import normalize_text
from Tool.pipelines.common import PARSED_DIR
from wiki.models.page import WikiPage
from wiki.store.files import PAGE_DIR, load_all_pages, load_published_pages

LOGGER = logging.getLogger(__name__)
TOKEN_RE = re.compile(r"[A-Za-z0-9]+|[\u4e00-\u9fff]+")


@dataclass(slots=True)
class PageHit:
    page_id: str
    title: str
    summary: str
    score: float
    page_type: str
    linked_pages: list[str]


@dataclass(slots=True)
class CitationHit:
    page_id: str
    page_title: str
    document_id: str
    fragment_id: str
    file_name: str
    anchor_label: str
    quote: str
    score: float


class LocalWikiIndex:
    def __init__(
        self,
        *,
        page_dir: str | Path | None = None,
        parsed_dir: str | Path | None = None,
    ) -> None:
        self.page_dir = Path(page_dir) if page_dir else PAGE_DIR
        self.parsed_dir = Path(parsed_dir) if parsed_dir else PARSED_DIR
        self.pages: list[WikiPage] = []
        self.page_lookup: dict[str, WikiPage] = {}
        self.page_ranker = _BM25Ranker([])
        self.page_docs: list[list[str]] = []
        self.fragment_lookup: dict[tuple[str, str], Fragment] = {}
        self.doc_lookup: dict[str, CanonicalDocument] = {}

    def refresh(self) -> "LocalWikiIndex":
        LOGGER.info("开始刷新本地检索索引")
        self.pages = self._load_pages()
        self.page_lookup = {page.page_id: page for page in self.pages}
        self.page_docs = [self._page_tokens(page) for page in self.pages]
        self.page_ranker = _BM25Ranker(self.page_docs)
        self.doc_lookup = self._load_parsed_documents()
        self.fragment_lookup = {}
        for document in self.doc_lookup.values():
            for fragment in document.fragments:
                self.fragment_lookup[(document.document.document_id, fragment.fragment_id)] = fragment
        LOGGER.info(
            "本地检索索引刷新完成：页面=%s，解析文档=%s，片段=%s",
            len(self.pages),
            len(self.doc_lookup),
            len(self.fragment_lookup),
        )
        return self

    def search_pages(self, query: str, *, top_k: int = 5) -> list[PageHit]:
        if not self.pages:
            self.refresh()

        query_tokens = tokenize(query)
        scores = self.page_ranker.score(query_tokens)
        ranked = sorted(
            (
                PageHit(
                    page_id=page.page_id,
                    title=page.title,
                    summary=page.summary,
                    score=score,
                    page_type=page.page_type,
                    linked_pages=list(page.linked_pages),
                )
                for page, score in zip(self.pages, scores)
                if score > 0
            ),
            key=lambda item: item.score,
            reverse=True,
        )
        return ranked[:top_k]

    def collect_citations(
        self,
        query: str,
        page_hits: list[PageHit],
        *,
        top_k: int = 8,
    ) -> list[CitationHit]:
        query_tokens = tokenize(query)
        query_token_set = set(query_tokens)
        candidates: list[tuple[WikiPage, dict, float]] = []
        seen_keys: set[tuple[str, str]] = set()
        for page_hit in page_hits:
            page = self.page_lookup.get(page_hit.page_id)
            if page is None:
                continue
            for ref in page.source_refs:
                key = (ref.get("document_id", ""), ref.get("fragment_id", ""))
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                candidates.append((page, ref, page_hit.score))

        scored: list[CitationHit] = []
        relaxed_pool: list[CitationHit] = []
        for page, ref, page_score in candidates:
            text = self._citation_text(ref)
            tokens = tokenize(f"{page.title} {page.summary} {text}")
            bm25_score = _BM25Ranker([tokens]).score(query_tokens)[0]
            overlap_count = len(query_token_set.intersection(tokens))
            overlap_ratio = overlap_count / max(len(query_token_set), 1)
            page_prior = max(page_score, 0.0)
            score = bm25_score + overlap_ratio + min(page_prior, 5.0) * 0.08
            citation_hit = CitationHit(
                page_id=page.page_id,
                page_title=page.title,
                document_id=ref.get("document_id", ""),
                fragment_id=ref.get("fragment_id", ""),
                file_name=ref.get("file_name", ""),
                anchor_label=ref.get("anchor_label", ""),
                quote=text,
                score=score,
            )
            if bm25_score > 0 or overlap_count > 0:
                scored.append(citation_hit)
            else:
                relaxed_pool.append(citation_hit)

        if not scored and relaxed_pool:
            LOGGER.info("证据片段词项匹配不足，启用页面先验召回补全：候选=%s", len(relaxed_pool))
            scored = list(relaxed_pool)
        elif relaxed_pool and len(scored) < top_k:
            fill_count = min(top_k - len(scored), len(relaxed_pool), 2)
            if fill_count > 0:
                scored.extend(sorted(relaxed_pool, key=lambda item: item.score, reverse=True)[:fill_count])

        ranked = sorted(scored, key=lambda item: item.score, reverse=True)
        return ranked[:top_k]

    def _load_pages(self) -> list[WikiPage]:
        if self.page_dir == PAGE_DIR:
            return load_published_pages()

        if not self.page_dir.exists():
            return []

        import json
        from wiki.models.page import PageSection

        pages: list[WikiPage] = []
        for path in sorted(self.page_dir.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            pages.append(
                WikiPage(
                    page_id=data["page_id"],
                    title=data["title"],
                    page_type=data["page_type"],
                    summary=data.get("summary", ""),
                    sections=[PageSection(**section) for section in data.get("sections", [])],
                    aliases=list(data.get("aliases", [])),
                    source_refs=list(data.get("source_refs", [])),
                    linked_pages=list(data.get("linked_pages", [])),
                    review_status=data.get("review_status", "generated"),
                    page_version=int(data.get("page_version", 1)),
                    updated_at=data.get("updated_at", ""),
                )
            )
        return [page for page in pages if page.review_status == "published"]

    def _load_parsed_documents(self) -> dict[str, CanonicalDocument]:
        if not self.parsed_dir.exists():
            return {}
        docs: dict[str, CanonicalDocument] = {}
        for path in sorted(self.parsed_dir.glob("*.json")):
            document = load_canonical_document(path)
            docs[document.document.document_id] = document
        return docs

    def _page_tokens(self, page: WikiPage) -> list[str]:
        weighted_text_parts: list[str] = []
        weighted_text_parts.extend([page.title] * 4)
        weighted_text_parts.extend(page.aliases * 3)
        if page.summary:
            weighted_text_parts.extend([page.summary] * 2)
        for section in page.sections:
            weighted_text_parts.append(section.heading)
            weighted_text_parts.append(section.content)
        return tokenize(" ".join(weighted_text_parts))

    def _citation_text(self, ref: dict) -> str:
        fragment = self.fragment_lookup.get((ref.get("document_id", ""), ref.get("fragment_id", "")))
        if fragment is not None:
            return fragment.text
        return ref.get("quote", "")


def tokenize(text: str) -> list[str]:
    normalized = normalize_text(text).lower()
    tokens: list[str] = []
    for chunk in TOKEN_RE.findall(normalized):
        if re.fullmatch(r"[\u4e00-\u9fff]+", chunk):
            tokens.append(chunk)
            if len(chunk) > 1:
                tokens.extend(chunk[index:index + 2] for index in range(len(chunk) - 1))
        else:
            tokens.append(chunk)
    return tokens


class _BM25Ranker:
    def __init__(self, docs: list[list[str]], *, k1: float = 1.5, b: float = 0.75) -> None:
        self.docs = docs
        self.k1 = k1
        self.b = b
        self.doc_count = len(docs)
        self.avgdl = sum(len(doc) for doc in docs) / len(docs) if docs else 0.0
        self.term_freqs = [Counter(doc) for doc in docs]
        self.doc_freqs: Counter[str] = Counter()
        for tf in self.term_freqs:
            for token in tf:
                self.doc_freqs[token] += 1

    def score(self, query_tokens: list[str]) -> list[float]:
        if not self.docs or not query_tokens:
            return [0.0 for _ in self.docs]

        query_counter = Counter(query_tokens)
        scores = [0.0 for _ in self.docs]
        for token, query_weight in query_counter.items():
            df = self.doc_freqs.get(token, 0)
            if df == 0:
                continue
            idf = math.log(1 + (self.doc_count - df + 0.5) / (df + 0.5))
            for index, tf in enumerate(self.term_freqs):
                freq = tf.get(token, 0)
                if freq == 0:
                    continue
                doc_len = len(self.docs[index])
                denom = freq + self.k1 * (1 - self.b + self.b * doc_len / (self.avgdl or 1.0))
                scores[index] += query_weight * idf * (freq * (self.k1 + 1) / denom)
        return scores
