from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class ValidationError:
    """校验错误"""
    field: str
    message: str
    code: str = "invalid"


@dataclass
class ValidationResult:
    """校验结果"""
    is_valid: bool
    errors: list[ValidationError]

    @property
    def error_messages(self) -> list[str]:
        return [f"{e.field}: {e.message}" for e in self.errors]


class DocumentValidator:
    """文档校验器"""

    ALLOWED_EXTENSIONS = {".pdf", ".docx", ".pptx", ".xlsx", ".txt", ".md"}
    MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB

    @classmethod
    def validate_file(cls, file_path: str | Path) -> ValidationResult:
        """验证文件"""
        errors: list[ValidationError] = []
        path = Path(file_path)

        if not path.exists():
            errors.append(ValidationError("file", "文件不存在", "not_found"))
            return ValidationResult(False, errors)

        if not path.is_file():
            errors.append(ValidationError("file", "路径不是文件", "not_file"))
            return ValidationResult(False, errors)

        ext = path.suffix.lower()
        if ext not in cls.ALLOWED_EXTENSIONS:
            errors.append(
                ValidationError(
                    "file",
                    f"不支持的文件类型: {ext}，支持的类型: {', '.join(cls.ALLOWED_EXTENSIONS)}",
                    "invalid_extension"
                )
            )

        size = path.stat().st_size
        if size > cls.MAX_FILE_SIZE:
            errors.append(
                ValidationError(
                    "file",
                    f"文件大小超过限制: {size / 1024 / 1024:.1f}MB > {cls.MAX_FILE_SIZE / 1024 / 1024}MB",
                    "file_too_large"
                )
            )

        if size == 0:
            errors.append(ValidationError("file", "文件为空", "empty_file"))

        return ValidationResult(len(errors) == 0, errors)


class PageIdValidator:
    """页面ID校验器"""

    PAGE_ID_PATTERN = re.compile(r"^[\w\-\u4e00-\u9fa5]+$")
    RESERVED_IDS = {
        "health", "api", "docs", "static", "admin",
        "index", "home", "search", "new", "edit", "delete"
    }

    @classmethod
    def validate(cls, page_id: str) -> ValidationResult:
        """验证页面ID"""
        errors: list[ValidationError] = []

        if not page_id:
            errors.append(ValidationError("page_id", "页面ID不能为空", "required"))
            return ValidationResult(False, errors)

        if len(page_id) > 100:
            errors.append(ValidationError("page_id", "页面ID长度不能超过100个字符", "too_long"))

        if not cls.PAGE_ID_PATTERN.match(page_id):
            errors.append(
                ValidationError(
                    "page_id",
                    "页面ID只能包含字母、数字、下划线、连字符和中文字符",
                    "invalid_format"
                )
            )

        if page_id.lower() in cls.RESERVED_IDS:
            errors.append(
                ValidationError(
                    "page_id",
                    f"页面ID '{page_id}' 是保留字，不能使用",
                    "reserved_id"
                )
            )

        return ValidationResult(len(errors) == 0, errors)


class SourceRefValidator:
    """来源引用校验器"""

    @classmethod
    def validate(cls, source_ref: dict[str, Any]) -> ValidationResult:
        """验证来源引用"""
        errors: list[ValidationError] = []

        document_id = source_ref.get("document_id", "")
        if not document_id or not str(document_id).strip():
            errors.append(ValidationError("document_id", "文档ID不能为空", "required"))

        quote = source_ref.get("quote", "")
        if quote and len(str(quote)) > 2000:
            errors.append(ValidationError("quote", "引用内容不能超过2000个字符", "too_long"))

        return ValidationResult(len(errors) == 0, errors)


class WikiPageValidator:
    """Wiki页面校验器"""

    @classmethod
    def validate(cls, page_data: dict[str, Any]) -> ValidationResult:
        """验证Wiki页面数据"""
        errors: list[ValidationError] = []

        page_id = page_data.get("page_id", "")
        result = PageIdValidator.validate(page_id)
        errors.extend(result.errors)

        title = page_data.get("title", "")
        if not title:
            errors.append(ValidationError("title", "标题不能为空", "required"))
        elif len(str(title)) > 200:
            errors.append(ValidationError("title", "标题长度不能超过200个字符", "too_long"))

        summary = page_data.get("summary", "")
        if len(str(summary)) > 2000:
            errors.append(ValidationError("summary", "摘要长度不能超过2000个字符", "too_long"))

        page_type = page_data.get("page_type", "")
        valid_types = {"overview", "entity", "concept", "comparison", "index"}
        if page_type and page_type not in valid_types:
            errors.append(
                ValidationError(
                    "page_type",
                    f"无效的页面类型: {page_type}，有效类型: {', '.join(valid_types)}",
                    "invalid_type"
                )
            )

        source_refs = page_data.get("source_refs", [])
        for idx, ref in enumerate(source_refs):
            result = SourceRefValidator.validate(ref)
            for error in result.errors:
                errors.append(
                    ValidationError(
                        f"source_refs[{idx}].{error.field}",
                        error.message,
                        error.code
                    )
                )

        linked_pages = page_data.get("linked_pages", [])
        for idx, linked_id in enumerate(linked_pages):
            if linked_id == page_id:
                errors.append(
                    ValidationError(
                        f"linked_pages[{idx}]",
                        "页面不能链接到自身",
                        "self_reference"
                    )
                )

        return ValidationResult(len(errors) == 0, errors)


class ReviewPackageValidator:
    """审批包校验器"""

    @classmethod
    def validate_decision(cls, data: dict[str, Any]) -> ValidationResult:
        """验证审批决策"""
        errors: list[ValidationError] = []

        decision = data.get("identity_decision", "")
        if decision not in {"confirmed", "needs_revision"}:
            errors.append(
                ValidationError(
                    "identity_decision",
                    "决策必须是 'confirmed' 或 'needs_revision'",
                    "invalid_decision"
                )
            )

        if decision == "confirmed":
            business_type = data.get("confirmed_business_type", "")
            if not business_type:
                errors.append(
                    ValidationError(
                        "confirmed_business_type",
                        "确认决策时，业务类型必填",
                        "required_on_confirm"
                    )
                )

        reviewed_by = data.get("reviewed_by", "")
        if reviewed_by and len(str(reviewed_by)) > 100:
            errors.append(
                ValidationError(
                    "reviewed_by",
                    "审批人名称不能超过100个字符",
                    "too_long"
                )
            )

        review_notes = data.get("review_notes", "")
        if review_notes and len(str(review_notes)) > 2000:
            errors.append(
                ValidationError(
                    "review_notes",
                    "审批备注不能超过2000个字符",
                    "too_long"
                )
            )

        return ValidationResult(len(errors) == 0, errors)


class QueryValidator:
    """查询校验器"""

    MIN_QUESTION_LENGTH = 2
    MAX_QUESTION_LENGTH = 500

    @classmethod
    def validate_question(cls, question: str) -> ValidationResult:
        """验证查询问题"""
        errors: list[ValidationError] = []

        if not question:
            errors.append(ValidationError("question", "问题不能为空", "required"))
            return ValidationResult(False, errors)

        question = question.strip()

        if len(question) < cls.MIN_QUESTION_LENGTH:
            errors.append(
                ValidationError(
                    "question",
                    f"问题至少需要 {cls.MIN_QUESTION_LENGTH} 个字符",
                    "too_short"
                )
            )

        if len(question) > cls.MAX_QUESTION_LENGTH:
            errors.append(
                ValidationError(
                    "question",
                    f"问题不能超过 {cls.MAX_QUESTION_LENGTH} 个字符",
                    "too_long"
                )
            )

        return ValidationResult(len(errors) == 0, errors)

    @classmethod
    def validate_top_k(cls, value: int, name: str, min_val: int = 1, max_val: int = 50) -> ValidationResult:
        """验证top_k参数"""
        errors: list[ValidationError] = []

        if not isinstance(value, int):
            errors.append(ValidationError(name, f"{name} 必须是整数", "invalid_type"))
        elif value < min_val:
            errors.append(
                ValidationError(
                    name,
                    f"{name} 不能小于 {min_val}",
                    "too_small"
                )
            )
        elif value > max_val:
            errors.append(
                ValidationError(
                    name,
                    f"{name} 不能大于 {max_val}",
                    "too_large"
                )
            )

        return ValidationResult(len(errors) == 0, errors)


def validate_all(validators: list[tuple[Any, dict[str, Any]]]) -> ValidationResult:
    """
    批量执行多个校验器

    Args:
        validators: [(validator_class, data), ...]

    Returns:
        合并后的校验结果
    """
    all_errors: list[ValidationError] = []

    for validator_class, data in validators:
        if hasattr(validator_class, 'validate'):
            result = validator_class.validate(data)
            all_errors.extend(result.errors)

    return ValidationResult(len(all_errors) == 0, all_errors)
