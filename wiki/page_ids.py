"""页面 ID 规范化工具."""

from __future__ import annotations

import re


def canonical_page_id(page_id: str) -> str:
    """将页面 ID 规范化为标准格式."""
    # 转换为小写，替换空格和特殊字符
    normalized = page_id.lower().strip()
    normalized = re.sub(r'[\s_]+', '-', normalized)
    normalized = re.sub(r'[^a-z0-9\-\u4e00-\u9fa5]', '', normalized)
    return normalized


def is_legacy_page_id(page_id: str) -> bool:
    """检查是否为旧版页面 ID 格式."""
    # 如果包含大写字母或特殊字符，认为是旧格式
    return bool(re.search(r'[A-Z_]', page_id))
