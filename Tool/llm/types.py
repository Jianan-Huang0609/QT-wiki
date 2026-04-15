from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(slots=True)
class LLMConfig:
    provider: str
    api_key: str
    endpoint: str
    model: str
    deployment: Optional[str] = None
    api_version: Optional[str] = None
    max_tokens: int = 4000
    temperature: float = 0.2
    source_path: str = ""


@dataclass(slots=True)
class ChatRequest:
    question: str
    max_tokens: int
    temperature: float
    top_p: float
    system: Optional[str]
