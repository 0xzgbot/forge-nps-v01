"""
LM Studio Client — OpenAI-compatible local inference fallback.

LM Studio loads any GGUF model and exposes an OpenAI-compatible API
(typically on localhost:1234, or any host you configure).

Set LMSTUDIO_HOST in your .env to point to wherever LM Studio is running:
  - Mac laptop: http://localhost:1234
  - Remote GPU box: http://192.168.1.50:1234
  - Spark: http://100.112.87.8:1234

No external dependencies needed beyond urllib.
"""

import json
import os
from typing import Any, Dict, List, Optional

import numpy as np


class LMStudioClient:
    """
    Lightweight async-capable client for LM Studio's local server.
    Used as fallback when Kimi/NIM is rate-limited or unavailable.
    """

    def __init__(
        self,
        base_url: str = "",
        chat_model: str = "",
        embed_model: str = "",
        timeout: float = 60.0,
    ):
        self.base_url = (base_url or os.getenv("LMSTUDIO_HOST", "http://localhost:1234")).rstrip("/")
        self.chat_model = chat_model or os.getenv("LMSTUDIO_CHAT_MODEL", "")
        self.embed_model = embed_model or os.getenv("LMSTUDIO_EMBED_MODEL", "")
        self.timeout = timeout

    # ------------------------------------------------------------------
    # Health / availability
    # ------------------------------------------------------------------

    @property
    def is_available(self) -> bool:
        try:
            import urllib.request
            req = urllib.request.Request(
                f"{self.base_url}/v1/models",
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=2) as resp:
                return resp.status == 200
        except Exception:
            return False

    def list_models(self) -> List[str]:
        """Return IDs of loaded models."""
        try:
            import urllib.request
            req = urllib.request.Request(
                f"{self.base_url}/v1/models",
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return [m.get("id", "") for m in data.get("data", [])]
        except Exception as e:
            return []

    # ------------------------------------------------------------------
    # Chat completions
    # ------------------------------------------------------------------

    def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        json_mode: bool = False,
    ) -> Dict[str, Any]:
        """
        Synchronous chat completion.
        Returns parsed response dict or {"error": str} on failure.
        """
        model_id = model or self.chat_model
        if not model_id:
            return {"error": "No chat model configured. Set LMSTUDIO_CHAT_MODEL or pass model="}

        payload = {
            "model": model_id,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        try:
            import urllib.request
            req = urllib.request.Request(
                f"{self.base_url}/v1/chat/completions",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data
        except Exception as e:
            return {"error": str(e)}

    async def chat_async(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        json_mode: bool = False,
    ) -> Dict[str, Any]:
        """Async wrapper — runs sync chat in thread pool."""
        import asyncio
        return await asyncio.get_event_loop().run_in_executor(
            None,
            self.chat,
            messages,
            model,
            temperature,
            max_tokens,
            json_mode,
        )

    # ------------------------------------------------------------------
    # Embeddings
    # ------------------------------------------------------------------

    def embed(self, text: str, model: Optional[str] = None) -> np.ndarray:
        """Return embedding vector for text."""
        model_id = model or self.embed_model
        if not model_id:
            return np.zeros(1, dtype=np.float32)

        payload = {
            "model": model_id,
            "input": text,
        }

        try:
            import urllib.request
            req = urllib.request.Request(
                f"{self.base_url}/v1/embeddings",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                vec = np.array(data["data"][0]["embedding"], dtype=np.float32)
                return vec
        except Exception:
            return np.zeros(1, dtype=np.float32)

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def simple_prompt(self, system: str, user: str, **kwargs) -> str:
        """Single-turn prompt. Returns assistant text or error string."""
        resp = self.chat(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            **kwargs,
        )
        if "error" in resp:
            return f"[LM Studio Error] {resp['error']}"
        try:
            return resp["choices"][0]["message"]["content"]
        except (KeyError, IndexError):
            return "[LM Studio Error] Unexpected response format"
