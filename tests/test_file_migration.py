from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_root_has_no_llm_tool_compat_entry():
    root_file = Path(__file__).resolve().parents[1] / "llm_tool.py"
    assert not root_file.exists(), "根目录 llm_tool.py 已删除，新代码应从 Tool.llm 导入"


def test_new_code_imports_from_package():
    from Tool.llm.client import LLMTool
    from Tool.llm.config import load_config
    from Tool.llm.prompts import build_summary_prompt
    from Tool.llm.types import LLMConfig, ChatRequest
    from Tool.contracts.canonical import CanonicalDocument
    from Tool.parsers import parse_document
    from Tool.normalizers import normalize_text, detect_doc_type
    from Tool.pipelines.common import build_manifest
    from wiki.models.page import WikiPage, UpdateProposal
    from wiki.builders.bootstrap import bootstrap_pages
    from wiki.updaters.incremental import incremental_update
    from wiki.updaters.conflict_scan import conflict_scan
    from wiki.updaters.publish import publish
    from wiki.store.files import save_page, load_page

    assert all([
        LLMTool, load_config, build_summary_prompt,
        LLMConfig, ChatRequest, CanonicalDocument,
        parse_document, normalize_text, detect_doc_type,
        build_manifest, WikiPage, UpdateProposal,
        bootstrap_pages, incremental_update,
        conflict_scan, publish, save_page, load_page,
    ])


def test_output_dirs_separate_from_source():
    from Tool.pipelines.common import PARSED_DIR, REPO_ROOT
    from wiki.store.files import PAGE_DIR, PROPOSAL_DIR

    assert PARSED_DIR.is_relative_to(REPO_ROOT)
    assert "output" in str(PARSED_DIR)
    assert PAGE_DIR.is_relative_to(REPO_ROOT)
    assert "output" in str(PAGE_DIR)
    assert PROPOSAL_DIR.is_relative_to(REPO_ROOT)
    assert "output" in str(PROPOSAL_DIR)


def test_output_dirs_in_gitignore():
    gitignore_path = Path(__file__).resolve().parents[1] / ".gitignore"
    content = gitignore_path.read_text(encoding="utf-8")
    assert "Tool/output/parsed" in content
    assert "wiki/output/pages" in content
    assert "wiki/output/proposals" in content


def test_config_dir_exists():
    from Tool.llm.config import REPO_ROOT

    config_dir = REPO_ROOT / "config"
    assert config_dir.exists()
    assert (config_dir / "azure_gpt4o_config.json").exists()


def test_root_config_removed():
    from Tool.llm.config import REPO_ROOT

    root_config = REPO_ROOT / "azure_gpt4o_config.json"
    assert not root_config.exists(), "根目录配置已删除，配置统一放在 config/ 目录"


def test_raw_manifests_dir_exists():
    from Tool.pipelines.common import MANIFEST_DIR

    assert MANIFEST_DIR.exists()


def test_app_dir_has_readme():
    app_readme = Path(__file__).resolve().parents[1] / "App" / "README.md"
    assert app_readme.exists()
    content = app_readme.read_text(encoding="utf-8")
    assert "API" in content or "api" in content


def test_resolve_inputs_skips_office_temporary_files(tmp_dir):
    from Tool.pipelines.common import resolve_inputs

    input_dir = tmp_dir / "Raw"
    input_dir.mkdir()
    (input_dir / "policy.docx").write_text("policy", encoding="utf-8")
    (input_dir / "~$draft.docx").write_text("temp", encoding="utf-8")
    (input_dir / "deck.pdf").write_text("pdf", encoding="utf-8")

    resolved = resolve_inputs(input_dir)

    assert [path.name for path in resolved] == ["deck.pdf", "policy.docx"]


def test_purge_temporary_office_artifacts_removes_manifest_and_parsed_output(tmp_dir):
    from Tool.pipelines import common

    raw_dir = tmp_dir / "Raw"
    manifest_dir = raw_dir / "manifests"
    parsed_dir = tmp_dir / "Tool" / "output" / "parsed"
    raw_dir.mkdir()
    manifest_dir.mkdir()
    parsed_dir.mkdir(parents=True)

    temp_file = raw_dir / "~$draft.docx"
    temp_file.write_text("temp", encoding="utf-8")
    parsed_output = parsed_dir / "doc-temp.json"
    parsed_output.write_text("{}", encoding="utf-8")
    manifest_path = manifest_dir / "doc-temp.json"
    manifest_path.write_text(
        json.dumps(
            {
                "document_id": "doc-temp",
                "file_name": "~$draft.docx",
                "stored_path": str(temp_file),
                "parsed_output": str(parsed_output),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    original_raw_dir = common.RAW_DIR
    original_manifest_dir = common.MANIFEST_DIR
    original_parsed_dir = common.PARSED_DIR
    common.RAW_DIR = raw_dir
    common.MANIFEST_DIR = manifest_dir
    common.PARSED_DIR = parsed_dir
    try:
        removed = common.purge_temporary_office_artifacts()
    finally:
        common.RAW_DIR = original_raw_dir
        common.MANIFEST_DIR = original_manifest_dir
        common.PARSED_DIR = original_parsed_dir

    assert removed == {"raw_files": 1, "manifests": 1, "parsed_outputs": 1}
    assert not temp_file.exists()
    assert not manifest_path.exists()
    assert not parsed_output.exists()
