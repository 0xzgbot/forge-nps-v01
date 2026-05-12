import json
import os
import re
import asyncio
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit, urlunsplit

import httpx

from core.bridge.runtime_config import MODEL_REPLACEMENTS, get_raw_config


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


def _with_exchange_debug(
    parsed: Dict[str, Any],
    *,
    stage: str,
    endpoint: str,
    model: str,
    payload: Dict[str, Any],
    raw_content: str,
) -> Dict[str, Any]:
    parsed["__raw_content"] = raw_content
    parsed["__exchange"] = {
        "stage": stage,
        "transport": "openai_chat_completions",
        "endpoint": endpoint,
        "model": model,
        "request": payload,
        "response": {
            "content": raw_content,
        },
    }
    return parsed


def _normalize_model_name(model_name: str) -> str:
    cleaned = (model_name or "").strip()
    return MODEL_REPLACEMENTS.get(cleaned, cleaned)


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "local", "lmstudio"}


def _lmstudio_chat_endpoint(cfg: Dict[str, Any]) -> str:
    host = (
        str(cfg.get("LMSTUDIO_HOST", "") or "")
        or os.getenv("LMSTUDIO_HOST", "")
        or "http://localhost"
    ).strip().rstrip("/")
    port = str(cfg.get("LMSTUDIO_PORT", "") or os.getenv("LMSTUDIO_PORT", "") or "1234").strip()
    if host.endswith("/v1"):
        host = host[:-3].rstrip("/")
    if not host.startswith(("http://", "https://")):
        host = "http://" + host
    parts = urlsplit(host)
    netloc = parts.netloc
    try:
        has_port = parts.port is not None
    except ValueError:
        has_port = ":" in netloc.rsplit("@", 1)[-1]
    if port and not has_port:
        netloc = f"{netloc}:{port}"
    base = urlunsplit((parts.scheme, netloc, parts.path.rstrip("/"), "", "")).rstrip("/")
    return f"{base}/v1/chat/completions"


def _multi_person_cast_directive(brief: str, target_shots: int) -> str:
    text = (brief or "").lower()
    asks_for_people = bool(re.search(r"\b(people|persons|portraits|characters|cast|faces|headshots|models)\b", text))
    if target_shots < 4 or not asks_for_people:
        return ""
    return (
        "Multi-person cast rule: each shot must feature a visibly different person, not the same averaged face. "
        "For every person specify a unique name or label, exact adult age or age decade, face shape, nose/jaw/eye details, "
        "hair color/style/texture, build/height, wardrobe, occupation or social context, and a specific environment. "
        "Do not default the whole set to one ambiguous median/biracial look, one age band, one hairstyle, or one body type. "
        "Honor any demographic instructions in the brief exactly; otherwise use deliberate variety across age, skin tone, "
        "facial structure, hair texture, body type, styling, and setting. "
        "Put these distinguishing traits directly inside visual_brief so the image model receives them."
    )


class KimiDirectorService:
    def __init__(self) -> None:
        cfg = get_raw_config()
        self.use_local_director = _truthy(os.getenv("USE_LOCAL_DIRECTOR", "") or cfg.get("USE_LOCAL_DIRECTOR", ""))
        self.backend = "lmstudio" if self.use_local_director else "nvidia"
        raw_key = (
            os.getenv("KIMI_API_KEY", "")
            or str(cfg.get("KIMI_API_KEY", ""))
            or os.getenv("NOUS_API_KEY", "")
            or os.getenv("OPENROUTER_API_KEY", "")
            or str(cfg.get("NOUS_API_KEY", ""))
        ).strip()
        self.api_key = self._sanitize_api_key(raw_key)
        if self.use_local_director:
            endpoint = _lmstudio_chat_endpoint(cfg)
        else:
            active = (os.getenv("KIMI_DIRECTOR_ENDPOINT_ACTIVE", "") or str(cfg.get("KIMI_DIRECTOR_ENDPOINT_ACTIVE", "api1"))).strip().lower()
            api1 = (os.getenv("KIMI_DIRECTOR_ENDPOINT_API1", "") or str(cfg.get("KIMI_DIRECTOR_ENDPOINT_API1", ""))).strip()
            api2 = (os.getenv("KIMI_DIRECTOR_ENDPOINT_API2", "") or str(cfg.get("KIMI_DIRECTOR_ENDPOINT_API2", ""))).strip()
            endpoint = api2 if active == "api2" and api2 else api1
            if not endpoint:
                endpoint = (
                    os.getenv("NIM_ENDPOINT", "")
                    or os.getenv("KIMI_ENDPOINT", "")
                    or str(cfg.get("NIM_ENDPOINT", ""))
                    or os.getenv("NOUS_ENDPOINT", "")
                    or os.getenv("OPENROUTER_ENDPOINT", "")
                    or str(cfg.get("NOUS_ENDPOINT", ""))
                ).strip()
            if not endpoint:
                endpoint = "https://inference-api.nousresearch.com/v1/chat/completions"
            endpoint = endpoint.rstrip("/")
            if not endpoint.endswith("/chat/completions"):
                endpoint += "/chat/completions"
        self.endpoint = endpoint
        self.model_name = _normalize_model_name(
            (os.getenv("LMSTUDIO_CHAT_MODEL", "") or str(cfg.get("LMSTUDIO_CHAT_MODEL", "")) if self.use_local_director else "")
            or os.getenv("KIMI_INSTRUCT_MODEL", "")
            or str(cfg.get("KIMI_INSTRUCT_MODEL", ""))
            or os.getenv("DIRECTOR_MODEL", "")
            or str(cfg.get("DIRECTOR_MODEL", "Hermes-4-405B"))
        )
        self.thinking_model_name = _normalize_model_name(
            (os.getenv("LMSTUDIO_CHAT_MODEL", "") or str(cfg.get("LMSTUDIO_CHAT_MODEL", "")) if self.use_local_director else "")
            or os.getenv("KIMI_THINKING_MODEL", "")
            or str(cfg.get("KIMI_THINKING_MODEL", ""))
            or self.model_name
        )

    def _auth_headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key and not self.use_local_director:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _response_format(self) -> Dict[str, str]:
        if self.use_local_director:
            return {"type": "text"}
        return {"type": "json_object"}

    def _require_ready(self) -> None:
        if self.use_local_director:
            if not self.model_name:
                raise RuntimeError("missing_lmstudio_chat_model")
            return
        if not self.api_key:
            raise RuntimeError("missing_kimi_api_key")

    @staticmethod
    def _sanitize_api_key(raw_key: str) -> str:
        """
        Keep HTTP header auth strictly ASCII-safe.
        This prevents crashes when a masked key (e.g., bullets) is pasted/saved.
        """
        if not raw_key:
            return ""
        # Drop common mask glyphs and whitespace noise.
        cleaned = raw_key.replace("•", "").replace("…", "").replace("*", "").strip()
        # HTTP headers must be latin-1/ASCII-safe for these token formats.
        safe = cleaned.encode("ascii", "ignore").decode("ascii").strip()
        return safe

    @staticmethod
    def requested_shot_count(brief: str, length: str = "") -> int:
        """
        Infer target shot count from explicit user wording.
        Examples: "20 images", "12 shots", "8 frames".
        Falls back to 5 when no explicit count is present.
        """
        text = f"{brief or ''} {length or ''}".lower()
        unit = r"(?:images?|shots?|frames?|renders?|stills?|assets?|variations?)"
        patterns = [
            rf"\b(\d{{1,3}})\s*[- ]?\s*{unit}\b",
            rf"\b{unit}\s*[:=]?\s*(\d{{1,3}})\b",
            r"\b(?:make|create|generate|render|produce|need|needs|want|wants|requested|requesting)\s+(\d{1,3})\b",
            r"\b(\d{1,3})\s*x\b",
        ]
        for pattern in patterns:
            m = re.search(pattern, text)
            if not m:
                continue
            try:
                n = int(m.group(1))
                return max(1, min(n, 120))
            except Exception:
                pass
        word_numbers = {
            "one": 1,
            "two": 2,
            "three": 3,
            "four": 4,
            "five": 5,
            "six": 6,
            "seven": 7,
            "eight": 8,
            "nine": 9,
            "ten": 10,
            "eleven": 11,
            "twelve": 12,
            "thirteen": 13,
            "fourteen": 14,
            "fifteen": 15,
            "sixteen": 16,
            "seventeen": 17,
            "eighteen": 18,
            "nineteen": 19,
            "twenty": 20,
            "thirty": 30,
        }
        for word, n in word_numbers.items():
            if re.search(rf"\b{word}\s+{unit}\b", text):
                return n
        return 5

    @staticmethod
    def _max_tokens_for_target(target_shots: int, default: int = 8192) -> int:
        if target_shots >= 20:
            return max(default, int(os.getenv("FORGE_KIMI_MAX_TOKENS_20_SHOTS", "16384")))
        if target_shots >= 12:
            return max(default, int(os.getenv("FORGE_KIMI_MAX_TOKENS_12_SHOTS", "12288")))
        return default

    async def request_plan(
        self,
        brief: str,
        campaign_id: str,
        bible_text: str = "",
        length: str = "",
        target_shots: Optional[int] = None,
    ) -> Dict[str, Any]:
        self._require_ready()

        target = int(target_shots or self.requested_shot_count(brief, length))
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
            f"target_shots: {target}\n"
            f"world_bible_excerpt:\n{bible_text[:6000] if bible_text else 'none'}\n\n"
            f"{_multi_person_cast_directive(brief, target)}\n\n"
            f"Generate exactly {target} shots in strict sequence and return JSON only.\n"
            f"Required schema:\n{json.dumps(schema_hint, indent=2)}"
        )
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.4,
            "response_format": self._response_format(),
            "max_tokens": self._max_tokens_for_target(target),
        }
        timeout_sec = float(os.getenv("FORGE_KIMI_TIMEOUT_SEC", "300"))
        # Scale timeout for larger plans (e.g., 20-image requests).
        if target and target >= 20:
            timeout_sec = max(timeout_sec, float(os.getenv("FORGE_KIMI_TIMEOUT_20_SHOTS_SEC", "600")))
        elif target >= 12:
            timeout_sec = max(timeout_sec, float(os.getenv("FORGE_KIMI_TIMEOUT_12_SHOTS_SEC", "420")))
        async with httpx.AsyncClient(timeout=timeout_sec) as client:
            resp = await client.post(
                self.endpoint,
                headers=self._auth_headers(),
                json=payload,
            )
            if resp.status_code >= 400:
                raise RuntimeError(f"http_error status={resp.status_code} error={resp.text[:500]}")
            data = resp.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            parsed = _extract_json_block(content)
            if not isinstance(parsed, dict):
                raise RuntimeError("kimi_invalid_json_shape")
            return _with_exchange_debug(
                parsed,
                stage="kimi_director_plan",
                endpoint=self.endpoint,
                model=self.model_name,
                payload=payload,
                raw_content=content,
            )

    async def request_missing_shots(
        self,
        *,
        brief: str,
        campaign_id: str,
        existing_shots: List[Dict[str, Any]],
        target_shots: int,
        bible_text: str = "",
        length: str = "",
    ) -> Dict[str, Any]:
        self._require_ready()

        have = len(existing_shots or [])
        if have >= target_shots:
            return {"campaign_id": campaign_id, "shots": []}
        needed = target_shots - have
        system_prompt = (
            "You are Kimi acting as Director Planner for FORGE NPS. "
            "Return only JSON. Extend the existing plan without duplicating existing sequence numbers."
        )
        prompt = {
            "campaign_id": campaign_id,
            "brief": brief,
            "length": length or "unspecified",
            "target_shots": target_shots,
            "have_shots": have,
            "need_additional_shots": needed,
            "existing_shots": existing_shots,
            "world_bible_excerpt": (bible_text[:4000] if bible_text else "none"),
            "multi_person_cast_rule": _multi_person_cast_directive(brief, target_shots) or "not applicable",
            "required_output_schema": {
                "campaign_id": "string",
                "shots": [{
                    "shot_id": "SHOT_006",
                    "sequence": 6,
                    "narrative_intent": "string",
                    "visual_brief": "string",
                    "characters": ["string"],
                    "environment": "string",
                    "camera_direction": "string",
                    "lighting_direction": "string",
                    "rationale": "string",
                    "constraints": "string",
                }],
            },
        }
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(prompt)},
            ],
            "temperature": 0.35,
            "response_format": self._response_format(),
            "max_tokens": self._max_tokens_for_target(target_shots),
        }
        timeout_sec = float(os.getenv("FORGE_KIMI_TIMEOUT_SEC", "300"))
        if target_shots >= 20:
            timeout_sec = max(timeout_sec, float(os.getenv("FORGE_KIMI_TIMEOUT_20_SHOTS_SEC", "600")))
        async with httpx.AsyncClient(timeout=timeout_sec) as client:
            resp = await client.post(
                self.endpoint,
                headers=self._auth_headers(),
                json=payload,
            )
            if resp.status_code >= 400:
                raise RuntimeError(f"http_error status={resp.status_code} error={resp.text[:500]}")
            data = resp.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            parsed = _extract_json_block(content)
            if not isinstance(parsed, dict):
                raise RuntimeError("kimi_invalid_json_shape")
            return _with_exchange_debug(
                parsed,
                stage="kimi_director_top_up",
                endpoint=self.endpoint,
                model=self.model_name,
                payload=payload,
                raw_content=content,
            )

    async def self_check_plan(
        self,
        brief: str,
        campaign_id: str,
        normalized_shots: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        self._require_ready()
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
            "model": self.thinking_model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(prompt)},
            ],
            "temperature": 0.2,
            "response_format": self._response_format(),
            "max_tokens": 4096,
        }
        timeout_sec = float(os.getenv("FORGE_KIMI_SELF_CHECK_TIMEOUT_SEC", "90"))
        retries = max(0, int(os.getenv("FORGE_KIMI_SELF_CHECK_RETRIES", "2")))
        last_error = ""
        async with httpx.AsyncClient(timeout=timeout_sec) as client:
            for attempt in range(retries + 1):
                try:
                    resp = await client.post(
                        self.endpoint,
                        headers=self._auth_headers(),
                        json=payload,
                    )
                    if resp.status_code >= 400:
                        last_error = f"self_check_http_error status={resp.status_code} error={resp.text[:500]}"
                        if resp.status_code in {429, 500, 502, 503, 504} and attempt < retries:
                            await asyncio.sleep(1.5 * (attempt + 1))
                            continue
                        raise RuntimeError(last_error)
                    data = resp.json()
                    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    parsed = _extract_json_block(content)
                    if not isinstance(parsed, dict):
                        raise RuntimeError("self_check_invalid_json_shape")
                    return _with_exchange_debug(
                        parsed,
                        stage="kimi_director_self_check",
                        endpoint=self.endpoint,
                        model=self.thinking_model_name,
                        payload=payload,
                        raw_content=content,
                    )
                except (httpx.TimeoutException, httpx.TransportError) as e:
                    last_error = f"self_check_transport_error {e.__class__.__name__}: {str(e).strip()}"
                    if attempt < retries:
                        await asyncio.sleep(1.5 * (attempt + 1))
                        continue
                    raise RuntimeError(last_error)
        raise RuntimeError(last_error or "self_check_failed")

    async def revise_plan(
        self,
        *,
        brief: str,
        campaign_id: str,
        normalized_shots: List[Dict[str, Any]],
        review: Dict[str, Any],
        target_shots: int,
        bible_text: str = "",
        length: str = "",
    ) -> Dict[str, Any]:
        self._require_ready()

        system_prompt = (
            "You are Kimi Director Revision pass. "
            "Rewrite and improve the shot plan using the review findings. "
            "Return only JSON for a full replacement plan."
        )
        payload = {
            "model": self.thinking_model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "campaign_id": campaign_id,
                            "brief": brief,
                            "length": length or "unspecified",
                            "target_shots": int(target_shots),
                            "world_bible_excerpt": (bible_text[:4000] if bible_text else "none"),
                            "multi_person_cast_rule": _multi_person_cast_directive(brief, target_shots) or "not applicable",
                            "current_shots": normalized_shots,
                            "review": review,
                            "required_output_schema": {
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
                            },
                        }
                    ),
                },
            ],
            "temperature": 0.45,
            "response_format": self._response_format(),
            "max_tokens": self._max_tokens_for_target(target_shots),
        }
        timeout_sec = float(os.getenv("FORGE_KIMI_TIMEOUT_SEC", "300"))
        if target_shots >= 20:
            timeout_sec = max(timeout_sec, float(os.getenv("FORGE_KIMI_TIMEOUT_20_SHOTS_SEC", "600")))
        async with httpx.AsyncClient(timeout=timeout_sec) as client:
            resp = await client.post(
                self.endpoint,
                headers=self._auth_headers(),
                json=payload,
            )
            if resp.status_code >= 400:
                raise RuntimeError(f"http_error status={resp.status_code} error={resp.text[:500]}")
            data = resp.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            parsed = _extract_json_block(content)
            if not isinstance(parsed, dict):
                raise RuntimeError("kimi_invalid_revision_shape")
            return _with_exchange_debug(
                parsed,
                stage="kimi_director_revision",
                endpoint=self.endpoint,
                model=self.thinking_model_name,
                payload=payload,
                raw_content=content,
            )

    def build_dev_fallback_plan(self, brief: str, campaign_id: str, target_shots: Optional[int] = None) -> Dict[str, Any]:
        count = max(1, min(int(target_shots or self.requested_shot_count(brief)), 120))
        shots = []
        cast_directive = _multi_person_cast_directive(brief, count)
        cast_seeds = [
            "Mara Ellis, 62-year-old retired park ranger, angular face, silver cropped hair, weathered skin, wiry build, waxed canvas jacket",
            "Dante Brooks, 34-year-old mechanic, broad nose, close-cropped black hair, stocky build, oil-stained work shirt",
            "Leah Novak, 27-year-old graduate student, narrow jaw, dark auburn bob, tall slim build, thrifted denim jacket",
            "Omar Haddad, 46-year-old restaurant owner, heavy-lidded eyes, salt-and-pepper beard, average build, rolled linen sleeves",
            "Priya Raman, 39-year-old civil engineer, round face, wavy black hair tied back, sturdy build, field vest and work boots",
            "Caleb Ivers, 24-year-old bike courier, sharp cheekbones, sandy curls, lean build, reflective streetwear",
            "Naomi Chen, 55-year-old florist, soft square face, gray-streaked hair, short build, patterned apron over cardigan",
            "Mateo Silva, 31-year-old nurse, oval face, dark under-eye texture, athletic build, plain scrubs under a rain shell",
        ]
        for i in range(1, count + 1):
            cast_seed = cast_seeds[(i - 1) % len(cast_seeds)]
            subject = f"{cast_seed}. " if cast_directive else ""
            shots.append({
                "shot_id": f"SHOT_{str(i).zfill(3)}",
                "sequence": i,
                "narrative_intent": "fallback synthetic plan",
                "visual_brief": f"{subject}{brief}. shot {i} with concrete subject action, visible material texture, motivated light source, and strong composition.",
                "characters": [cast_seed.split(",", 1)[0]] if cast_directive else [],
                "environment": "fallback environment",
                "camera_direction": "specific lens framing with clear foreground-midground-background relationship",
                "lighting_direction": "motivated source-based lighting with stable shadow direction",
                "rationale": "development fallback mode",
                "constraints": "dev fallback only; preserve distinct cast identity" if cast_directive else "dev fallback only",
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
