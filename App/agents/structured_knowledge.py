from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from wiki.models import ReviewObject, ReviewPackage
from wiki.store import list_review_packages


def approved_review_packages() -> list[ReviewPackage]:
    return [item for item in list_review_packages() if is_review_package_approved(item)]


def is_review_package_approved(review_package: ReviewPackage) -> bool:
    if review_package.identity_decision != "confirmed":
        return False
    if not getattr(review_package, "extracted_relations", []):
        return True
    return review_package.relation_decision in {"confirmed", "not_applicable"}


def normalize_name(value: str) -> str:
    lowered = str(value or "").strip().lower()
    return re.sub(r"[\W_]+", "", lowered, flags=re.UNICODE)


def flatten_relations(review_packages: list[ReviewPackage] | None = None) -> list[dict[str, Any]]:
    packages = approved_review_packages() if review_packages is None else [
        item for item in review_packages if is_review_package_approved(item)
    ]
    rows: list[dict[str, Any]] = []
    for package in packages:
        object_lookup = {item.object_id: item for item in getattr(package, "extracted_objects", [])}
        for relation in getattr(package, "extracted_relations", []):
            from_object = object_lookup.get(relation.from_object_id)
            to_object = object_lookup.get(relation.to_object_id)
            rows.append(
                {
                    "package_id": package.package_id,
                    "document_id": package.document_id,
                    "title": package.document_identity.title or package.document_id,
                    "business_type": package.confirmed_business_type or package.document_identity.business_type,
                    "relation_id": relation.relation_id,
                    "relation_type": relation.relation_type,
                    "claim_type": relation.claim_type,
                    "direction": relation.direction,
                    "confidence": relation.confidence,
                    "human_required": relation.human_required,
                    "from_object_id": relation.from_object_id,
                    "from_object_name": from_object.name if from_object else relation.from_object_id,
                    "from_object_type": from_object.object_type if from_object else "unknown",
                    "to_object_id": relation.to_object_id,
                    "to_object_name": to_object.name if to_object else relation.to_object_id,
                    "to_object_type": to_object.object_type if to_object else "unknown",
                    "evidence_refs": list(relation.evidence_refs),
                }
            )
    return rows


def build_structured_context(question: str, *, package_limit: int = 4, relation_limit: int = 12) -> dict[str, Any]:
    packages = approved_review_packages()
    if not packages:
        return {"packages": [], "relations": [], "objects": []}

    ranked_packages = _rank_review_packages(question, packages, limit=package_limit)
    relation_rows = flatten_relations(ranked_packages)
    scored_relations = sorted(
        relation_rows,
        key=lambda item: (_score_relation(question, item), item["confidence"]),
        reverse=True,
    )
    selected_relations = [item for item in scored_relations if _score_relation(question, item) > 0][:relation_limit]
    if not selected_relations:
        selected_relations = scored_relations[:relation_limit]

    selected_objects: list[dict[str, Any]] = []
    seen_object_ids: set[tuple[str, str]] = set()
    for package in ranked_packages:
        for item in getattr(package, "extracted_objects", []):
            key = (package.package_id, item.object_id)
            if key in seen_object_ids:
                continue
            if _score_object(question, item) <= 0 and selected_relations:
                linked = any(
                    rel["package_id"] == package.package_id
                    and (rel["from_object_id"] == item.object_id or rel["to_object_id"] == item.object_id)
                    for rel in selected_relations
                )
                if not linked:
                    continue
            seen_object_ids.add(key)
            selected_objects.append(
                {
                    "package_id": package.package_id,
                    "document_id": package.document_id,
                    "title": package.document_identity.title or package.document_id,
                    "object_id": item.object_id,
                    "object_type": item.object_type,
                    "name": item.name,
                    "confidence": item.confidence,
                    "evidence_refs": list(item.evidence_refs),
                }
            )
            if len(selected_objects) >= 12:
                break
        if len(selected_objects) >= 12:
            break

    return {
        "packages": [
            {
                "package_id": package.package_id,
                "document_id": package.document_id,
                "title": package.document_identity.title or package.document_id,
                "business_type": package.confirmed_business_type or package.document_identity.business_type,
                "relation_count": len(getattr(package, "extracted_relations", [])),
                "object_count": len(getattr(package, "extracted_objects", [])),
                "source_refs": list(getattr(package, "evidence_refs", [])),
            }
            for package in ranked_packages
        ],
        "relations": selected_relations,
        "objects": selected_objects,
    }


def build_mapping_matrix(review_packages: list[ReviewPackage] | None = None) -> dict[str, Any]:
    packages = approved_review_packages() if review_packages is None else [
        item for item in review_packages if is_review_package_approved(item)
    ]
    relations = flatten_relations(packages)

    step_records: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    step_roles: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)

    for relation in relations:
        if relation["relation_type"] == "produces" and relation["from_object_type"] == "process_step":
            step_key = normalize_name(relation["from_object_name"])
            record_key = normalize_name(relation["to_object_name"])
            if step_key and record_key:
                step_records[step_key][record_key] = _named_item(
                    relation["to_object_name"],
                    relation["to_object_type"],
                    relation["document_id"],
                    relation["title"],
                )
        if relation["relation_type"] == "responsible_for" and relation["to_object_type"] == "process_step":
            step_key = normalize_name(relation["to_object_name"])
            role_key = normalize_name(relation["from_object_name"])
            if step_key and role_key:
                step_roles[step_key][role_key] = _named_item(
                    relation["from_object_name"],
                    relation["from_object_type"],
                    relation["document_id"],
                    relation["title"],
                )

    rows: dict[str, dict[str, Any]] = {}
    for relation in relations:
        requirement_name, requirement_type, step_name, step_type = _requirement_step_pair(relation)
        if not requirement_name or not step_name:
            continue

        requirement_key = normalize_name(requirement_name) or relation["from_object_id"]
        step_key = normalize_name(step_name)
        row = rows.setdefault(
            requirement_key,
            {
                "requirement_name": requirement_name,
                "requirement_type": requirement_type,
                "source_documents": set(),
                "source_packages": set(),
                "claim_types": set(),
                "mapped_process_steps": {},
                "mapped_records": {},
                "mapped_roles": {},
                "evidence_refs": [],
            },
        )

        row["source_documents"].add(relation["document_id"])
        row["source_packages"].add(relation["title"])
        row["claim_types"].add(relation["claim_type"])
        row["mapped_process_steps"][step_key] = _named_item(
            step_name,
            step_type,
            relation["document_id"],
            relation["title"],
        )
        for item_key, item in step_records.get(step_key, {}).items():
            row["mapped_records"][item_key] = item
        for item_key, item in step_roles.get(step_key, {}).items():
            row["mapped_roles"][item_key] = item
        for ref in relation["evidence_refs"]:
            if ref not in row["evidence_refs"]:
                row["evidence_refs"].append(ref)

    matrix_rows = [
        {
            "requirement_name": row["requirement_name"],
            "requirement_type": row["requirement_type"],
            "source_documents": sorted(row["source_documents"]),
            "source_packages": sorted(row["source_packages"]),
            "claim_types": sorted(row["claim_types"]),
            "mapped_process_steps": sorted(row["mapped_process_steps"].values(), key=lambda item: item["name"]),
            "mapped_records": sorted(row["mapped_records"].values(), key=lambda item: item["name"]),
            "mapped_roles": sorted(row["mapped_roles"].values(), key=lambda item: item["name"]),
            "evidence_refs": row["evidence_refs"][:6],
        }
        for row in rows.values()
    ]
    matrix_rows.sort(key=lambda item: (item["requirement_name"], item["requirement_type"]))

    return {
        "generated_at": _generated_at(packages),
        "package_count": len(packages),
        "relation_count": len(relations),
        "row_count": len(matrix_rows),
        "rows": matrix_rows,
    }


def build_slides_outline(review_packages: list[ReviewPackage] | None = None) -> dict[str, Any]:
    packages = approved_review_packages() if review_packages is None else [
        item for item in review_packages if is_review_package_approved(item)
    ]
    matrix = build_mapping_matrix(packages)
    relations = flatten_relations(packages)
    business_type_counts: dict[str, int] = defaultdict(int)
    for item in packages:
        business_type = item.confirmed_business_type or item.document_identity.business_type or "unknown"
        business_type_counts[business_type] += 1

    top_rows = matrix["rows"][:5]
    slides = [
        {
            "title": "批准知识基线",
            "bullets": [
                f"已批准审批包 {len(packages)} 个",
                f"结构化关系 {len(relations)} 条",
                f"要求映射矩阵 {matrix['row_count']} 行",
            ],
        },
        {
            "title": "文档身份分布",
            "bullets": [f"{name}: {count} 个" for name, count in sorted(business_type_counts.items())] or ["暂无已批准文档"],
        },
        {
            "title": "关键要求到流程映射",
            "bullets": [
                _mapping_row_bullet(row)
                for row in top_rows
            ] or ["暂无可展示的要求映射"],
        },
        {
            "title": "记录与职责覆盖",
            "bullets": [
                _coverage_bullet(row)
                for row in top_rows
            ] or ["暂无记录或职责覆盖数据"],
        },
        {
            "title": "持续复核边界",
            "bullets": _boundary_bullets(packages, relations),
        },
    ]

    markdown_lines = ["# Slides Outline", ""]
    for index, slide in enumerate(slides, 1):
        markdown_lines.append(f"## {index}. {slide['title']}")
        for bullet in slide["bullets"]:
            markdown_lines.append(f"- {bullet}")
        markdown_lines.append("")

    return {
        "generated_at": _generated_at(packages),
        "package_count": len(packages),
        "slide_count": len(slides),
        "slides": slides,
        "markdown": "\n".join(markdown_lines).strip(),
    }


def _rank_review_packages(question: str, review_packages: list[ReviewPackage], *, limit: int) -> list[ReviewPackage]:
    scored = sorted(
        review_packages,
        key=lambda item: (_score_package(question, item), item.updated_at or item.created_at, item.package_id),
        reverse=True,
    )
    selected = [item for item in scored if _score_package(question, item) > 0][:limit]
    return selected or scored[:limit]


def _score_package(question: str, review_package: ReviewPackage) -> float:
    normalized_question = normalize_name(question)
    score = 0.0
    title = review_package.document_identity.title or review_package.document_id
    title_key = normalize_name(title)
    if title_key and (title_key in normalized_question or normalized_question in title_key):
        score += 8.0

    business_type = review_package.confirmed_business_type or review_package.document_identity.business_type
    if business_type and business_type in question:
        score += 2.0

    for item in getattr(review_package, "extracted_objects", []):
        score += _score_object(question, item)

    for relation in getattr(review_package, "extracted_relations", []):
        score += _score_relation(
            question,
            {
                "relation_type": relation.relation_type,
                "from_object_name": relation.from_object_id,
                "to_object_name": relation.to_object_id,
            },
        )

    if any(token in question for token in ("映射", "关系", "对应", "步骤", "记录", "职责", "要求")):
        score += min(len(getattr(review_package, "extracted_relations", [])) * 0.2, 2.0)
    return score


def _score_object(question: str, review_object: ReviewObject) -> float:
    question_key = normalize_name(question)
    name_key = normalize_name(review_object.name)
    if not question_key or not name_key:
        return 0.0
    if name_key in question_key or question_key in name_key:
        return 5.0
    return 0.0


def _score_relation(question: str, relation: dict[str, Any]) -> float:
    question_key = normalize_name(question)
    from_key = normalize_name(relation.get("from_object_name", ""))
    to_key = normalize_name(relation.get("to_object_name", ""))
    score = 0.0
    if from_key and from_key in question_key:
        score += 3.0
    if to_key and to_key in question_key:
        score += 3.0
    relation_type = str(relation.get("relation_type", "")).strip().lower()
    relation_keywords = {
        "requires": ("要求", "对应", "映射"),
        "produces": ("产出", "输出", "记录"),
        "responsible_for": ("负责", "职责", "角色"),
        "implements": ("实现", "满足"),
        "constrains": ("约束", "限制"),
    }
    if any(token in question for token in relation_keywords.get(relation_type, ())):
        score += 2.0
    return score


def _requirement_step_pair(relation: dict[str, Any]) -> tuple[str, str, str, str]:
    relation_type = relation["relation_type"]
    from_type = relation["from_object_type"]
    to_type = relation["to_object_type"]
    if relation_type == "requires" and from_type in {"requirement", "regulation_clause"} and to_type == "process_step":
        return relation["from_object_name"], from_type, relation["to_object_name"], to_type
    if relation_type == "implements" and from_type == "process_step" and to_type in {"requirement", "regulation_clause"}:
        return relation["to_object_name"], to_type, relation["from_object_name"], from_type
    return "", "", "", ""


def _named_item(name: str, object_type: str, document_id: str, source_package: str) -> dict[str, Any]:
    return {
        "name": name,
        "object_type": object_type,
        "document_id": document_id,
        "source_package": source_package,
    }


def _mapping_row_bullet(row: dict[str, Any]) -> str:
    step_names = "、".join(item["name"] for item in row["mapped_process_steps"][:3]) or "暂无流程步骤"
    return f"{row['requirement_name']} -> {step_names}"


def _coverage_bullet(row: dict[str, Any]) -> str:
    record_names = "、".join(item["name"] for item in row["mapped_records"][:2]) or "暂无记录"
    role_names = "、".join(item["name"] for item in row["mapped_roles"][:2]) or "暂无职责角色"
    return f"{row['requirement_name']}: 记录 {record_names}; 角色 {role_names}"


def _boundary_bullets(packages: list[ReviewPackage], relations: list[dict[str, Any]]) -> list[str]:
    bullets: list[str] = []
    high_risk = [item for item in relations if item["human_required"]]
    if high_risk:
        bullets.append(f"仍需持续关注的高风险关系 {len(high_risk)} 条，后续扩展跨文档映射时应优先复核。")
    for item in packages[:3]:
        if item.review_notes:
            bullets.append(f"{item.document_identity.title or item.document_id}: {item.review_notes}")
        elif item.relation_review_notes:
            bullets.append(f"{item.document_identity.title or item.document_id}: {item.relation_review_notes}")
    return bullets or ["当前没有额外的边界提示。"]


def _generated_at(packages: list[ReviewPackage]) -> str:
    timestamps = [item.updated_at for item in packages if item.updated_at]
    return max(timestamps) if timestamps else ""
