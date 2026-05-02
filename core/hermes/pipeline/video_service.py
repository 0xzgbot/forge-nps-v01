import base64
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable

import httpx

from core.bridge.runtime_config import get_raw_config
from core.dispatch.comfy_client import ComfyUIClient
from .profile_cli import HermesProfileCLI
from .role_skill_mapper import role_skill_scope


class HermesVideoService:
    def __init__(
        self,
        *,
        media_videos: Path,
        active_campaign_getter: Callable[[], str],
        find_shot: Callable[[str], Optional[Dict[str, Any]]],
        resolve_image_path: Callable[[str], Optional[Path]],
        workflow_file_for_id: Callable[[str], Optional[Path]],
    ) -> None:
        self.media_videos = media_videos
        self.active_campaign_getter = active_campaign_getter
        self.find_shot = find_shot
        self.resolve_image_path = resolve_image_path
        self.workflow_file_for_id = workflow_file_for_id
        self.profile_cli = HermesProfileCLI()

    @staticmethod
    def _extract_json_response(text: str) -> Dict[str, Any]:
        raw = (text or "").strip()
        if not raw:
            raise RuntimeError("vision_empty_response")
        if raw.startswith("```"):
            parts = raw.split("```")
            if len(parts) >= 2:
                raw = parts[1].strip()
                if raw.startswith("json"):
                    raw = raw[4:].strip()
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            start = raw.find("{")
            if start < 0:
                raise
            decoder = json.JSONDecoder()
            parsed, _ = decoder.raw_decode(raw[start:])
        if not isinstance(parsed, dict):
            raise RuntimeError("vision_response_json_not_object")
        return parsed

    @staticmethod
    def _image_mime_type(image_path: str) -> str:
        suffix = Path(image_path).suffix.lower()
        if suffix in {".jpg", ".jpeg"}:
            return "image/jpeg"
        if suffix == ".webp":
            return "image/webp"
        return "image/png"

    def _vision_config(self) -> tuple[str, str, str]:
        cfg = get_raw_config()
        active = str(cfg.get("KIMI_VISUAL_ENDPOINT_ACTIVE", "api1") or "api1").strip().lower()
        api1 = str(cfg.get("KIMI_VISUAL_ENDPOINT_API1", "") or cfg.get("NIM_ENDPOINT", "") or "").strip()
        api2 = str(cfg.get("KIMI_VISUAL_ENDPOINT_API2", "") or "").strip()
        endpoint = api2 if active == "api2" and api2 else api1
        model = str(cfg.get("KIMI_VISUAL_MODEL", "") or cfg.get("LMSTUDIO_VISION_MODEL", "") or "").strip()
        api_key = str(cfg.get("KIMI_API_KEY", "") or os.getenv("KIMI_API_KEY", "") or "").strip()
        endpoint = endpoint.rstrip("/")
        if endpoint and not endpoint.endswith("/chat/completions"):
            endpoint = f"{endpoint}/chat/completions"
        if not endpoint:
            raise RuntimeError("vision_endpoint_not_configured")
        if not model:
            raise RuntimeError("vision_model_not_configured")
        return endpoint, model, api_key

    async def _run_vision_video_analysis(
        self,
        *,
        image_b64: str,
        mime_type: str,
        shot: Dict[str, Any],
        duration: int,
        fps: int,
    ) -> Dict[str, Any]:
        endpoint, model, api_key = self._vision_config()
        source_prompt = str(shot.get("best_source_prompt") or "").strip()
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are the Vision Analyst for Hermes video prompting. "
                        "Inspect the actual selected first frame and return raw JSON only. "
                        "Do not invent elements that are not visible."
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Analyze this first frame for an LTX2.3 image-to-video prompt.\n"
                                f"shot_id: {shot.get('shot_id', '')}\n"
                                f"target_duration_sec: {duration}\n"
                                f"fps: {fps}\n"
                                f"source_prompt_field: {shot.get('best_source_field', '')}\n"
                                f"source_prompt: {source_prompt}\n\n"
                                "Return JSON with keys: visible_subjects, setting, composition, lighting, "
                                "camera_motion, subject_motion, environmental_motion, continuity_locks, "
                                "motion_avoid, prompt_seed. The prompt_seed must be one strong paragraph "
                                "grounded in the image for video continuation."
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime_type};base64,{image_b64}"},
                        },
                    ],
                },
            ],
            "temperature": 0.1,
            "max_tokens": 2048,
        }
        headers = {"Content-Type": "application/json"}
        if api_key and endpoint.startswith("https://"):
            headers["Authorization"] = f"Bearer {api_key}"
        async with httpx.AsyncClient(timeout=120.0) as http:
            resp = await http.post(endpoint, headers=headers, json=payload)
        if resp.status_code >= 400:
            raise RuntimeError(f"vision_video_prompt_http_error status={resp.status_code} error={resp.text[:500]}")
        data = resp.json()
        content = (
            (data.get("choices") or [{}])[0]
            .get("message", {})
            .get("content", "")
        )
        result = content if isinstance(content, dict) else self._extract_json_response(str(content))
        if not isinstance(result, dict):
            raise RuntimeError("vision_video_prompt_invalid_response")
        return result

    async def process(
        self,
        *,
        shot_ids: List[str],
        workflow_id: str,
        duration: int = 4,
        fps: int = 24,
        prompt: str = "",
        min_audit_score: float = 0.85,
        min_audit_confidence: float = 0.70,
        require_audit_pass: bool = True,
        allow_failed_override: bool = False,
    ) -> Dict[str, Any]:
        if not shot_ids:
            return {"status": "error", "error": "shot_ids_required"}
        if not workflow_id:
            return {"status": "error", "error": "workflow_id_required"}

        wf = self.workflow_file_for_id(workflow_id)
        if not wf:
            return {"status": "error", "error": f"workflow_missing:{workflow_id}"}

        cfg = get_raw_config()
        primary = (os.getenv("COMFYUI_PRIMARY", "") or str(cfg.get("COMFYUI_PRIMARY", "")) or "").rstrip("/")
        secondary = (os.getenv("COMFYUI_SECONDARY", "") or str(cfg.get("COMFYUI_SECONDARY", "")) or "").rstrip("/")
        hosts = [h for h in [primary, secondary] if h]
        if not hosts:
            return {"status": "error", "error": "comfy_not_configured", "message": "Set COMFYUI_PRIMARY in Settings."}
        dedup_hosts: List[str] = []
        for h in hosts:
            if h not in dedup_hosts:
                dedup_hosts.append(h)

        host = dedup_hosts[0]
        client = ComfyUIClient(host)
        for candidate in dedup_hosts:
            probe = ComfyUIClient(candidate)
            ok, _ = await probe.check_health()
            if ok:
                host = candidate
                client = probe
                break
        campaign_id = (self.active_campaign_getter() or "video_batch").strip() or "video_batch"
        output_dir = self.media_videos / campaign_id
        output_dir.mkdir(parents=True, exist_ok=True)

        results: List[Dict[str, Any]] = []
        for sid in shot_ids:
            shot = self.find_shot(str(sid))
            if not shot:
                results.append({"shot_id": sid, "status": "error", "error": "shot_not_found"})
                continue

            verdict = self._evaluate_video_eligibility(
                shot,
                min_audit_score=min_audit_score,
                min_audit_confidence=min_audit_confidence,
                require_audit_pass=require_audit_pass,
                allow_failed_override=allow_failed_override,
            )
            if not verdict["eligible"]:
                results.append(
                    {
                        "shot_id": sid,
                        "status": "blocked",
                        "error": "blocked_for_video",
                        "reasons": verdict["reasons"],
                        "workflow_id": workflow_id,
                    }
                )
                continue

            image_path = ""
            if shot.get("image_path"):
                image_path = str(shot.get("image_path"))
            elif shot.get("image_url"):
                p = self.resolve_image_path(str(shot.get("image_url") or ""))
                if p:
                    image_path = str(p)
            if not image_path:
                results.append({"shot_id": sid, "status": "error", "error": "image_missing"})
                continue

            prompt_text = (prompt or "").strip() or str(
                shot.get("video_prompt") or shot.get("compiled_prompt") or shot.get("prompt") or shot.get("campaign_brief") or ""
            )
            if duration:
                prompt_text = f"{prompt_text}\n\nvideo_duration_seconds={int(duration)}"
            if fps:
                prompt_text = f"{prompt_text}\nvideo_fps={int(fps)}"

            submit = await client.submit_prompt_for_shot(
                shot_id=f"{sid}__video",
                prompt=prompt_text,
                workflow_path=str(wf),
                output_dir=str(output_dir),
                image_path=image_path,
                wait_for_output=False,
            )
            if submit.get("status") != "success":
                results.append(
                    {
                        "shot_id": sid,
                        "status": "error",
                        "error": submit.get("error", "submit_failed"),
                        "workflow_id": workflow_id,
                    }
                )
                continue
            results.append(
                {
                    "shot_id": sid,
                    "status": "ok",
                    "workflow_id": workflow_id,
                    "prompt_id": submit.get("prompt_id"),
                    "seed": submit.get("seed"),
                    "queued": True,
                }
            )

        return {
            "status": "ok",
            "workflow_id": workflow_id,
            "requested": len(shot_ids),
            "results": results,
            "output_dir": str(output_dir),
        }

    async def generate_prompts(
        self,
        *,
        shot_ids: List[str],
        duration: int = 4,
        fps: int = 24,
        bible_text: str = "",
    ) -> Dict[str, Any]:
        """
        Orchestrate Vision analysis plus Hermes profile agents to generate LTX video prompts.
        Returns {"status": "ok", "prompts": {"SHOT_001": "...", ...}}
        """
        def _is_reindex_text(text: str) -> bool:
            t = str(text or "").strip().lower()
            return t.startswith("reindexed media:") or t.startswith("imported media:")

        def _manifest_brief_for_shot(shot: Dict[str, Any]) -> str:
            try:
                image_path = str(shot.get("image_path") or "")
                if image_path:
                    p = Path(image_path)
                    for parent in [p.parent, p.parent.parent]:
                        manifest = parent / "_campaign.json"
                        if manifest.exists():
                            data = json.loads(manifest.read_text(encoding="utf-8"))
                            brief = str(data.get("brief") or "").strip()
                            if brief:
                                return brief
            except Exception:
                pass
            return ""

        def _best_source_prompt(shot: Dict[str, Any]) -> tuple[str, str]:
            ordered = [
                ("compiled_prompt", shot.get("compiled_prompt")),
                ("raw_kimi_prompt", shot.get("raw_kimi_prompt")),
                ("visual_brief", shot.get("visual_brief")),
                ("prompt", shot.get("prompt")),
                ("campaign_brief", shot.get("campaign_brief")),
            ]
            for key, val in ordered:
                txt = str(val or "").strip()
                if not txt:
                    continue
                if _is_reindex_text(txt):
                    continue
                return txt, key
            manifest_brief = _manifest_brief_for_shot(shot)
            if manifest_brief:
                return manifest_brief, "campaign_manifest_brief"
            return "", "missing_source_prompt"

        # Collect shot data and images
        selected_shot_id_set = set(str(x) for x in shot_ids)
        selected_by_short_id: Dict[str, str] = {}
        shots_data = []
        for sid in shot_ids:
            shot = self.find_shot(str(sid))
            if not shot:
                continue
            short_id = str(shot.get("shot_id") or "").strip()
            if short_id and short_id not in selected_by_short_id:
                selected_by_short_id[short_id] = str(sid)
            image_path = ""
            if shot.get("image_path"):
                image_path = str(shot.get("image_path"))
            elif shot.get("image_url"):
                p = self.resolve_image_path(str(shot.get("image_url") or ""))
                if p:
                    image_path = str(p)
            if not image_path or not Path(image_path).exists():
                continue
            with open(image_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
            best_prompt, prompt_source = _best_source_prompt(shot)
            if not best_prompt:
                best_prompt = "No reliable source prompt is available; use the image pixels as the source of truth."
                prompt_source = "vision_only"
            shots_data.append({
                "shot_id": sid,
                "image_b64": b64,
                "image_mime_type": self._image_mime_type(image_path),
                "visual_brief": str(shot.get("visual_brief", "")),
                "camera_direction": str(shot.get("camera_direction", "")),
                "lighting_direction": str(shot.get("lighting_direction", "")),
                "characters": shot.get("characters", []),
                "compiled_prompt": str(shot.get("compiled_prompt", "")),
                "raw_kimi_prompt": str(shot.get("raw_kimi_prompt", "")),
                "prompt": str(shot.get("prompt", "")),
                "campaign_brief": str(shot.get("campaign_brief", "")),
                "rationale": str(shot.get("rationale", "")),
                "best_source_prompt": best_prompt,
                "best_source_field": prompt_source,
            })

        if not shots_data:
            return {"status": "error", "error": "no_valid_shots"}

        cfg = get_raw_config()
        model = (os.getenv("LMSTUDIO_CHAT_MODEL", "") or str(cfg.get("LMSTUDIO_CHAT_MODEL", ""))).strip()
        if not model:
            return {"status": "error", "error": "hermes_profile_model_not_configured"}

        # Agent 1: Vision Analyst. This must inspect the actual first-frame pixels.
        analysis_results = []
        for s in shots_data:
            try:
                vision_out = await self._run_vision_video_analysis(
                    image_b64=s["image_b64"],
                    mime_type=s["image_mime_type"],
                    shot=s,
                    duration=duration,
                    fps=fps,
                )
            except Exception as e:
                return {
                    "status": "error",
                    "error": "video_vision_analysis_failed",
                    "shot_id": s["shot_id"],
                    "message": str(e),
                }
            content = json.dumps(vision_out, ensure_ascii=False)
            analysis_results.append({
                "shot_id": s["shot_id"],
                "analysis": content,
                "vision_analysis": vision_out,
                "compiled_prompt": s["compiled_prompt"],
                "raw_kimi_prompt": s["raw_kimi_prompt"],
                "prompt": s["prompt"],
                "campaign_brief": s["campaign_brief"],
                "camera_direction": s["camera_direction"],
                "lighting_direction": s["lighting_direction"],
                "characters": s["characters"],
                "rationale": s["rationale"],
                "best_source_prompt": s["best_source_prompt"],
                "best_source_field": s["best_source_field"],
            })

        # Agent 2: Duration Planner.
        duration_payload = {
            "target_total_duration_sec": duration,
            "fps": fps,
            "shots": [
                {
                    "shot_id": a["shot_id"],
                    "analysis": a["analysis"],
                    "compiled_prompt": a["compiled_prompt"],
                }
                for a in analysis_results
            ],
        }
        duration_plan = ""
        planner_task = {
            "task": "video_duration_plan",
            "target_total_duration_sec": duration,
            "fps": fps,
            "shots": duration_payload["shots"],
            "instructions": (
                "Allocate duration/frames per shot for LTX2.3 with coherent pacing. "
                "Output JSON only: {\"plan\":[{\"shot_id\":\"...\",\"duration_sec\":N,\"frames\":N,\"reasoning\":\"...\"}]}"
            ),
        }
        planner_out = await self.profile_cli.run_json("critic", planner_task)
        if isinstance(planner_out, dict) and planner_out.get("plan"):
            plan = planner_out.get("plan")
            if isinstance(plan, dict):
                items = plan.get("shots") if isinstance(plan.get("shots"), list) else []
                normalized_items = []
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    normalized_items.append({
                        "shot_id": item.get("shot_id", ""),
                        "duration_sec": item.get("duration_sec", duration),
                        "frames": item.get("frames", item.get("num_frames", item.get("frame_count", duration * fps))),
                        "reasoning": item.get("reasoning", "Hermes duration profile allocation"),
                    })
                duration_plan = json.dumps({"plan": normalized_items})
            elif isinstance(plan, list):
                duration_plan = json.dumps({"plan": plan})
        if not duration_plan:
            return {"status": "error", "error": "video_duration_plan_failed"}

        # Agent 3: Prompt Engineer (Hermes compiler profile, strict LTX2.3 schema)
        prompt_payload = {
            "lore_bible_excerpt": bible_text[:4000] if bible_text else "none",
            "duration_plan": json.loads(duration_plan) if isinstance(duration_plan, str) else duration_plan,
            "shots": analysis_results,
            "fps": fps,
        }
        prompts_data = {}
        prompt_raw_text = ""
        compiler_scope = role_skill_scope("prompt_compiler")
        compiler_task = {
            "task": "ltx23_video_prompt_compile",
            "standard": "ltx23-prompting-workflow",
            "shots": analysis_results,
            "duration_plan": prompt_payload["duration_plan"],
            "fps": fps,
            "allowed_skill_patterns": compiler_scope.get("patterns", []),
            "instructions": (
                "Return strict JSON only with shape: "
                "{\"prompts\": {\"SHOT_001\": {\"duration_sec\": N, \"fps\": N, "
                "\"segments\": [{\"time_range\": \"0-1s\", \"prompt\": \"...\"}], "
                "\"full_prompt\": \"...\", \"negative\": \"...\"}}}. "
                "Prompts must be detailed, model-specific LTX2.3 image-to-video prompts grounded in "
                "the vision_analysis. Do not output generic text like preserve identity and gentle "
                "parallax by itself. Include specific visible subjects, exact environment, camera "
                "movement, subject/environment motion, lighting continuity, temporal pacing, and "
                "concrete negative constraints."
            ),
        }
        compiler_out = await self.profile_cli.run_json("compiler", compiler_task)
        if isinstance(compiler_out, dict):
            prompt_raw_text = json.dumps(compiler_out, ensure_ascii=False)[:2000]
            prompts_data = compiler_out.get("prompts", {}) if isinstance(compiler_out.get("prompts"), dict) else {}
        if not prompts_data:
            return {"status": "error", "error": "video_prompt_compile_failed"}

        # Flatten to simple video_prompt strings
        flat_prompts = {}
        for sid, pdata in prompts_data.items():
            if isinstance(pdata, dict):
                segments = pdata.get("segments", [])
                full = pdata.get("full_prompt", "")
                if segments:
                    flat_prompts[sid] = " | ".join([f"[{s.get('time_range', '')}] {s.get('prompt', '')}" for s in segments])
                elif full:
                    flat_prompts[sid] = full
                else:
                    flat_prompts[sid] = str(pdata)
            else:
                flat_prompts[sid] = str(pdata)

        # Normalize prompt keys back to selected internal shot IDs.
        # Models often return SHOT_001-style keys instead of full internal IDs.
        normalized_prompts: Dict[str, str] = {}
        unmapped_keys: List[str] = []
        for key, val in flat_prompts.items():
            k = str(key)
            target_id: Optional[str] = None
            if k in selected_shot_id_set:
                target_id = k
            elif k in selected_by_short_id:
                target_id = selected_by_short_id[k]
            else:
                # Last chance: check if any selected shot's internal id ends with "__{short_id}__workflow"
                # and prompt key is short shot id.
                for selected_id in selected_shot_id_set:
                    if f"__{k}__" in selected_id:
                        target_id = selected_id
                        break
            if target_id:
                normalized_prompts[target_id] = val
            else:
                unmapped_keys.append(k)

        if not normalized_prompts and flat_prompts and shots_data:
            return {
                "status": "error",
                "error": "video_prompt_key_mapping_failed",
                "unmapped_prompt_keys": unmapped_keys,
                "selected_shot_ids": list(selected_shot_id_set),
            }

        return {
            "status": "ok",
            "prompts": normalized_prompts,
            "raw": prompts_data,
            "analysis_results": analysis_results,
            "duration_plan": duration_plan,
            "unmapped_prompt_keys": unmapped_keys,
            "selected_count": len(selected_shot_id_set),
            "prompt_raw_text": prompt_raw_text[:2000],
            "video_prompt_backend": "profile_cli",
        }

    @staticmethod
    def _evaluate_video_eligibility(
        shot: Dict[str, Any],
        *,
        min_audit_score: float,
        min_audit_confidence: float,
        require_audit_pass: bool,
        allow_failed_override: bool,
    ) -> Dict[str, Any]:
        reasons: List[str] = []
        audit_status = str(shot.get("audit_status", "") or "").strip().lower()
        score = float(shot.get("audit_score", 0) or 0)
        confidence = float(shot.get("audit_confidence", 0) or 0)
        issues = [str(x) for x in (shot.get("audit_issues") or [])]
        critical = [str(x) for x in (shot.get("audit_critical_failures") or [])]
        merged = " ".join([*issues, *critical]).lower()
        hard_fail_terms = (
            "extra fingers", "extra limbs", "deformed", "dog head", "broken face",
            "identity mismatch", "wrong identity", "reflection contradiction", "mirror contradiction",
        )
        has_hard_fail = any(t in merged for t in hard_fail_terms)
        if has_hard_fail:
            reasons.append("hard_fail_visual")
        if require_audit_pass and not audit_status:
            reasons.append("audit_missing")
        if require_audit_pass and audit_status != "pass":
            reasons.append("audit_not_passed")
        if score < min_audit_score:
            reasons.append("score_below_threshold")
        if confidence < min_audit_confidence:
            reasons.append("confidence_below_threshold")
        has_soft_failures = len(reasons) > 0 and not has_hard_fail
        eligible = (len(reasons) == 0) or (bool(allow_failed_override) and has_soft_failures)
        return {"eligible": eligible, "reasons": reasons, "has_hard_fail": has_hard_fail}
