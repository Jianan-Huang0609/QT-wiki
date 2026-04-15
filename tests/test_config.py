from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from Tool.llm.config import REPO_ROOT, _apply_env_overrides, load_config, resolve_config_path


def test_config_dir_path_priority():
    resolved = resolve_config_path("azure_gpt4o_config.json")
    assert resolved.exists()
    assert resolved.name == "azure_gpt4o_config.json"


def test_config_dir_path_preferred_over_root():
    config_dir_path = REPO_ROOT / "config" / "azure_gpt4o_config.json"
    assert config_dir_path.exists(), "config/ 目录下的配置必须存在"

    resolved = resolve_config_path("azure_gpt4o_config.json")
    assert resolved.exists()


def test_missing_config_raises():
    with pytest.raises(FileNotFoundError, match="LLM config not found"):
        resolve_config_path("nonexistent_config_xyz.json")


def test_env_override_api_key(sample_config_data):
    with patch.dict(os.environ, {"AZURE_OPENAI_API_KEY": "env-override-key"}):
        cfg = _apply_env_overrides(sample_config_data)
        assert cfg["azure_api_key"] == "env-override-key"


def test_env_override_endpoint(sample_config_data):
    with patch.dict(os.environ, {"AZURE_OPENAI_ENDPOINT": "https://env-endpoint.example.com"}):
        cfg = _apply_env_overrides(sample_config_data)
        assert cfg["azure_endpoint"] == "https://env-endpoint.example.com"


def test_env_override_max_tokens(sample_config_data):
    with patch.dict(os.environ, {"LLM_MAX_TOKENS": "8000"}):
        cfg = _apply_env_overrides(sample_config_data)
        assert cfg["max_tokens"] == 8000


def test_env_override_temperature(sample_config_data):
    with patch.dict(os.environ, {"LLM_TEMPERATURE": "0.5"}):
        cfg = _apply_env_overrides(sample_config_data)
        assert cfg["temperature"] == 0.5


def test_env_override_provider_switch(sample_config_data):
    with patch.dict(os.environ, {
        "LLM_PROVIDER": "openai_compatible",
        "LLM_API_KEY": "compat-key",
        "LLM_BASE_URL": "https://compat.example.com/v1",
        "LLM_MODEL": "my-model",
    }):
        cfg = _apply_env_overrides(sample_config_data)
        assert cfg["provider"] == "openai_compatible"
        assert cfg["api_key"] == "compat-key"
        assert cfg["base_url"] == "https://compat.example.com/v1"
        assert cfg["model"] == "my-model"


def test_load_config_returns_llm_config():
    config = load_config()
    assert config.provider in ("azure_openai", "openai_compatible")
    assert config.api_key
    assert config.endpoint
    assert config.model
    assert config.source_path


def test_load_config_custom_path(sample_config_file):
    config = load_config(str(sample_config_file))
    assert config.api_key == "test-key-12345"
    assert config.endpoint == "https://test-endpoint.example.com"
