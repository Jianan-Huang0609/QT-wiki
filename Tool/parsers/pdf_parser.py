from __future__ import annotations

import re
from pathlib import Path

import pypdf

from Tool.contracts.canonical import CanonicalDocument, DocumentMeta, Fragment, Section
from Tool.normalizers import chunk_lines, detect_doc_type, extract_terms, normalize_text

SECTION_RE = re.compile(r"^第[一二三四五六七八九十百零〇\d]+章")
ARTICLE_RE = re.compile(r"^第[一二三四五六七八九十百零〇\d]+条")
DATE_RE = re.compile(r"^\d{4}/\d{1,2}/\d{1,2}$")
PAGE_NO_RE = re.compile(r"^\d{1,3}$")
BULLET_RE = re.compile(r"^(?:[•⚫➢■▪◆\-]|[①②③④⑤⑥⑦⑧⑨⑩]|[（(]?[一二三四五六七八九十\d]+[）).、])")
TITLE_MARKER_RE = re.compile(r"^(?:[•⚫➢■▪◆\-—–]+|[①②③④⑤⑥⑦⑧⑨⑩]+|[（(]?[一二三四五六七八九十\d]+[）).、])\s*")
SLIDE_NUMBER_PREFIX_RE = re.compile(r"^\d+(?:\.\d+){0,3}\s+")
TRAILING_TITLE_PUNCT_RE = re.compile(r"[：:？?！!；;。]+$")
ENGLISH_PAREN_SUFFIX_RE = re.compile(r"\s*[（(][A-Za-z][A-Za-z0-9/_\- ]*[）)]$")
SLIDE_MARKERS = ("分享人", "教师简介", "目录", "理解要点", "本章要点", "框架结构", "章节条款数对比")
STRUCTURAL_SLIDE_MARKERS = ("分享人", "教师简介", "目录", "框架结构", "章节条款数对比")
TITLE_NOISE_LINES = {"理解要点", "本章要点", "目", "录"}
SENTENCE_TITLE_MARKERS = ("应当", "必须", "包括", "如下", "下列", "至少", "记录", "程序", "要求")
GENERIC_SLIDE_TITLES = {"总则", "附则", "概述", "说明", "原则"}
TITLE_NOISE_MARKERS = ("下面引自", "本资料仅限于", "请勿传播", "理解和实施")
THEMATIC_TITLE_MARKERS = (
    "QMS",
    "质量",
    "风险",
    "文件",
    "设备",
    "放行",
    "采购",
    "验证",
    "设计",
    "历程",
    "修订",
    "特点",
    "关系",
    "管理",
    "控制",
    "编写",
    "保证",
    "过程",
    "标准",
    "法规",
    "体系",
    "规范",
)


def parse_pdf(file_path: Path, manifest: dict) -> CanonicalDocument:
    reader = pypdf.PdfReader(str(file_path))
    extracted_pages: list[tuple[int, str]] = []
    errors: list[str] = []

    for page_number, page in enumerate(reader.pages, start=1):
        try:
            extracted_pages.append((page_number, page.extract_text() or ""))
        except Exception as exc:
            errors.append(f"page {page_number}: {exc}")

    if _looks_like_slide_pdf(extracted_pages, title_hint=manifest.get("title", file_path.stem), file_name=file_path.name):
        return _parse_slide_pdf(
            file_path=file_path,
            manifest=manifest,
            extracted_pages=extracted_pages,
            page_count=len(reader.pages),
            errors=errors,
        )

    sections: list[Section] = []
    fragments: list[Fragment] = []
    current_section_id: str | None = None
    section_index = 0
    fragment_index = 0

    for page_number, text in extracted_pages:
        for paragraph_index, chunk in enumerate(chunk_lines(text), start=1):
            if not chunk:
                continue
            if SECTION_RE.match(chunk):
                section_index += 1
                current_section_id = f"sec-{section_index}"
                sections.append(
                    Section(
                        section_id=current_section_id,
                        title=chunk,
                        level=1,
                        page_range=[page_number, page_number],
                    )
                )

            fragment_index += 1
            fragments.append(
                Fragment(
                    fragment_id=f"frag-{fragment_index}",
                    section_id=current_section_id,
                    fragment_type="paragraph",
                    text=normalize_text(chunk),
                    anchors={"page": page_number, "paragraph_index": paragraph_index},
                )
            )

    title = _pick_title(fragments, file_path.stem)
    meta = DocumentMeta(
        document_id=manifest["document_id"],
        title=title,
        source_path=manifest["stored_path"],
        file_name=file_path.name,
        source_type="pdf",
        doc_type=detect_doc_type(title, file_path.name),
        checksum=manifest.get("checksum", ""),
        metadata={"manifest_path": manifest.get("manifest_path", ""), "page_count": len(reader.pages)},
    )

    parse_status = "parsed" if fragments and not errors else "partially_parsed" if fragments else "failed"
    if not fragments and not errors:
        errors.append("No text fragments extracted from PDF.")

    return CanonicalDocument(
        document=meta,
        sections=sections,
        fragments=fragments,
        tables=[],
        figures=[],
        terms=extract_terms([fragment.text for fragment in fragments]),
        entities=[],
        parse_status=parse_status,
        source_anchors=[
            {"fragment_id": fragment.fragment_id, "anchors": fragment.anchors}
            for fragment in fragments
        ],
        errors=errors,
    )


def _parse_slide_pdf(
    *,
    file_path: Path,
    manifest: dict,
    extracted_pages: list[tuple[int, str]],
    page_count: int,
    errors: list[str],
) -> CanonicalDocument:
    sections: list[Section] = []
    fragments: list[Fragment] = []
    skipped_pages: list[int] = []

    for page_number, text in extracted_pages:
        lines = _prepare_slide_lines(text)
        if not lines:
            continue
        if _is_structural_slide(lines):
            skipped_pages.append(page_number)
            continue

        title, title_source = _pick_slide_page_title(lines, fallback=f"第{page_number}页")
        body_lines = _drop_first_occurrence(lines, title_source)
        merged_lines = _merge_slide_lines(body_lines)
        if not merged_lines:
            skipped_pages.append(page_number)
            continue

        section_id = f"slide-{page_number}"
        sections.append(
            Section(
                section_id=section_id,
                title=title,
                level=1,
                page_range=[page_number, page_number],
            )
        )
        for paragraph_index, chunk in enumerate(merged_lines, start=1):
            fragments.append(
                Fragment(
                    fragment_id=f"frag-{page_number}-{paragraph_index}",
                    section_id=section_id,
                    fragment_type="paragraph",
                    text=chunk,
                    anchors={"page": page_number, "paragraph_index": paragraph_index},
                )
            )

    title = _pick_slide_document_title(sections, fragments, fallback=file_path.stem)
    meta = DocumentMeta(
        document_id=manifest["document_id"],
        title=title,
        source_path=manifest["stored_path"],
        file_name=file_path.name,
        source_type="pdf",
        doc_type="presentation",
        checksum=manifest.get("checksum", ""),
        metadata={
            "manifest_path": manifest.get("manifest_path", ""),
            "page_count": page_count,
            "pdf_layout": "slides",
            "skipped_pages": skipped_pages,
        },
    )

    parse_status = "parsed" if fragments and not errors else "partially_parsed" if fragments else "failed"
    if not fragments and not errors:
        errors.append("No text fragments extracted from slide-like PDF.")

    return CanonicalDocument(
        document=meta,
        sections=sections,
        fragments=fragments,
        tables=[],
        figures=[],
        terms=extract_terms([fragment.text for fragment in fragments]),
        entities=[],
        parse_status=parse_status,
        source_anchors=[
            {"fragment_id": fragment.fragment_id, "anchors": fragment.anchors}
            for fragment in fragments
        ],
        errors=errors,
    )


def _looks_like_slide_pdf(extracted_pages: list[tuple[int, str]], *, title_hint: str, file_name: str) -> bool:
    if not extracted_pages:
        return False

    sample_pages = extracted_pages[: min(12, len(extracted_pages))]
    marker_pages = 0
    short_line_pages = 0
    article_pages = 0

    for _, text in sample_pages:
        lines = _prepare_slide_lines(text)
        if not lines:
            continue
        if any(marker in " ".join(lines[:10]) for marker in SLIDE_MARKERS):
            marker_pages += 1
        if len(lines) >= 6:
            short_ratio = sum(1 for line in lines if len(line) <= 30) / len(lines)
            if short_ratio >= 0.6:
                short_line_pages += 1
        if sum(1 for line in lines if ARTICLE_RE.match(line)) >= 2:
            article_pages += 1

    title_source = f"{title_hint} {file_name}"
    title_bias = any(keyword in title_source for keyword in ("理解和实施", "培训", "讲义", "课件"))
    return (
        marker_pages >= 2 and short_line_pages >= 2 and article_pages <= max(2, len(sample_pages) // 4)
    ) or (
        title_bias and marker_pages >= 1 and short_line_pages >= 1
    )


def _prepare_slide_lines(text: str) -> list[str]:
    lines = [normalize_text(line) for line in text.splitlines()]
    lines = [line for line in lines if line]
    if lines and DATE_RE.match(lines[0]):
        lines = lines[1:]
    if lines and PAGE_NO_RE.match(lines[0]):
        lines = lines[1:]
    return [line for line in lines if not PAGE_NO_RE.match(line)]


def _is_structural_slide(lines: list[str]) -> bool:
    preview = " ".join(lines[:12])
    return any(marker in preview for marker in STRUCTURAL_SLIDE_MARKERS)


def _pick_slide_page_title(lines: list[str], *, fallback: str) -> tuple[str, str]:
    candidates = [line for line in lines[:12] if line]
    if not candidates:
        return fallback, fallback

    scored_candidates: list[tuple[int, int, str, str]] = []
    for index, raw_line in enumerate(candidates):
        cleaned_line = _normalize_slide_title_candidate(raw_line)
        score = _slide_title_score(raw_line, cleaned_line, index=index)
        scored_candidates.append((score, -index, cleaned_line, raw_line))

    best_score, _, cleaned_line, raw_line = max(scored_candidates)
    if best_score > 0 and cleaned_line:
        return cleaned_line, raw_line
    return fallback, fallback


def _normalize_slide_title_candidate(line: str) -> str:
    cleaned = TITLE_MARKER_RE.sub("", line).strip()
    cleaned = SLIDE_NUMBER_PREFIX_RE.sub("", cleaned).strip()
    cleaned = ENGLISH_PAREN_SUFFIX_RE.sub("", cleaned).strip()
    cleaned = TRAILING_TITLE_PUNCT_RE.sub("", cleaned).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned


def _slide_title_score(raw_line: str, cleaned_line: str, *, index: int) -> int:
    if not cleaned_line or cleaned_line in TITLE_NOISE_LINES:
        return -10

    score = 0
    if 4 <= len(cleaned_line) <= 28:
        score += 5
    elif len(cleaned_line) <= 45:
        score += 3
    elif len(cleaned_line) <= 60:
        score += 1
    else:
        score -= 2

    score += max(0, 5 - index)

    if raw_line != cleaned_line and len(cleaned_line) <= 24:
        score += 1
    if TITLE_MARKER_RE.match(raw_line):
        score -= 1
    if raw_line.startswith(("—", "——", "–")):
        score -= 2
    if re.match(r"^[A-Za-z][).、]\s*", raw_line):
        score -= 5
    if any(marker in cleaned_line for marker in TITLE_NOISE_MARKERS):
        score -= 6
    if ARTICLE_RE.match(cleaned_line) or SECTION_RE.match(cleaned_line):
        score += 2
    if re.match(r"^\d+(?:\.\d+)*[.、]?", raw_line):
        score += 2
    if cleaned_line.startswith(tuple(str(year) for year in range(1990, 2036))):
        score -= 3
    if any(marker in cleaned_line for marker in SENTENCE_TITLE_MARKERS):
        score -= 3
    if cleaned_line in GENERIC_SLIDE_TITLES:
        score -= 4
    if re.match(r"^(新版|最新)[“\"《]?(规范|制度|标准)[”\"》]?$", cleaned_line):
        score -= 4
    if any(keyword in cleaned_line for keyword in THEMATIC_TITLE_MARKERS):
        score += 2
    if "发展历程" in cleaned_line:
        score += 4
    if re.search(r"(历程|特点|编写|管理|控制|保证|关系|要求|确认)$", cleaned_line):
        score += 2
    return score


def _drop_first_occurrence(lines: list[str], target: str) -> list[str]:
    dropped = False
    result: list[str] = []
    for line in lines:
        if not dropped and line == target:
            dropped = True
            continue
        result.append(line)
    return result


def _merge_slide_lines(lines: list[str], *, max_chunk_chars: int = 260) -> list[str]:
    chunks: list[str] = []
    bucket: list[str] = []

    for line in lines:
        if _is_slide_noise_line(line):
            if bucket:
                chunks.append(" ".join(bucket))
                bucket = []
            continue

        starts_new = bool(bucket) and (
            BULLET_RE.match(line)
            or ARTICLE_RE.match(line)
            or SECTION_RE.match(line)
        )
        next_length = len(" ".join(bucket + [line]))
        if starts_new or (bucket and (_ends_sentence(bucket[-1]) or next_length > max_chunk_chars)):
            chunks.append(" ".join(bucket))
            bucket = [line]
            continue
        bucket.append(line)

    if bucket:
        chunks.append(" ".join(bucket))
    return [chunk for chunk in chunks if len(chunk) >= 8]


def _is_slide_noise_line(line: str) -> bool:
    if not line:
        return True
    if line in {"理解要点", "本章要点", "目", "录", "——", "……"}:
        return True
    return False


def _ends_sentence(text: str) -> bool:
    return text.endswith(("。", "；", "？", "！", ".", ";", ":", "："))


def _pick_slide_document_title(sections: list[Section], fragments: list[Fragment], *, fallback: str) -> str:
    if sections:
        first_title = sections[0].title
        if 6 <= len(first_title) <= 60:
            return first_title
    return _pick_title(fragments, fallback)


def _pick_title(fragments: list[Fragment], fallback: str) -> str:
    for fragment in fragments[:12]:
        text = fragment.text
        if (
            text
            and len(text) >= 6
            and len(text) <= 40
            and not re.match(r"^\d{4}/\d{1,2}/\d{1,2}$", text)
            and not re.match(r"^\d{4}/\d{1,2}/\d{1,2}\s+\d+\s+", text)
            and "分享人" not in text
            and "目录" not in text
            and "本章要点" not in text
            and "章节条款数对比" not in text
            and "变化率" not in text
        ):
            return text
    return fallback
