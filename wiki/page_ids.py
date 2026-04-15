from __future__ import annotations

LEGACY_PAGE_ID_MAP = {
    "medical-device-production-qms-policy": "医疗器械生产质量管理规范",
    "quality-management-system": "质量管理体系",
    "risk-management": "风险管理",
    "roles-and-responsibilities": "机构与人员职责",
    "document-and-data-management": "文件和数据管理",
    "equipment-management": "设备管理",
    "procurement-and-materials": "采购与原材料管理",
    "product-release": "产品放行",
}


def canonical_page_id(page_id: str) -> str:
    return LEGACY_PAGE_ID_MAP.get(page_id, page_id)


def is_legacy_page_id(page_id: str) -> bool:
    return page_id in LEGACY_PAGE_ID_MAP
