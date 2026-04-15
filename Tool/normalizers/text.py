from __future__ import annotations

import hashlib
import re
from collections import Counter


WHITESPACE_RE = re.compile(r"\s+")
SECTION_OR_ARTICLE_RE = re.compile(r"(?=第[一二三四五六七八九十百零〇\d]+[章节条])")
LIST_MARKER_RE = re.compile(r"(?=[（(][一二三四五六七八九十\d]+[)）])")
SENTENCE_BREAK_RE = re.compile(r"(?<=[。；！？])")

DOMAIN_TERMS = [
    "质量管理体系",
    "风险管理",
    "管理者代表",
    "质量管理部门",
    "产品放行",
    "采购与原材料管理",
    "文件和数据管理",
    "设计开发",
    "验证与确认",
    "厂房与设施",
    "设备管理",
    "医疗器械",
]


def normalize_text(text: str) -> str:
    return WHITESPACE_RE.sub(" ", text.replace("\u3000", " ").strip())


def chunk_lines(text: str, *, max_chunk_chars: int = 220) -> list[str]:
    lines = [normalize_text(line) for line in text.splitlines()]
    chunks: list[str] = []
    bucket: list[str] = []
    for line in lines:
        if not line:
            if bucket:
                chunks.append(" ".join(bucket))
                bucket = []
            continue
        for piece in _split_chunk_candidate(line, max_chunk_chars=max_chunk_chars):
            if not piece:
                continue
            if bucket and re.match(r"^第[一二三四五六七八九十百零〇\d]+[章节条]", piece):
                chunks.append(" ".join(bucket))
                bucket = []
            next_length = len(" ".join(bucket + [piece]))
            if bucket and next_length > max_chunk_chars:
                chunks.append(" ".join(bucket))
                bucket = []
            bucket.append(piece)
    if bucket:
        chunks.append(" ".join(bucket))
    return chunks


def _split_chunk_candidate(text: str, *, max_chunk_chars: int) -> list[str]:
    normalized = normalize_text(text)
    pieces = [normalized]
    for splitter in (SECTION_OR_ARTICLE_RE, LIST_MARKER_RE, SENTENCE_BREAK_RE):
        next_pieces: list[str] = []
        changed = False
        for piece in pieces:
            sub_pieces = [segment.strip() for segment in splitter.split(piece) if segment.strip()]
            if len(sub_pieces) > 1:
                changed = True
                next_pieces.extend(sub_pieces)
            else:
                next_pieces.append(piece)
        pieces = next_pieces
        if changed:
            break

    final_pieces: list[str] = []
    for piece in pieces:
        if len(piece) <= max_chunk_chars:
            final_pieces.append(piece)
            continue
        start = 0
        while start < len(piece):
            final_pieces.append(piece[start:start + max_chunk_chars].strip())
            start += max_chunk_chars
    return [piece for piece in final_pieces if piece]


def stable_slug(text: str, prefix: str) -> str:
    lowered = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    if lowered:
        return f"{prefix}-{lowered}"
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]
    return f"{prefix}-{digest}"


def detect_doc_type(title: str, file_name: str) -> str:
    source = f"{title} {file_name}"
    if any(keyword in source for keyword in ("理解和实施", "培训", "讲义")):
        return "guidance"
    if any(keyword in source for keyword in ("规范", "条例", "办法")):
        return "policy"
    if file_name.lower().endswith(".pptx"):
        return "presentation"
    if file_name.lower().endswith(".xlsx"):
        return "spreadsheet"
    return "general"


def extract_terms(texts: list[str], *, limit: int = 12) -> list[str]:
    hits = [term for term in DOMAIN_TERMS if any(term in text for text in texts)]
    if len(hits) >= limit:
        return hits[:limit]

    counter = Counter()
    for text in texts:
        for token in re.findall(r"[\u4e00-\u9fff]{4,12}", text):
            counter[token] += 1

    for token, _ in counter.most_common(limit * 3):
        if token not in hits:
            hits.append(token)
        if len(hits) >= limit:
            break
    return hits[:limit]
