import asyncio
import json
import os
from typing import Any, Dict, Optional

from core.bridge.runtime_config import get_raw_config


class HermesProfileCLI:
    """
    Best-effort CLI profile runner.
    Falls back gracefully when profile CLI is unavailable.
    """

    def __init__(self) -> None:
        self.runner = os.getenv("FORGE_PROFILE_CLI_RUNNER", "forgehermes").strip() or "forgehermes"
        self.timeout_sec = float(os.getenv("FORGE_PROFILE_CLI_TIMEOUT_SEC", "120"))
        self.profile_map = {
            "compiler": os.getenv("FORGE_PROFILE_COMPILER", "compiler"),
            "remediator": os.getenv("FORGE_PROFILE_REMEDIATOR", "remediator"),
            "director": os.getenv("FORGE_PROFILE_DIRECTOR", "director_planner"),
            "critic": os.getenv("FORGE_PROFILE_CRITIC", "coverage_critic"),
            "continuity": os.getenv("FORGE_PROFILE_CONTINUITY", "continuity_guard"),
            "audit": os.getenv("FORGE_PROFILE_AUDIT", "audit_judge"),
        }

    @staticmethod
    def _parse_json_text(text: str) -> Optional[Dict[str, Any]]:
        raw = (text or "").strip()
        if not raw:
            return None
        if raw.startswith("```"):
            parts = raw.split("```")
            if len(parts) >= 2:
                raw = parts[1].strip()
                if raw.startswith("json"):
                    raw = raw[4:].strip()
        try:
            parsed = json.loads(raw)
        except Exception:
            start = raw.find("{")
            if start < 0:
                return None
            try:
                parsed, _ = json.JSONDecoder().raw_decode(raw[start:])
            except Exception:
                return None
        return parsed if isinstance(parsed, dict) else None

    def _runtime_args_and_env(self) -> tuple[list[str], Dict[str, str]]:
        cfg = get_raw_config()
        provider = os.getenv("FORGE_PROFILE_PROVIDER", "custom").strip() or "custom"
        model = (
            os.getenv("FORGE_PROFILE_MODEL", "")
            or os.getenv("LMSTUDIO_CHAT_MODEL", "")
            or str(cfg.get("LMSTUDIO_CHAT_MODEL", ""))
        ).strip()
        base_url = (
            os.getenv("FORGE_PROFILE_BASE_URL", "")
            or os.getenv("OPENAI_BASE_URL", "")
            or str(cfg.get("LMSTUDIO_HOST", ""))
            or str(cfg.get("KIMI_VISUAL_ENDPOINT_API1", ""))
        ).strip()

        if base_url:
            base_url = base_url.rstrip("/")
            if base_url.endswith("/chat/completions"):
                base_url = base_url[: -len("/chat/completions")]
            if not base_url.endswith("/v1"):
                if ":1234" not in base_url:
                    base_url = f"{base_url}:1234"
                base_url = f"{base_url}/v1"

        args: list[str] = []
        if provider:
            args.extend(["--provider", provider])
        if model:
            args.extend(["--model", model])

        env = os.environ.copy()
        if base_url:
            env["OPENAI_BASE_URL"] = base_url
            env["CUSTOM_BASE_URL"] = base_url
        env.setdefault("OPENAI_API_KEY", "not-needed")
        return args, env

    async def run_json(self, profile: str, task: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        prompt = json.dumps(task, ensure_ascii=True)
        target_profile = self.profile_map.get(profile, profile)
        # Use explicit profile switch + oneshot mode for deterministic stdout.
        runtime_args, env = self._runtime_args_and_env()
        cmd = [self.runner, *runtime_args, "--profile", target_profile, "-z", prompt]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            out, _err = await asyncio.wait_for(proc.communicate(), timeout=self.timeout_sec)
            if proc.returncode != 0:
                return None
            text = (out or b"").decode("utf-8", errors="ignore").strip()
            if not text:
                return None
            parsed = self._parse_json_text(text)
            if parsed is not None:
                return parsed
            return {"text": text}
        except Exception:
            return None
