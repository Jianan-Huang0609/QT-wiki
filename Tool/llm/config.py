from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterable

from Tool.llm.types import LLMConfig

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_AZURE_CONFIG = "azure_gpt4o_config.json"
DEFAULT_GPT5_CONFIG = "azure_gpt5_config.json"


def _candidate_paths(config_path: str | None) -> Iterable[Path]:
    if config_path:
        explicit = Path(config_path)
        yield explicit
        if not explicit.is_absolute():
            yield REPO_ROOT / explicit
            yield REPO_ROOT / "config" / explicit.name
            yield REPO_ROOT / explicit.name
    else:
        yield REPO_ROOT / "config" / DEFAULT_AZURE_CONFIG
        yield REPO_ROOT / DEFAULT_AZURE_CONFIG


def resolve_config_path(config_path: str | None = None) -> Path:
    for candidate in _candidate_paths(config_path):
        if candidate.exists():
            return candidate.resolve()

    target_name = Path(config_path).name if config_path else DEFAULT_AZURE_CONFIG
    raise FileNotFoundError(
        f"LLM config not found: {target_name}. "
        f"Expected under {REPO_ROOT / 'config'} or repository root."
    )


def _load_raw_config(config_path: str | None = None) -> tuple[dict[str, Any], Path]:
    resolved = resolve_config_path(config_path)
    with resolved.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return data, resolved


def _apply_env_overrides(data: dict[str, Any]) -> dict[str, Any]:
    cfg = dict(data)

    provider = os.getenv("LLM_PROVIDER")
    if provider:
        cfg["provider"] = provider

    if cfg.get("provider", "azure_openai") == "azure_openai":
        cfg["azure_api_key"] = os.getenv(
            "AZURE_OPENAI_API_KEY",
            os.getenv("LLM_API_KEY", cfg.get("azure_api_key", "")),
        )
        cfg["azure_endpoint"] = os.getenv(
            "AZURE_OPENAI_ENDPOINT",
            cfg.get("azure_endpoint", ""),
        )
        cfg["azure_deployment"] = os.getenv(
            "AZURE_OPENAI_DEPLOYMENT",
            cfg.get("azure_deployment", ""),
        )
        cfg["model"] = os.getenv("LLM_MODEL", cfg.get("model", cfg.get("azure_deployment", "")))
        cfg["api_version"] = os.getenv("AZURE_OPENAI_API_VERSION", cfg.get("api_version", "2024-02-01"))
    else:
        cfg["api_key"] = os.getenv("LLM_API_KEY", cfg.get("api_key", ""))
        cfg["base_url"] = os.getenv("LLM_BASE_URL", cfg.get("base_url", ""))
        cfg["model"] = os.getenv("LLM_MODEL", cfg.get("model", ""))

    if os.getenv("LLM_MAX_TOKENS"):
        cfg["max_tokens"] = int(os.getenv("LLM_MAX_TOKENS", "4000"))
    if os.getenv("LLM_TEMPERATURE"):
        cfg["temperature"] = float(os.getenv("LLM_TEMPERATURE", "0.2"))

    return cfg


def load_config(config_path: str | None = None) -> LLMConfig:
    raw_data, resolved = _load_raw_config(config_path)
    cfg = _apply_env_overrides(raw_data)
    provider = cfg.get("provider", "azure_openai")

    if provider == "azure_openai":
        return LLMConfig(
            provider=provider,
            api_key=cfg["azure_api_key"],
            endpoint=cfg["azure_endpoint"].rstrip("/"),
            deployment=cfg["azure_deployment"],
            model=cfg.get("model", cfg["azure_deployment"]),
            api_version=cfg.get("api_version", "2024-02-01"),
            max_tokens=int(cfg.get("max_tokens", 4000)),
            temperature=float(cfg.get("temperature", 0.2)),
            source_path=str(resolved),
        )

    return LLMConfig(
        provider=provider,
        api_key=cfg["api_key"],
        endpoint=cfg.get("base_url", "").rstrip("/"),
        model=cfg["model"],
        deployment=None,
        api_version=None,
        max_tokens=int(cfg.get("max_tokens", 4000)),
        temperature=float(cfg.get("temperature", 0.2)),
        source_path=str(resolved),
    )
