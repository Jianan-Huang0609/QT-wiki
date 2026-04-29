from __future__ import annotations

from pathlib import Path
from typing import Any

from wiki.models.page import PageSection, ReviewPackage, UpdateProposal, WikiPage
from wiki.page_ids import canonical_page_id


def save_page_markdown(page: WikiPage, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{canonical_page_id(page.page_id)}.md"
    path.write_text(render_page_markdown(page), encoding="utf-8")
    return path


def save_proposal_markdown(proposal: UpdateProposal, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{proposal.proposal_id}.md"
    path.write_text(render_proposal_markdown(proposal), encoding="utf-8")
    return path


def save_review_package_markdown(review_package: ReviewPackage, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{review_package.package_id}.md"
    path.write_text(render_review_package_markdown(review_package), encoding="utf-8")
    return path


def render_page_markdown(page: WikiPage) -> str:
    refs = _dedupe_refs([*page.source_refs, *_section_refs(page.sections)])
    lines = [
        "---",
        f"page_id: {_yaml_scalar(canonical_page_id(page.page_id))}",
        f"title: {_yaml_scalar(page.title)}",
        f"page_type: {_yaml_scalar(page.page_type)}",
        f"review_status: {_yaml_scalar(page.review_status)}",
        f"page_version: {page.page_version}",
        f"updated_at: {_yaml_scalar(page.updated_at)}",
        *_yaml_sequence("aliases", page.aliases),
        *_yaml_sequence("linked_pages", [canonical_page_id(page_id) for page_id in page.linked_pages]),
        "source_refs:",
        *_yaml_ref_list(refs),
        "---",
        "",
        f"# {page.title}",
        "",
        "## 摘要",
        "",
        page.summary or "暂无摘要。",
    ]

    for section in page.sections:
        lines.extend(["", f"## {section.heading}", "", section.content or "暂无内容。"])
        section_ref_ids = _ref_ids(section.source_refs, refs)
        if section_ref_ids:
            lines.extend(["", f"来源: {', '.join(f'[^src-{index}]' for index in section_ref_ids)}"])

    if page.linked_pages:
        lines.extend(["", "## 关联页面", ""])
        lines.extend(f"- [[{page_id}]]" for page_id in page.linked_pages)

    lines.extend(["", "## 引用来源", ""])
    if refs:
        lines.extend(_footnote_lines(refs))
    else:
        lines.append("暂无来源。")

    return _trim_trailing_blank_lines(lines)


def render_proposal_markdown(proposal: UpdateProposal) -> str:
    refs = _dedupe_refs(proposal.source_refs)
    lines = [
        "---",
        f"proposal_id: {_yaml_scalar(proposal.proposal_id)}",
        f"target_page_id: {_yaml_scalar(canonical_page_id(proposal.target_page_id))}",
        f"action: {_yaml_scalar(proposal.action)}",
        f"risk_level: {_yaml_scalar(proposal.risk_level)}",
        f"status: {_yaml_scalar(proposal.status)}",
        *_yaml_sequence("source_document_ids", proposal.source_document_ids),
        *_yaml_sequence("evidence_fragment_ids", proposal.evidence_fragment_ids),
        "source_refs:",
        *_yaml_ref_list(refs),
        "---",
        "",
        f"# 提案: {proposal.target_page_id}",
        "",
        "## 变更原因",
        "",
        proposal.reason or "暂无说明。",
        "",
        "## 候选内容",
        "",
        proposal.candidate_content or "暂无内容。",
        "",
        "## 审核信息",
        "",
        f"- 风险等级: {proposal.risk_level}",
        f"- 状态: {proposal.status}",
    ]
    if proposal.review_notes:
        lines.append(f"- 审核备注: {proposal.review_notes}")

    lines.extend(["", "## 引用来源", ""])
    if refs:
        lines.extend(_footnote_lines(refs))
    else:
        lines.append("暂无来源。")

    return _trim_trailing_blank_lines(lines)


def render_review_package_markdown(review_package: ReviewPackage) -> str:
    refs = _dedupe_refs([*review_package.evidence_refs, *review_package.document_identity.source_refs])
    identity = review_package.document_identity
    lines = [
        "---",
        f"package_id: {_yaml_scalar(review_package.package_id)}",
        f"document_id: {_yaml_scalar(review_package.document_id)}",
        f"status: {_yaml_scalar(review_package.status)}",
        f"identity_decision: {_yaml_scalar(review_package.identity_decision)}",
        f"relation_decision: {_yaml_scalar(review_package.relation_decision)}",
        f"business_type: {_yaml_scalar(identity.business_type)}",
        f"is_binding: {str(identity.is_binding).lower()}",
        f"confidence: {identity.confidence:.3f}",
        *_yaml_sequence("candidate_page_titles", review_package.candidate_page_titles),
        "source_refs:",
        *_yaml_ref_list(refs),
        "---",
        "",
        f"# 审批包: {identity.title or review_package.document_id}",
        "",
        "## 文档身份",
        "",
        f"- 类型: {identity.business_type}",
        f"- 效力: {identity.effective_level or '待确认'}",
        f"- 版本: {identity.version or '待确认'}",
        f"- 适用范围: {identity.scope or '待确认'}",
        f"- 是否强约束: {'是' if identity.is_binding else '否'}",
        f"- 置信度: {identity.confidence:.2f}",
        "",
        "## 人工确认结果",
        "",
        f"- 决策状态: {review_package.identity_decision}",
        f"- 确认类型: {review_package.confirmed_business_type or '待确认'}",
        f"- 确认效力: {review_package.confirmed_effective_level or '待确认'}",
        f"- 确认强约束: {_confirmed_binding_text(review_package.confirmed_is_binding)}",
        f"- 审核人: {review_package.reviewed_by or '待填写'}",
        f"- 审核时间: {review_package.reviewed_at or '待填写'}",
        "",
        "## 关系确认结果",
        "",
        f"- 决策状态: {review_package.relation_decision}",
        f"- 审核人: {review_package.relation_reviewed_by or '待填写'}",
        f"- 审核时间: {review_package.relation_reviewed_at or '待填写'}",
        "",
        "## 证据摘要",
        "",
    ]
    if review_package.evidence_refs:
        lines.extend(_render_ref_digest(review_package.evidence_refs))
    else:
        lines.append("暂无证据摘要。")

    lines.extend(["", "## 待人工确认", ""])
    if review_package.human_questions:
        for question in review_package.human_questions:
            lines.append(f"- {question.question}")
            lines.append(f"  理由: {question.rationale}")
    else:
        lines.append("暂无。")

    lines.extend(["", "## 风险与缺口", ""])
    if review_package.issues:
        for issue in review_package.issues:
            lines.append(f"- [{issue.severity}] {issue.detail}")
    else:
        lines.append("暂无。")

    lines.extend(["", "## 抽取对象", ""])
    if review_package.extracted_objects:
        for item in review_package.extracted_objects:
            lines.append(f"- [{item.object_type}] {item.name}")
    else:
        lines.append("暂无。")

    lines.extend(["", "## 抽取关系", ""])
    if review_package.extracted_relations:
        for item in review_package.extracted_relations:
            lines.append(f"- [{item.relation_type}] {item.from_object_id} -> {item.to_object_id}")
    else:
        lines.append("暂无。")

    if review_package.review_notes:
        lines.extend(["", "## 审核备注", "", review_package.review_notes])
    if review_package.relation_review_notes:
        lines.extend(["", "## 关系审核备注", "", review_package.relation_review_notes])

    lines.extend(["", "## 候选页面", ""])
    if review_package.candidate_page_titles:
        lines.extend(f"- {title}" for title in review_package.candidate_page_titles)
    else:
        lines.append("暂无。")

    lines.extend(["", "## 引用来源", ""])
    if refs:
        lines.extend(_footnote_lines(refs))
    else:
        lines.append("暂无来源。")

    return _trim_trailing_blank_lines(lines)


def _section_refs(sections: list[PageSection]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for section in sections:
        refs.extend(section.source_refs)
    return refs


def _dedupe_refs(refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for ref in refs:
        key = (
            str(ref.get("document_id", "")),
            str(ref.get("fragment_id", "")),
            str(ref.get("anchor_label", "")),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(dict(ref))
    return result


def _ref_ids(section_refs: list[dict[str, Any]], all_refs: list[dict[str, Any]]) -> list[int]:
    ids: list[int] = []
    ref_keys = [_ref_key(ref) for ref in all_refs]
    for ref in section_refs:
        key = _ref_key(ref)
        if key in ref_keys:
            ids.append(ref_keys.index(key) + 1)
    return ids


def _ref_key(ref: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(ref.get("document_id", "")),
        str(ref.get("fragment_id", "")),
        str(ref.get("anchor_label", "")),
    )


def _yaml_ref_list(refs: list[dict[str, Any]]) -> list[str]:
    if not refs:
        return ["  []"]
    lines: list[str] = []
    for ref in refs:
        lines.append(f"  - document_id: {_yaml_scalar(str(ref.get('document_id', '')))}")
        for key in ("fragment_id", "file_name", "anchor_label", "quote"):
            value = ref.get(key)
            if value not in (None, ""):
                lines.append(f"    {key}: {_yaml_scalar(str(value))}")
    return lines


def _yaml_sequence(key: str, values: list[str]) -> list[str]:
    if not values:
        return [f"{key}: []"]
    return [f"{key}:", *[f"  - {_yaml_scalar(str(value))}" for value in values]]


def _yaml_scalar(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{escaped}"'


def _footnote_lines(refs: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for index, ref in enumerate(refs, 1):
        parts = [
            ref.get("document_id", ""),
            ref.get("fragment_id", ""),
            ref.get("anchor_label", ""),
            ref.get("file_name", ""),
        ]
        source = " / ".join(str(part) for part in parts if part)
        quote = str(ref.get("quote", "")).strip()
        line = f"[^src-{index}]: `{source}`"
        if quote:
            line += f" - {quote}"
        lines.append(line)
    return lines


def _render_ref_digest(refs: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for ref in refs[:8]:
        anchor = ref.get("anchor_label", "") or ref.get("fragment_id", "")
        quote = str(ref.get("quote", "")).strip() or "暂无摘录。"
        lines.append(f"- {anchor}: {quote}")
    return lines


def _confirmed_binding_text(value: bool | None) -> str:
    if value is None:
        return "待确认"
    return "是" if value else "否"


def _trim_trailing_blank_lines(lines: list[str]) -> str:
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines) + "\n"
