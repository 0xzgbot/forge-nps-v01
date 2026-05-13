import json
import os
import random
import uuid
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional

from core.dispatch.comfy_client import ComfyUIClient
from core.bridge.runtime_config import get_raw_config

from .profile_cli import HermesProfileCLI
from .role_skill_mapper import role_skill_scope
from .state_machine import transition_shot


class HermesAuditService:
    def __init__(
        self,
        *,
        shots_store: List[Dict[str, Any]],
        find_shot: Callable[[str], Optional[Dict[str, Any]]],
        resolve_image_path: Callable[[str], Optional[Path]],
        now_iso: Callable[[], str],
        record_event: Callable[..., None],
        audit_render: Callable[[str, str, str], Awaitable[Dict[str, Any]]],
        workflow_file_for_id: Callable[[str], Optional[Path]],
        media_images: Path,
        get_hermes_bridge: Callable[[], Any],
    ) -> None:
        self.shots_store = shots_store
        self.find_shot = find_shot
        self.resolve_image_path = resolve_image_path
        self.now_iso = now_iso
        self.record_event = record_event
        self.audit_render = audit_render
        self.workflow_file_for_id = workflow_file_for_id
        self.media_images = media_images
        self.get_hermes_bridge = get_hermes_bridge
        self.profile_cli = HermesProfileCLI()

    def _persist_media_shot_metadata(self, shot: Dict[str, Any]) -> None:
        image_path = str(shot.get("image_path") or "").strip()
        if not image_path:
            resolved = self.resolve_image_path(str(shot.get("image_url") or ""))
            image_path = str(resolved) if resolved else ""
        if not image_path:
            return
        path = Path(image_path)
        if not path.exists():
            return
        fields = {
            "audit_status",
            "audit_score",
            "audit_issues",
            "audit_model_score",
            "audit_checks_score",
            "audit_confidence",
            "audit_model_passed",
            "audit_final_passed",
            "audit_checks",
            "audit_critical_failures",
            "audit_noncritical_issues",
            "audit_decision_reasons",
            "audit_raw_response",
            "audit_timestamp",
            "audit_model",
            "retry_of",
            "parent_shot_id",
            "remediation_reason",
            "remediated_prompt",
            "original_compiled_prompt",
            "remediation_model",
            "profile_used",
            "profile_backend",
            "skills_scope_role",
            "skills_scope_patterns",
            "skills_scope_version",
            "video_prompt",
            "video_prompt_source",
            "negative_prompt",
            "workflow_profile",
            "model_standard_name",
            "model_standard_version",
            "model_standard_source",
            "model_standard_rules",
            "sections",
            "kimi_plan",
            "kimi_rationale",
        }
        metadata_path = path.parent / "_shot_metadata.json"
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}
            if not isinstance(metadata, dict):
                metadata = {}
        except Exception:
            metadata = {}
        existing = metadata.get(path.stem)
        if not isinstance(existing, dict):
            existing = {}
        for key in fields:
            if key in shot:
                existing[key] = shot.get(key)
        existing["updated_at"] = self.now_iso()
        metadata[path.stem] = existing
        tmp = path.parent / "._shot_metadata.json.tmp"
        tmp.write_text(json.dumps(metadata, ensure_ascii=True, indent=2), encoding="utf-8")
        tmp.replace(metadata_path)

    @staticmethod
    def _audit_event_extra(shot: Dict[str, Any], score: float) -> Dict[str, Any]:
        return {
            "audit_score": score,
            "audit_model_score": shot.get("audit_model_score"),
            "audit_checks_score": shot.get("audit_checks_score"),
            "audit_issues": shot.get("audit_issues") or [],
            "audit_critical_failures": shot.get("audit_critical_failures") or [],
            "audit_noncritical_issues": shot.get("audit_noncritical_issues") or [],
            "audit_decision_reasons": shot.get("audit_decision_reasons") or [],
        }

    @staticmethod
    def _needs_full_body_framing_fix(shot: Dict[str, Any]) -> bool:
        source = " ".join(
            [
                str(shot.get("compiled_prompt") or shot.get("prompt") or ""),
                " ".join(str(x) for x in (shot.get("audit_issues") or [])),
                " ".join(str(x) for x in (shot.get("audit_critical_failures") or [])),
                " ".join(str(x) for x in (shot.get("audit_decision_reasons") or [])),
            ]
        ).lower()
        prompt_requires = any(
            phrase in source
            for phrase in ("full-body", "full body", "full-length", "full length", "head-to-toe", "head to toe")
        )
        crop_failed = any(
            phrase in source
            for phrase in (
                "cut off",
                "cuts off",
                "cropped",
                "mid-thigh",
                "mid thigh",
                "below the knees",
                "knees",
                "shins",
                "feet",
                "not full body",
                "not a full-body",
            )
        )
        return prompt_requires and crop_failed

    @staticmethod
    def _enforce_full_body_remediation(prompt: str) -> str:
        base = str(prompt or "").strip()
        full_body_directive = (
            "MANDATORY CORRECTION: true head-to-toe full-body studio portrait. "
            "The entire person must fit inside the frame: top of head, torso, both legs, ankles, shoes, and both feet fully visible. "
            "Show the studio floor under both shoes and leave clear padding above the head and below the feet. "
            "Camera is pulled back for a wide vertical 9:16 composition, subject occupies about 70 percent of image height, not a close-up, not a three-quarter crop, not knee-up, not thigh-up. "
            "Use a clean seamless white cyclorama studio background with visible floor-to-wall curve."
        )
        negative_directive = (
            "Avoid cropped legs, cropped feet, hidden shoes, knee crop, thigh crop, ankle crop, close portrait framing, waist-up framing, and oversized subject scale."
        )
        if "MANDATORY CORRECTION: true head-to-toe" in base:
            return base
        return f"{full_body_directive} {base} {negative_directive}".strip()

    async def reprocess(self, shot_ids: List[str]) -> Dict[str, Any]:
        requested = len(shot_ids)
        updated = 0
        results = []
        for shot_id in shot_ids:
            s = self.find_shot(shot_id)
            if not s:
                results.append({"shot_id": shot_id, "status": "missing"})
                continue
            image_path = self.resolve_image_path(s.get("image_path") or s.get("image_url", ""))
            if not image_path:
                results.append({"shot_id": shot_id, "status": "missing_image"})
                continue

            try:
                transition_shot(s, "audit_started")
            except Exception:
                # Re-audit can be requested for previously failed/final shots.
                # Normalize back to rendered then enter audit_started.
                s["state"] = "rendered"
                s["status"] = "rendered"
                transition_shot(s, "audit_started")
            self.record_event("audit_started", shot_id=shot_id, campaign_id=s.get("campaign_id", ""), workflow_id=s.get("workflow_id", ""), source=s.get("source", "campaign"))
            audit = await self.audit_render(str(image_path), s.get("compiled_prompt") or s.get("prompt", ""), s.get("campaign_id", "default"))
            score = float(audit.get("score", 0) or 0)
            passed = bool(audit.get("passed", False))
            s["audit_model"] = os.getenv("KIMI_VISUAL_MODEL", os.getenv("LMSTUDIO_VISION_MODEL", "qwen3.6-35b-a3b"))
            s["audit_status"] = "pass" if passed else "fail"
            s["audit_score"] = score
            s["audit_issues"] = audit.get("issues", [])
            s["audit_model_score"] = float(audit.get("model_score", score) or 0)
            s["audit_checks_score"] = float(audit.get("checks_score", 0) or 0)
            s["audit_confidence"] = float(audit.get("confidence", 0) or 0)
            s["audit_model_passed"] = bool(audit.get("model_passed", passed))
            s["audit_final_passed"] = bool(audit.get("final_passed", passed))
            s["audit_checks"] = audit.get("checks", {})
            s["audit_critical_failures"] = audit.get("critical_failures", [])
            s["audit_noncritical_issues"] = audit.get("noncritical_issues", [])
            s["audit_decision_reasons"] = audit.get("audit_decision_reasons", [])
            s["audit_raw_response"] = audit
            s["audit_timestamp"] = self.now_iso()
            expected_traits = ((s.get("identity_pack") or {}).get("identity_tokens") or []) if isinstance(s.get("identity_pack"), dict) else []
            s["identity_expected_traits"] = expected_traits
            detected_notes = []
            detected_notes.extend([str(x) for x in (s.get("audit_decision_reasons") or [])[:4]])
            detected_notes.extend([str(x) for x in (s.get("audit_issues") or [])[:4]])
            s["identity_detected_notes"] = detected_notes[:6]
            if s.get("identity_type"):
                s["identity_status"] = "pass" if passed else "fail"
                s["identity_score"] = score
                s["identity_fail_reasons"] = [] if passed else detected_notes[:4]
            try:
                transition_shot(s, "audited_pass" if passed else "audited_fail")
            except Exception:
                # If state drift occurred, force a consistent terminal audit state.
                s["state"] = "audit_started"
                s["status"] = "auditing"
                transition_shot(s, "audited_pass" if passed else "audited_fail")
            self._persist_media_shot_metadata(s)
            self.record_event("audit_result", shot_id=shot_id, campaign_id=s.get("campaign_id", ""), workflow_id=s.get("workflow_id", ""), source=s.get("source", "campaign"), success=passed, extra=self._audit_event_extra(s, score))
            updated += 1
            results.append({
                "shot_id": shot_id,
                "status": "ok",
                "audit_status": s["audit_status"],
                "score": score,
                "issues": s["audit_issues"],
            })
        return {"status": "ok", "requested": requested, "updated": updated, "results": results}

    async def remediate(self, shot_ids: List[str], max_retries: int = 1) -> Dict[str, Any]:
        # max_retries preserved for API compatibility; currently one pass per selected shot.
        _ = max_retries
        hermes = self.get_hermes_bridge()
        cfg = get_raw_config()
        host = (
            os.getenv("COMFYUI_PRIMARY", "")
            or str(cfg.get("COMFYUI_PRIMARY", ""))
        ).rstrip("/")
        if not host:
            return {
                "status": "error",
                "error": "comfy_not_configured",
                "message": "COMFYUI_PRIMARY is not configured",
            }
        comfy = ComfyUIClient(host)
        results = []
        for shot_id in shot_ids:
            s = self.find_shot(shot_id)
            if not s:
                results.append({"shot_id": shot_id, "status": "missing"})
                continue
            if s.get("audit_status") != "fail":
                results.append({"shot_id": shot_id, "status": "skipped", "reason": "Shot is not failed"})
                continue

            transition_shot(s, "remediation_started")
            self.record_event("remediation_started", shot_id=shot_id, campaign_id=s.get("campaign_id", ""), workflow_id=s.get("workflow_id", ""), source=s.get("source", "campaign"))

            remediation_reason = "; ".join(s.get("audit_issues", [])[:4]) or "audit_fail"
            diagnosis = None
            remediator_scope = role_skill_scope("remediation_reprompter")
            cli_diag = await self.profile_cli.run_json(
                "remediator",
                {
                    "task": "remediate_failed_image_prompt",
                    "campaign_id": s.get("campaign_id", ""),
                    "shot_id": shot_id,
                    "workflow_id": s.get("workflow_id", ""),
                    "original_prompt": s.get("compiled_prompt") or s.get("prompt", ""),
                    "audit_result": s.get("audit_raw_response", {}),
                    "audit_issues": s.get("audit_issues", []),
                    "remediation_reason": remediation_reason,
                    "required_fix_behavior": (
                        "Return a materially revised fix_prompt, not the original prompt with minor suffixes. "
                        "If the failure says full-body, head-to-toe, cropped legs, cropped knees, cropped shins, or feet not visible, "
                        "the fix_prompt must explicitly require head-to-toe framing, both feet and shoes fully visible, visible studio floor below the feet, "
                        "clear padding above head and below shoes, and a pulled-back wide vertical studio composition."
                    ),
                    "allowed_skill_patterns": remediator_scope.get("patterns", []),
                },
            )
            try:
                diagnosis = await hermes.analyze_failure(
                    visual_audit_result=s.get("audit_raw_response", {}),
                    original_prompt=s.get("compiled_prompt") or s.get("prompt", ""),
                )
            except Exception:
                diagnosis = None
            remediated_prompt = ""
            remediation_model = "hermes_local"
            if isinstance(cli_diag, dict):
                remediated_prompt = str(cli_diag.get("fix_prompt") or cli_diag.get("compiled_prompt") or cli_diag.get("prompt") or "").strip()
                if remediated_prompt:
                    remediation_model = "remediator_profile_cli"
            if isinstance(diagnosis, dict):
                if not remediated_prompt:
                    remediated_prompt = str(diagnosis.get("fix_prompt") or "").strip()
            if not remediated_prompt:
                remediated_prompt = (s.get("compiled_prompt") or s.get("prompt", "")) + f", corrective constraints: {remediation_reason}"
            if self._needs_full_body_framing_fix(s):
                remediated_prompt = self._enforce_full_body_remediation(remediated_prompt)

            retry_shot_id = f"{shot_id}__retry_{uuid.uuid4().hex[:6]}"
            retry_record = dict(s)
            retry_record["id"] = retry_shot_id
            retry_record["retry_of"] = shot_id
            retry_record["parent_shot_id"] = shot_id
            retry_record["prompt"] = remediated_prompt
            retry_record["compiled_prompt"] = remediated_prompt
            retry_record["video_prompt"] = (
                f"{remediated_prompt}. "
                "LTX2.3 image-to-video continuation: preserve corrected identity/anatomy and scene geometry; "
                "add controlled motion with stable lighting continuity; avoid anatomy drift, face morphing, "
                "extra limbs/fingers, texture flicker, and warped reflections."
            )
            retry_record["remediation_reason"] = remediation_reason
            retry_record["remediated_prompt"] = remediated_prompt
            retry_record["original_compiled_prompt"] = s.get("compiled_prompt", "")
            retry_record["remediation_model"] = remediation_model
            retry_record["profile_used"] = "remediation_reprompter"
            retry_record["profile_backend"] = "lmstudio" if remediation_model == "remediator_profile_cli" else "local"
            retry_record["skills_scope_role"] = "remediation_reprompter"
            retry_record["skills_scope_patterns"] = remediator_scope.get("patterns", [])
            retry_record["skills_scope_version"] = remediator_scope.get("map_version", "unknown")
            if isinstance(cli_diag, dict):
                retry_record["skills_used"] = cli_diag.get("skills_used", retry_record.get("skills_used", []))
            retry_record["audit_status"] = ""
            retry_record["seed"] = random.randint(1, 2**31 - 1)
            transition_shot(retry_record, "retry_queued")
            self.shots_store.append(retry_record)

            self.record_event("retry_linked", shot_id=retry_shot_id, campaign_id=s.get("campaign_id", ""), workflow_id=s.get("workflow_id", ""), source=s.get("source", "campaign"), extra={"retry_of": shot_id})
            self.record_event("render_attempt", shot_id=retry_shot_id, campaign_id=s.get("campaign_id", ""), workflow_id=s.get("workflow_id", ""), source=s.get("source", "campaign"))

            wf = self.workflow_file_for_id(s.get("workflow_id", ""))
            if not wf:
                transition_shot(retry_record, "final_fail")
                self.record_event("remediation_result", shot_id=retry_shot_id, campaign_id=s.get("campaign_id", ""), workflow_id=s.get("workflow_id", ""), source=s.get("source", "campaign"), success=False, extra={"reason": "workflow_missing"})
                results.append({"shot_id": shot_id, "status": "error", "reason": "workflow_missing"})
                continue

            submit = await comfy.submit_prompt_for_shot(
                shot_id=retry_shot_id,
                prompt=remediated_prompt,
                workflow_path=str(wf),
                seed=retry_record.get("seed"),
                output_dir=str(self.media_images / s.get("campaign_id", "remediation")),
            )
            if submit.get("status") != "success":
                transition_shot(retry_record, "final_fail")
                err = submit.get("error", "render_failed")
                self.record_event("remediation_result", shot_id=retry_shot_id, campaign_id=s.get("campaign_id", ""), workflow_id=s.get("workflow_id", ""), source=s.get("source", "campaign"), success=False, extra={"reason": err})
                self.record_event("final_outcome", shot_id=retry_shot_id, campaign_id=s.get("campaign_id", ""), workflow_id=s.get("workflow_id", ""), source=s.get("source", "campaign"), success=False)
                results.append({"shot_id": shot_id, "status": "error", "reason": err})
                continue

            saved = submit.get("saved_files", [])
            image_path = saved[0] if saved else ""
            retry_record["prompt_id"] = submit.get("prompt_id")
            transition_shot(retry_record, "retry_rendered")
            if image_path:
                retry_record["image_path"] = image_path
                try:
                    rel = Path(image_path).resolve().relative_to(self.media_images.resolve())
                    retry_record["image_url"] = f"/external-renders/{rel.as_posix()}"
                except Exception:
                    retry_record["image_url"] = f"/external-renders/{Path(image_path).name}"
            self.record_event("render_result", shot_id=retry_shot_id, campaign_id=s.get("campaign_id", ""), workflow_id=s.get("workflow_id", ""), source=s.get("source", "campaign"), success=True)

            if image_path:
                transition_shot(retry_record, "audit_started")
                self.record_event("audit_started", shot_id=retry_shot_id, campaign_id=s.get("campaign_id", ""), workflow_id=s.get("workflow_id", ""), source=s.get("source", "campaign"))
                try:
                    audit = await self.audit_render(image_path, remediated_prompt, s.get("campaign_id", "remediation"))
                except Exception as e:
                    transition_shot(retry_record, "final_fail")
                    retry_record["audit_status"] = "error"
                    retry_record["audit_error"] = f"audit_exception:{e}"
                    retry_record["audit_timestamp"] = self.now_iso()
                    self._persist_media_shot_metadata(retry_record)
                    self.record_event("audit_result", shot_id=retry_shot_id, campaign_id=s.get("campaign_id", ""), workflow_id=s.get("workflow_id", ""), source=s.get("source", "campaign"), success=False, extra={"reason": retry_record["audit_error"]})
                    self.record_event("remediation_result", shot_id=retry_shot_id, campaign_id=s.get("campaign_id", ""), workflow_id=s.get("workflow_id", ""), source=s.get("source", "campaign"), success=False, extra={"reason": retry_record["audit_error"]})
                    self.record_event("final_outcome", shot_id=retry_shot_id, campaign_id=s.get("campaign_id", ""), workflow_id=s.get("workflow_id", ""), source=s.get("source", "campaign"), success=False)
                    results.append({"shot_id": shot_id, "status": "error", "reason": retry_record["audit_error"], "retry_shot_id": retry_shot_id})
                    continue
                score = float(audit.get("score", 0) or 0)
                passed = bool(audit.get("passed", False))
                retry_record["audit_model"] = os.getenv("KIMI_VISUAL_MODEL", os.getenv("LMSTUDIO_VISION_MODEL", "qwen3.6-35b-a3b"))
                retry_record["audit_status"] = "pass" if passed else "fail"
                retry_record["audit_score"] = score
                retry_record["audit_issues"] = audit.get("issues", [])
                retry_record["audit_model_score"] = float(audit.get("model_score", score) or 0)
                retry_record["audit_checks_score"] = float(audit.get("checks_score", 0) or 0)
                retry_record["audit_confidence"] = float(audit.get("confidence", 0) or 0)
                retry_record["audit_model_passed"] = bool(audit.get("model_passed", passed))
                retry_record["audit_final_passed"] = bool(audit.get("final_passed", passed))
                retry_record["audit_checks"] = audit.get("checks", {})
                retry_record["audit_critical_failures"] = audit.get("critical_failures", [])
                retry_record["audit_noncritical_issues"] = audit.get("noncritical_issues", [])
                retry_record["audit_decision_reasons"] = audit.get("audit_decision_reasons", [])
                retry_record["audit_raw_response"] = audit
                retry_record["audit_timestamp"] = self.now_iso()
                expected_traits = ((retry_record.get("identity_pack") or {}).get("identity_tokens") or []) if isinstance(retry_record.get("identity_pack"), dict) else []
                retry_record["identity_expected_traits"] = expected_traits
                detected_notes = []
                detected_notes.extend([str(x) for x in (retry_record.get("audit_decision_reasons") or [])[:4]])
                detected_notes.extend([str(x) for x in (retry_record.get("audit_issues") or [])[:4]])
                retry_record["identity_detected_notes"] = detected_notes[:6]
                if retry_record.get("identity_type"):
                    retry_record["identity_status"] = "pass" if passed else "fail"
                    retry_record["identity_score"] = score
                    retry_record["identity_fail_reasons"] = [] if passed else detected_notes[:4]
                transition_shot(retry_record, "audited_pass" if passed else "audited_fail")
                transition_shot(retry_record, "final_pass" if passed else "final_fail")
                self._persist_media_shot_metadata(retry_record)
                audit_extra = self._audit_event_extra(retry_record, score)
                self.record_event("audit_result", shot_id=retry_shot_id, campaign_id=s.get("campaign_id", ""), workflow_id=s.get("workflow_id", ""), source=s.get("source", "campaign"), success=passed, extra=audit_extra)
                self.record_event("remediation_result", shot_id=retry_shot_id, campaign_id=s.get("campaign_id", ""), workflow_id=s.get("workflow_id", ""), source=s.get("source", "campaign"), success=passed, extra=audit_extra)
                self.record_event("final_outcome", shot_id=retry_shot_id, campaign_id=s.get("campaign_id", ""), workflow_id=s.get("workflow_id", ""), source=s.get("source", "campaign"), success=passed)
                results.append({
                    "shot_id": shot_id,
                    "status": "ok",
                    "retry_shot_id": retry_shot_id,
                    "retry_audit_status": retry_record["audit_status"],
                    "image_url": retry_record.get("image_url"),
                })
            else:
                transition_shot(retry_record, "final_fail")
                self.record_event("final_outcome", shot_id=retry_shot_id, campaign_id=s.get("campaign_id", ""), workflow_id=s.get("workflow_id", ""), source=s.get("source", "campaign"), success=False)
                results.append({"shot_id": shot_id, "status": "error", "reason": "no_output"})

        return {"status": "ok", "results": results}
