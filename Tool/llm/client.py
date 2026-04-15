from __future__ import annotations

import logging
from typing import Optional

import requests

from Tool.llm.config import DEFAULT_GPT5_CONFIG, load_config, resolve_config_path
from Tool.llm.prompts import FINAL_ONLY_SYSTEM_PROMPT
from Tool.llm.types import ChatRequest

LOGGER = logging.getLogger(__name__)


class LLMTool:
    """Thin chat-completions client with Azure/OpenAI-compatible support."""

    def __init__(self, config_path: str = "config/azure_gpt4o_config.json"):
        self.config = load_config(config_path)
        self.provider = self.config.provider
        self.api_key = self.config.api_key
        self.endpoint = self.config.endpoint
        self.deployment = self.config.deployment
        self.api_version = self.config.api_version
        self.model = self.config.model
        self.default_max_tokens = self.config.max_tokens
        self.default_temperature = self.config.temperature
        self.config_path = self.config.source_path
        LOGGER.debug(
            "LLM 客户端已初始化：provider=%s，model=%s，config=%s",
            self.provider,
            self.model,
            self.config_path,
        )

    def ask(
        self,
        question: str,
        *,
        max_tokens: int = 0,
        temperature: float = 0.0,
        top_p: float = 0.6,
        system: Optional[str] = FINAL_ONLY_SYSTEM_PROMPT,
    ) -> str:
        request = ChatRequest(
            question=question,
            max_tokens=max_tokens or self.default_max_tokens,
            temperature=temperature if temperature != 0.0 else self.default_temperature,
            top_p=top_p,
            system=system,
        )
        return self._send_chat_request(request)

    def _send_chat_request(self, request: ChatRequest) -> str:
        messages = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages.append({"role": "user", "content": request.question})

        payload = {
            "messages": messages,
            "temperature": request.temperature,
            "top_p": request.top_p,
            "max_completion_tokens": request.max_tokens,
        }

        if self.provider == "azure_openai":
            url = f"{self.endpoint}/openai/deployments/{self.deployment}/chat/completions"
            params = {"api-version": self.api_version}
            headers = {
                "Content-Type": "application/json",
                "api-key": self.api_key,
            }
        else:
            url = f"{self.endpoint}/chat/completions"
            params = {}
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            }
            payload["model"] = self.model

        LOGGER.info(
            "LLM 请求开始：provider=%s，model=%s，config=%s，提示词长度=%s，max_tokens=%s，temperature=%s",
            self.provider,
            self.model,
            self.config_path,
            len(request.question),
            request.max_tokens,
            request.temperature,
        )
        try:
            response = requests.post(
                url,
                json=payload,
                params=params,
                headers=headers,
                timeout=120,
            )
            response.raise_for_status()
            data = response.json()
            choices = data.get("choices", [])
            if not choices:
                LOGGER.warning("LLM 请求已完成，但没有返回 choices：provider=%s，model=%s", self.provider, self.model)
                return ""
            content = (choices[0].get("message", {}) or {}).get("content", "").strip()
            LOGGER.info(
                "LLM 请求完成：provider=%s，model=%s，返回长度=%s",
                self.provider,
                self.model,
                len(content),
            )
            return content
        except Exception:
            LOGGER.exception("LLM 请求失败：provider=%s，model=%s，config=%s", self.provider, self.model, self.config_path)
            raise


_TOOLS: dict[str, LLMTool] = {}


def _get_tool(config_path: str) -> LLMTool:
    resolved = str(resolve_config_path(config_path))
    tool = _TOOLS.get(resolved)
    if tool is None:
        LOGGER.debug("创建缓存中的 LLM 客户端：config=%s", resolved)
        tool = LLMTool(resolved)
        _TOOLS[resolved] = tool
    return tool


def ask_llm(
    question: str,
    config_path: str = "config/azure_gpt4o_config.json",
    *,
    max_tokens: int = 10000,
    temperature: float = 1,
    top_p: float = 0.6,
    system: Optional[str] = FINAL_ONLY_SYSTEM_PROMPT,
) -> str:
    return _get_tool(config_path).ask(
        question,
        max_tokens=max_tokens,
        temperature=temperature,
        top_p=top_p,
        system=system,
    )


def ask_llm_gpt5(
    question: str,
    config_path: str = f"config/{DEFAULT_GPT5_CONFIG}",
    *,
    max_tokens: int = 10000,
    temperature: float = 1,
    top_p: float = 0.6,
    system: Optional[str] = FINAL_ONLY_SYSTEM_PROMPT,
) -> str:
    try:
        tool = _get_tool(config_path)
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            "GPT-5 config not found. Expected config/azure_gpt5_config.json or an explicit config_path."
        ) from exc

    return tool.ask(
        question,
        max_tokens=max_tokens,
        temperature=temperature,
        top_p=top_p,
        system=system,
    )
