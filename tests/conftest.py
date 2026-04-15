from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def tmp_dir():
    dirpath = tempfile.mkdtemp()
    yield Path(dirpath)
    shutil.rmtree(dirpath, ignore_errors=True)


@pytest.fixture
def sample_config_data():
    return {
        "provider": "azure_openai",
        "azure_api_key": "test-key-12345",
        "azure_endpoint": "https://test-endpoint.example.com",
        "azure_deployment": "gpt-4o",
        "model": "gpt-4o",
        "api_version": "2024-02-01",
        "max_tokens": 4000,
        "temperature": 0.2,
    }


@pytest.fixture
def sample_config_file(tmp_dir, sample_config_data):
    config_path = tmp_dir / "azure_gpt4o_config.json"
    config_path.write_text(json.dumps(sample_config_data, ensure_ascii=False), encoding="utf-8")
    return config_path


@pytest.fixture
def sample_manifest():
    return {
        "document_id": "doc-test-0001-abcd1234",
        "title": "测试文档",
        "file_name": "test.docx",
        "stored_path": "Raw/test.docx",
        "mime_type": "application/vnd.openxmlformats.officedocument.wordprocessingml.document",
        "source_system": "manual_cli",
        "biz_domain": "medical-device-qms",
        "department": "quality",
        "owner": "qa-team",
        "confidentiality": "internal",
        "version": "v1",
        "checksum": "abcd1234" + "e" * 56,
        "ingested_at": "2026-04-14T14:00:00",
        "parse_status": "pending",
        "parsed_output": None,
        "manifest_path": "Raw/manifests/doc-test-0001-abcd1234.json",
    }


@pytest.fixture
def sample_canonical_dict():
    return {
        "document": {
            "document_id": "doc-test-0001-abcd1234",
            "title": "医疗器械生产质量管理规范",
            "source_path": "Raw/test.docx",
            "file_name": "test.docx",
            "source_type": "docx",
            "doc_type": "policy",
            "language": "zh-CN",
            "checksum": "abcd1234" + "e" * 56,
            "metadata": {},
        },
        "sections": [
            {"section_id": "sec-1", "title": "第一章 总则", "level": 1, "page_range": [], "parent_id": None},
        ],
        "fragments": [
            {
                "fragment_id": "frag-1",
                "section_id": "sec-1",
                "fragment_type": "paragraph",
                "text": "企业应当建立质量管理体系并保持其有效性。",
                "anchors": {"paragraph_index": 1},
            },
            {
                "fragment_id": "frag-2",
                "section_id": "sec-1",
                "fragment_type": "paragraph",
                "text": "风险管理应当贯穿产品全生命周期。",
                "anchors": {"paragraph_index": 2},
            },
        ],
        "tables": [],
        "figures": [],
        "terms": ["质量管理体系", "风险管理"],
        "entities": [],
        "parse_status": "parsed",
        "source_anchors": [
            {"fragment_id": "frag-1", "anchors": {"paragraph_index": 1}},
            {"fragment_id": "frag-2", "anchors": {"paragraph_index": 2}},
        ],
        "errors": [],
    }


@pytest.fixture
def sample_canonical_pdf_dict():
    return {
        "document": {
            "document_id": "doc-test-0002-efgh5678",
            "title": "质量管理体系培训讲义",
            "source_path": "Raw/training.pdf",
            "file_name": "training.pdf",
            "source_type": "pdf",
            "doc_type": "guidance",
            "language": "zh-CN",
            "checksum": "efgh5678" + "f" * 56,
            "metadata": {},
        },
        "sections": [
            {"section_id": "sec-1", "title": "第一章 质量管理体系基础知识", "level": 1, "page_range": [1, 3], "parent_id": None},
        ],
        "fragments": [
            {
                "fragment_id": "frag-1",
                "section_id": "sec-1",
                "fragment_type": "paragraph",
                "text": "质量管理体系是企业确保产品符合法规要求的核心框架。",
                "anchors": {"page": 1, "paragraph_index": 1},
            },
            {
                "fragment_id": "frag-2",
                "section_id": "sec-1",
                "fragment_type": "paragraph",
                "text": "风险管理是质量管理体系的重要组成部分。",
                "anchors": {"page": 2, "paragraph_index": 1},
            },
        ],
        "tables": [],
        "figures": [],
        "terms": ["质量管理体系", "风险管理"],
        "entities": [],
        "parse_status": "parsed",
        "source_anchors": [
            {"fragment_id": "frag-1", "anchors": {"page": 1, "paragraph_index": 1}},
            {"fragment_id": "frag-2", "anchors": {"page": 2, "paragraph_index": 1}},
        ],
        "errors": [],
    }


@pytest.fixture
def parsed_dir_with_docs(tmp_dir, sample_canonical_dict, sample_canonical_pdf_dict):
    parsed_dir = tmp_dir / "parsed"
    parsed_dir.mkdir()
    (parsed_dir / "doc-test-0001-abcd1234.json").write_text(
        json.dumps(sample_canonical_dict, ensure_ascii=False), encoding="utf-8"
    )
    (parsed_dir / "doc-test-0002-efgh5678.json").write_text(
        json.dumps(sample_canonical_pdf_dict, ensure_ascii=False), encoding="utf-8"
    )
    return parsed_dir


@pytest.fixture
def wiki_output_dirs(tmp_dir):
    pages_dir = tmp_dir / "pages"
    proposals_dir = tmp_dir / "proposals"
    pages_dir.mkdir()
    proposals_dir.mkdir()
    return pages_dir, proposals_dir
