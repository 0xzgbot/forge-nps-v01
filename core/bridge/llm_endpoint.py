"""Resolve any OpenAI-compatible LLM the user connected.

Kimi / NVIDIA / Nous are optional backends, not required directors.
Canonical keys: LLM_BASE_URL, LLM_MODEL, LLM_API_KEY.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, Optional
from urllib.parse import urlsplit, urlunsplit

from core.bridge.runtime_config import get_raw_config


def _cfg() -> Dict[str, Any]:
    try:
        return get_raw_config()
    except Exception:
        return {}


def _pick(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "local", "lmstudio"}


def normalize_openai_base(raw: str, *, default_port: str = "") -> str:
    value = (raw or "").strip().rstrip("/")
    if not value:
        return ""
    if not value.startswith(("http://", "https://")):
        value = "http://" + value
    parts = urlsplit(value)
    path = parts.path.rstrip("/")
    if path.endswith("/chat/completions"):
        path = path[: -len("/chat/completions")].rstrip("/")
    if path.endswith("/v1"):
        path = path.rstrip("/")
    else:
        path = f"{path}/v1" if path else "/v1"
    netloc = parts.netloc
    try:
        has_port = parts.port is not None
    except ValueError:
        has_port = ":" in netloc.rsplit("@", 1)[-1]
    if default_port and not has_port:
        netloc = f"{netloc}:{default_port}"
    return urlunsplit((parts.scheme, netloc, path, "", "")).rstrip("/")


@dataclass(frozen=True)
class LLMEndpoint:
    base_url: str
    model: str
    api_key: str
    source: str
    local: bool

    @property
    def chat_url(self) -> str:
        base = (self.base_url or "").rstrip("/")
        if base.endswith("/chat/completions"):
            return base
        return f"{base}/chat/completions"

    @property
    def ready(self) -> bool:
        if not self.base_url or not self.model:
            return False
        if self.local:
            return True
        return True


def resolve_llm_endpoint(cfg: Optional[Dict[str, Any]] = None) -> LLMEndpoint:
    data = cfg if isinstance(cfg, dict) else _cfg()
    local = _truthy(
        _pick(
            os.getenv("LLM_BACKEND"),
            os.getenv("USE_LOCAL_DIRECTOR"),
            data.get("USE_LOCAL_DIRECTOR"),
            os.getenv("USE_LOCAL_MODELS"),
            data.get("USE_LOCAL_MODELS"),
        )
    ) or str(os.getenv("LLM_BACKEND", "")).strip().lower() in {"lmstudio", "ollama", "vllm", "local"}

    model = _pick(
        os.getenv("LLM_MODEL"),
        data.get("LLM_MODEL"),
        os.getenv("CINESMITH_PROFILE_MODEL"),
        os.getenv("DIRECTOR_MODEL"),
        data.get("DIRECTOR_MODEL"),
        os.getenv("LMSTUDIO_CHAT_MODEL") if local else "",
        data.get("LMSTUDIO_CHAT_MODEL") if local else "",
        os.getenv("KIMI_INSTRUCT_MODEL"),
        data.get("KIMI_INSTRUCT_MODEL"),
    )

    api_key = _pick(
        os.getenv("LLM_API_KEY"),
        data.get("LLM_API_KEY"),
        os.getenv("OPENAI_API_KEY"),
        data.get("OPENAI_API_KEY"),
        os.getenv("OPENROUTER_API_KEY"),
        data.get("OPENROUTER_API_KEY"),
        os.getenv("NOUS_API_KEY"),
        data.get("NOUS_API_KEY"),
        os.getenv("ANTHROPIC_API_KEY"),
        os.getenv("KIMI_API_KEY"),
        data.get("KIMI_API_KEY"),
    )

    lm_host = _pick(os.getenv("LMSTUDIO_HOST"), data.get("LMSTUDIO_HOST"), "http://localhost")
    lm_port = _pick(os.getenv("LMSTUDIO_PORT"), data.get("LMSTUDIO_PORT"), "1234")

    candidates = [
        ("llm", _pick(os.getenv("LLM_BASE_URL"), data.get("LLM_BASE_URL")), ""),
        ("profile", _pick(os.getenv("CINESMITH_PROFILE_BASE_URL"), data.get("CINESMITH_PROFILE_BASE_URL")), ""),
        ("openai", _pick(os.getenv("OPENAI_BASE_URL"), data.get("OPENAI_BASE_URL")), ""),
        ("openrouter", _pick(os.getenv("OPENROUTER_ENDPOINT"), data.get("OPENROUTER_ENDPOINT")), ""),
        ("nous", _pick(os.getenv("NOUS_ENDPOINT"), data.get("NOUS_ENDPOINT")), ""),
        ("legacy_nim", _pick(os.getenv("NIM_ENDPOINT"), data.get("NIM_ENDPOINT")), ""),
        ("legacy_kimi", _pick(os.getenv("KIMI_ENDPOINT"), data.get("KIMI_ENDPOINT"), os.getenv("KIMI_DIRECTOR_ENDPOINT_API1"), data.get("KIMI_DIRECTOR_ENDPOINT_API1")), ""),
    ]
    if local:
        candidates.insert(0, ("lmstudio", lm_host, lm_port))

    for source, raw, port in candidates:
        base = normalize_openai_base(raw, default_port=port)
        if base:
            if source == "lmstudio" and not model:
                model = _pick(os.getenv("LMSTUDIO_CHAT_MODEL"), data.get("LMSTUDIO_CHAT_MODEL"))
            return LLMEndpoint(
                base_url=base,
                model=model,
                api_key=api_key,
                source=source,
                local=source == "lmstudio" or local,
            )

    return LLMEndpoint(base_url="", model=model, api_key=api_key, source="unset", local=local)
