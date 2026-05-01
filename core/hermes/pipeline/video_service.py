import base64
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable

from core.bridge.runtime_config import get_raw_config
from core.bridge.lmstudio_client import LMStudioClient
from core.dispatch.comfy_client import ComfyUIClient


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
        host = (
            os.getenv("COMFYUI_PRIMARY", "")
            or str(cfg.get("COMFYUI_PRIMARY", ""))
            or "http://localhost:8188"
        ).rstrip("/")
        client = ComfyUIClient(host)
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
        Orchestrate 3 LM Studio agents to generate LTX video prompts.
        Returns {"status": "ok", "prompts": {"SHOT_001": "...", ...}}
        """
        # Collect shot data and images
        shots_data = []
        for sid in shot_ids:
            shot = self.find_shot(str(sid))
            if not shot:
                continue
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
            shots_data.append({
                "shot_id": sid,
                "image_b64": b64,
                "visual_brief": str(shot.get("visual_brief", "")),
                "camera_direction": str(shot.get("camera_direction", "")),
                "lighting_direction": str(shot.get("lighting_direction", "")),
                "characters": shot.get("characters", []),
                "compiled_prompt": str(shot.get("compiled_prompt", "")),
                "rationale": str(shot.get("rationale", "")),
            })

        if not shots_data:
            return {"status": "error", "error": "no_valid_shots"}

        client = LMStudioClient(timeout=120.0)
        model = os.getenv("LMSTUDIO_CHAT_MODEL", "")
        if not model:
            models = client.list_models()
            model = models[0] if models else ""

        # Agent 1: Image Analyst
        analysis_results = []
        for s in shots_data:
            messages = [
                {"role": "system", "content": (
                    "You are a Visual Analyst for an AI filmmaking pipeline. "
                    "Analyze the provided rendered image. Extract: subject action, implied motion, "
                    "camera movement cues, lighting mood, background elements, and composition. "
                    "Be concise (2-3 sentences)."
                )},
                {"role": "user", "content": [
                    {"type": "text", "text": f"Shot: {s['shot_id']} | Camera: {s['camera_direction']} | Lighting: {s['lighting_direction']}"},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{s['image_b64']}"}},
                ]},
            ]
            resp = await client.chat_async(messages=messages, model=model, temperature=0.3, max_tokens=512)
            content = ""
            try:
                content = resp["choices"][0]["message"]["content"]
            except Exception:
                content = "Analysis unavailable"
            analysis_results.append({
                "shot_id": s["shot_id"],
                "analysis": content,
                "compiled_prompt": s["compiled_prompt"],
                "camera_direction": s["camera_direction"],
                "lighting_direction": s["lighting_direction"],
                "characters": s["characters"],
                "rationale": s["rationale"],
            })

        # Agent 2: Duration Planner
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
        duration_messages = [
            {"role": "system", "content": (
                "You are a Duration Planner for LTX-Video generation. "
                "Given shot analyses and a target total duration, allocate seconds and frames per shot. "
                "LTX-Video works at 24-25fps. Output ONLY a JSON object: "
                '{"plan": [{"shot_id": "...", "duration_sec": N, "frames": N, "reasoning": "..."}]}'
            )},
            {"role": "user", "content": json.dumps(duration_payload)},
        ]
        duration_resp = await client.chat_async(messages=duration_messages, model=model, temperature=0.2, max_tokens=1024, json_mode=True)
        duration_plan = ""
        try:
            duration_plan = duration_resp["choices"][0]["message"]["content"]
        except Exception:
            duration_plan = json.dumps({"plan": [{"shot_id": a["shot_id"], "duration_sec": max(1, duration // len(analysis_results)), "frames": max(1, duration // len(analysis_results)) * fps, "reasoning": "even split"} for a in analysis_results]})

        # Agent 3: Prompt Engineer
        prompt_payload = {
            "lore_bible_excerpt": bible_text[:4000] if bible_text else "none",
            "duration_plan": json.loads(duration_plan) if isinstance(duration_plan, str) else duration_plan,
            "shots": analysis_results,
            "fps": fps,
        }
        prompt_messages = [
            {"role": "system", "content": (
                "You are an LTX-Video Prompt Engineer. Write time-segmented video generation prompts. "
                "Each prompt must break the shot into temporal segments (e.g., 0-1s, 1-2s, 2-3s) "
                "with specific motion descriptors, camera moves, and transitions for each segment. "
                "Output ONLY a JSON object: "
                '{"prompts": {"SHOT_001": {"duration_sec": N, "fps": N, "segments": [{"time_range": "0-1s", "prompt": "..."}], "full_prompt": "..."}}}'
            )},
            {"role": "user", "content": json.dumps(prompt_payload)},
        ]
        prompt_resp = await client.chat_async(messages=prompt_messages, model=model, temperature=0.4, max_tokens=2048, json_mode=True)
        prompts_data = {}
        try:
            raw = prompt_resp["choices"][0]["message"]["content"]
            if isinstance(raw, str):
                prompts_data = json.loads(raw).get("prompts", {})
            else:
                prompts_data = raw.get("prompts", {})
        except Exception:
            prompts_data = {}

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

        return {"status": "ok", "prompts": flat_prompts, "raw": prompts_data}

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
