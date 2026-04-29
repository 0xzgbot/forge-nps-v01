import json
import os
from typing import Any, Dict, List, Optional

import httpx

from core.bridge.runtime_config import get_raw_config


def _extract_json_block(text: str) -> Any:
    raw = (text or "").strip()
    if not raw:
        raise ValueError("empty_kimi_content")
    if raw.startswith("```"):
        parts = raw.split("```")
        if len(parts) >= 2:
            raw = parts[1]
            if raw.startswith("json"):
                raw = raw[4:]
    return json.loads(raw.strip())


class KimiDirectorService:
    def __init__(self) -> None:
        cfg = get_raw_config()
        self.api_key = (os.getenv("KIMI_API_KEY", "") or str(cfg.get("KIMI_API_KEY", ""))).strip()
        endpoint = (os.getenv("NIM_ENDPOINT", "") or str(cfg.get("NIM_ENDPOINT", ""))).strip()
        if not endpoint:
            endpoint = "https://integrate.api.nvidia.com/v1/chat/completions"
        endpoint = endpoint.rstrip("/")
        if not endpoint.endswith("/chat/completions"):
            endpoint += "/chat/completions"
        self.endpoint = endpoint
        self.model_name = (
            os.getenv("KIMI_INSTRUCT_MODEL", "") or str(cfg.get("KIMI_INSTRUCT_MODEL", "moonshotai/kimi-k2"))
        ).strip()

    async def request_plan(
        self,
        brief: str,
        campaign_id: str,
        bible_text: str = "",
        length: str = "",
    ) -> Dict[str, Any]:
        if not self.api_key:
            raise RuntimeError("missing_kimi_api_key")

        schema_hint = {
            "campaign_id": "string",
            "shots": [{
                "shot_id": "SHOT_001",
                "sequence": 1,
                "narrative_intent": "string",
                "visual_brief": "string",
                "characters": ["string"],
                "environment": "string",
                "camera_direction": "string",
                "lighting_direction": "string",
                "rationale": "string",
                "constraints": "string",
            }],
        }
        system_prompt = (
            "You are Kimi acting as Director Planner for FORGE NPS. "
            "Return only JSON matching the schema exactly. "
            "You are planning shots, not writing final diffusion prompts."
        )
        user_prompt = (
            f"campaign_id: {campaign_id}\n"
            f"brief: {brief}\n"
            f"length: {length or 'unspecified'}\n"
            f"world_bible_excerpt:\n{bible_text[:6000] if bible_text else 'none'}\n\n"
            "Generate 4-8 shots in strict sequence and return JSON only.\n"
            f"Required schema:\n{json.dumps(schema_hint, indent=2)}"
        )
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.4,
            "response_format": {"type": "json_object"},
        }
        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.post(
                self.endpoint,
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json=payload,
            )
            if resp.status_code >= 400:
                raise RuntimeError(f"http_error status={resp.status_code} error={resp.text[:500]}")
            data = resp.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            parsed = _extract_json_block(content)
            if not isinstance(parsed, dict):
                raise RuntimeError("kimi_invalid_json_shape")
            parsed["__raw_content"] = content
            return parsed

    async def self_check_plan(
        self,
        brief: str,
        campaign_id: str,
        normalized_shots: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        if not self.api_key:
            raise RuntimeError("missing_kimi_api_key")
        # Judge-facing: require Kimi second pass critique for coverage/coherence risk.
        system_prompt = (
            "You are Kimi Quality Director. "
            "Evaluate the shot plan for narrative coherence, visual diversity, and renderability risk. "
            "Return JSON only."
        )
        prompt = {
            "campaign_id": campaign_id,
            "brief": brief,
            "shots": normalized_shots,
            "required_output_schema": {
                "score": "0-100 integer",
                "status": "pass|warn|fail",
                "coverage_gaps": ["string"],
                "continuity_risks": ["string"],
                "renderability_risks": ["string"],
                "director_notes": "string",
            },
        }
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(prompt)},
            ],
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                self.endpoint,
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json=payload,
            )
            if resp.status_code >= 400:
                raise RuntimeError(f"self_check_http_error status={resp.status_code} error={resp.text[:500]}")
            data = resp.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            parsed = _extract_json_block(content)
            if not isinstance(parsed, dict):
                raise RuntimeError("self_check_invalid_json_shape")
            parsed["__raw_content"] = content
            return parsed

    def build_dev_fallback_plan(self, brief: str, campaign_id: str) -> Dict[str, Any]:
        shots = []
        for i in range(1, 6):
            shots.append({
                "shot_id": f"SHOT_{str(i).zfill(3)}",
                "sequence": i,
                "narrative_intent": "fallback synthetic plan",
                "visual_brief": f"{brief}. cinematic shot {i}, high detail, strong composition.",
                "characters": [],
                "environment": "fallback environment",
                "camera_direction": "cinematic framing",
                "lighting_direction": "balanced dramatic lighting",
                "rationale": "development fallback mode",
                "constraints": "dev fallback only",
            })
        return {"campaign_id": campaign_id, "shots": shots, "__raw_content": json.dumps({"fallback": True, "shots": shots})}

    def normalize_shots(self, plan: Dict[str, Any], campaign_id: str) -> List[Dict[str, Any]]:
        shots = plan.get("shots", [])
        if not isinstance(shots, list) or not shots:
            raise RuntimeError("kimi_no_shots")
        normalized = []
        for i, s in enumerate(shots, start=1):
            if not isinstance(s, dict):
                raise RuntimeError(f"kimi_shot_invalid_type:{i}")
            shot_id = str(s.get("shot_id") or f"SHOT_{str(i).zfill(3)}")
            visual_brief = str(s.get("visual_brief") or "").strip()
            if not visual_brief:
                raise RuntimeError(f"kimi_missing_visual_brief:{shot_id}")
            normalized.append({
                "campaign_id": campaign_id,
                "shot_id": shot_id,
                "sequence": int(s.get("sequence") or i),
                "narrative_intent": str(s.get("narrative_intent") or ""),
                "visual_brief": visual_brief,
                "characters": s.get("characters") if isinstance(s.get("characters"), list) else [],
                "environment": str(s.get("environment") or ""),
                "camera_direction": str(s.get("camera_direction") or ""),
                "lighting_direction": str(s.get("lighting_direction") or ""),
                "rationale": str(s.get("rationale") or ""),
                "constraints": str(s.get("constraints") or ""),
            })
        return sorted(normalized, key=lambda x: x["sequence"])

    @staticmethod
    def score_from_review(review: Optional[Dict[str, Any]]) -> Optional[int]:
        if not isinstance(review, dict):
            return None
        raw = review.get("score")
        try:
            return int(float(raw))
        except Exception:
            return None

