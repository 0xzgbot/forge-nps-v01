import asyncio
import json
import os
from typing import Any, Dict, Optional

import httpx

from core.bridge.runtime_config import get_raw_config


class HermesProfileCLI:
    """
    Hermes profile runner.
    Uses direct OpenAI-compatible HTTP by default to avoid CLI startup latency.
    """

    def __init__(self) -> None:
        self.runner = os.getenv("FORGE_PROFILE_CLI_RUNNER", "forgehermes").strip() or "forgehermes"
        self.timeout_sec = float(os.getenv("FORGE_PROFILE_CLI_TIMEOUT_SEC", "120"))
        self.last_error = ""
        self.profile_map = {
            "compiler": os.getenv("FORGE_PROFILE_COMPILER", "compiler"),
            "remediator": os.getenv("FORGE_PROFILE_REMEDIATOR", "remediator"),
            "director": os.getenv("FORGE_PROFILE_DIRECTOR", "director_planner"),
            "critic": os.getenv("FORGE_PROFILE_CRITIC", "coverage_critic"),
            "continuity": os.getenv("FORGE_PROFILE_CONTINUITY", "continuity_guard"),
            "audit": os.getenv("FORGE_PROFILE_AUDIT", "audit_judge"),
        }

    @staticmethod
    def _profile_system_prompt(profile: str) -> str:
        prompts = {
            "compiler": (
                "You are Hermes / Prompt Compiler for FORGE NPS. Return JSON only. "
                "For image prompt tasks, output compiled_prompt and negative_prompt. "
                "For LTX2.3 video prompt tasks, output the exact requested JSON schema."
            ),
            "remediator": "You are Hermes / Remediation Reprompter. Return JSON only with corrected prompt fields.",
            "director": "You are Hermes / Campaign Intake Director. Return JSON only in the requested schema.",
            "critic": "You are Hermes / Coverage Critic. Return JSON only in the requested schema.",
            "continuity": "You are Hermes / Continuity Guard. Return JSON only.",
            "audit": "You are Hermes / Audit Judge. Return JSON only.",
        }
        return prompts.get(profile, "You are Hermes. Return JSON only in the requested schema.")

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

    def _runtime_args_and_env(self) -> tuple[list[str], Dict[str, str], Dict[str, str]]:
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
        debug = {
            "provider": provider,
            "model": model,
            "base_url": base_url,
        }
        return args, env, debug

    async def _run_direct_json(self, profile: str, task: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        self.last_error = ""
        _args, env, runtime_debug = self._runtime_args_and_env()
        model = str(runtime_debug.get("model") or "").strip()
        base_url = str(runtime_debug.get("base_url") or "").strip().rstrip("/")
        if not model or not base_url:
            self.last_error = f"profile_runtime_missing model={bool(model)} base_url={bool(base_url)}"
            return None
        endpoint = base_url if base_url.endswith("/chat/completions") else f"{base_url}/chat/completions"
        target_profile = self.profile_map.get(profile, profile)
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "/no_think\n" + self._profile_system_prompt(profile)},
                {
                    "role": "user",
                    "content": (
                        json.dumps(task, ensure_ascii=True)
                        + "\n/no_think\nReturn only compact JSON in assistant content."
                    ),
                },
            ],
            "temperature": 0.2,
            "max_tokens": int(os.getenv("FORGE_PROFILE_MAX_TOKENS", "8192")),
            "chat_template_kwargs": {"thinking": False, "enable_thinking": False},
        }
        headers = {"Content-Type": "application/json"}
        api_key = env.get("OPENAI_API_KEY") or env.get("CUSTOM_API_KEY") or "not-needed"
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout_sec) as client:
                resp = await client.post(endpoint, headers=headers, json=payload)
            if resp.status_code >= 400:
                self.last_error = f"http_{resp.status_code}:{resp.text[:500]}"
                return None
            data = resp.json()
            choice = (data.get("choices") or [{}])[0]
            message = choice.get("message", {}) if isinstance(choice, dict) else {}
            text = message.get("content", "")
            parsed = text if isinstance(text, dict) else self._parse_json_text(str(text))
            if parsed is None:
                reasoning = str(message.get("reasoning_content") or "")
                finish_reason = str(choice.get("finish_reason") or "unknown") if isinstance(choice, dict) else "unknown"
                if not str(text or "").strip() and reasoning.strip():
                    self.last_error = f"empty_content_reasoning_only finish_reason={finish_reason}"
                else:
                    self.last_error = f"json_parse_failed finish_reason={finish_reason} content={str(text)[:300]}"
                return None
            parsed["__exchange"] = {
                "stage": f"hermes_profile_{target_profile}",
                "transport": "openai_chat_completions",
                "profile": target_profile,
                "provider": runtime_debug.get("provider", ""),
                "model": model,
                "base_url": base_url,
                "request": payload,
                "response": {
                    "content": text,
                    "finish_reason": choice.get("finish_reason") if isinstance(choice, dict) else "",
                    "usage": data.get("usage", {}),
                },
            }
            return parsed
        except Exception as e:
            self.last_error = str(e) or e.__class__.__name__
            return None

    async def run_json(self, profile: str, task: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        self.last_error = ""
        if os.getenv("FORGE_PROFILE_USE_CLI", "false").lower() != "true":
            return await self._run_direct_json(profile, task)

        prompt = json.dumps(task, ensure_ascii=True)
        target_profile = self.profile_map.get(profile, profile)
        # Use explicit profile switch + oneshot mode for deterministic stdout.
        runtime_args, env, runtime_debug = self._runtime_args_and_env()
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
                self.last_error = f"cli_exit_{proc.returncode}:{(_err or b'').decode('utf-8', errors='ignore')[:500]}"
                return None
            text = (out or b"").decode("utf-8", errors="ignore").strip()
            if not text:
                self.last_error = "cli_empty_stdout"
                return None
            parsed = self._parse_json_text(text)
            if parsed is not None:
                parsed["__exchange"] = {
                    "stage": f"hermes_profile_{target_profile}",
                    "transport": "forgehermes_oneshot",
                    "runner": self.runner,
                    "profile": target_profile,
                    "provider": runtime_debug.get("provider", ""),
                    "model": runtime_debug.get("model", ""),
                    "base_url": runtime_debug.get("base_url", ""),
                    "request": task,
                    "response": {
                        "stdout": text,
                    },
                }
                return parsed
            return {
                "text": text,
                "__exchange": {
                    "stage": f"hermes_profile_{target_profile}",
                    "transport": "forgehermes_oneshot",
                    "runner": self.runner,
                    "profile": target_profile,
                    "provider": runtime_debug.get("provider", ""),
                    "model": runtime_debug.get("model", ""),
                    "base_url": runtime_debug.get("base_url", ""),
                    "request": task,
                    "response": {
                        "stdout": text,
                    },
                },
            }
        except Exception as e:
            self.last_error = str(e) or e.__class__.__name__
            return None
