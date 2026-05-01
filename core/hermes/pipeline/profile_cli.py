import asyncio
import json
import os
from typing import Any, Dict, Optional


class HermesProfileCLI:
    """
    Best-effort CLI profile runner.
    Falls back gracefully when profile CLI is unavailable.
    """

    def __init__(self) -> None:
        self.runner = os.getenv("FORGE_PROFILE_CLI_RUNNER", "forgehermes").strip() or "forgehermes"
        self.timeout_sec = float(os.getenv("FORGE_PROFILE_CLI_TIMEOUT_SEC", "45"))
        self.profile_map = {
            "compiler": os.getenv("FORGE_PROFILE_COMPILER", "compiler"),
            "remediator": os.getenv("FORGE_PROFILE_REMEDIATOR", "remediator"),
            "director": os.getenv("FORGE_PROFILE_DIRECTOR", "director_planner"),
            "critic": os.getenv("FORGE_PROFILE_CRITIC", "coverage_critic"),
            "continuity": os.getenv("FORGE_PROFILE_CONTINUITY", "continuity_guard"),
            "audit": os.getenv("FORGE_PROFILE_AUDIT", "audit_judge"),
        }

    async def run_json(self, profile: str, task: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        prompt = json.dumps(task, ensure_ascii=True)
        target_profile = self.profile_map.get(profile, profile)
        # Use explicit profile switch + oneshot mode for deterministic stdout.
        cmd = [self.runner, "--profile", target_profile, "-z", prompt]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            out, _err = await asyncio.wait_for(proc.communicate(), timeout=self.timeout_sec)
            if proc.returncode != 0:
                return None
            text = (out or b"").decode("utf-8", errors="ignore").strip()
            if not text:
                return None
            try:
                return json.loads(text)
            except Exception:
                return {"text": text}
        except Exception:
            return None
