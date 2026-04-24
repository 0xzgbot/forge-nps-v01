import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger("RemediationLoop")


class RemediationLoop:
    """
    Iterative self-healing engine. Three escalation tiers:
      iter 1 — Hermes skill registry fix
      iter 2 — Kimi root-cause escalation
      iter 3 — Direct Kimi prompt rewrite, final attempt
    After max_iterations marks shot for human review and continues.
    """

    def __init__(
        self,
        hermes,
        auditor,
        session_manager,
        max_iterations: int = 3,
    ):
        self.hermes = hermes
        self.auditor = auditor
        self.session_manager = session_manager
        self.max_iterations = max_iterations
        self._iteration_logs: Dict[str, List[Dict]] = {}

    async def remediate(
        self,
        result: Dict[str, Any],
        audit_report: Dict[str, Any],
        director_schema: Dict[str, Any],
        lore_paths: List[str],
    ) -> Dict[str, Any]:
        shot_id = audit_report.get("shot_id", result.get("shot_id", "UNKNOWN"))
        self._iteration_logs.setdefault(shot_id, [])

        current_audit = audit_report
        asset_path = result.get("asset_path", "")
        success = False

        for iteration in range(1, self.max_iterations + 1):
            method, fix_applied, kimi_root_cause = await self._run_iteration(
                iteration, shot_id, current_audit, director_schema, lore_paths
            )

            # Re-generate with updated description
            regen_description = fix_applied or current_audit.get("remediation_prompt", "")
            re_result = await self.hermes.dispatch_shots(
                [{"shot_id": shot_id, "description": regen_description}],
                director_schema,
            )
            asset_path = re_result[0].get("asset_path", asset_path) if re_result else asset_path

            current_audit = await self.auditor.audit_asset(regen_description, shot_id)

            log_entry = {
                "shot_id": shot_id,
                "iteration": iteration,
                "method": method,
                "kimi_root_cause": kimi_root_cause,
                "fix_applied": fix_applied,
                "audit_result": {
                    "is_consistent": current_audit["is_consistent"],
                    "confidence_score": current_audit.get("confidence_score", 0.0),
                },
                "timestamp": datetime.now().isoformat(),
            }
            self._iteration_logs[shot_id].append(log_entry)
            self._persist_log(shot_id, iteration, log_entry)

            if current_audit["is_consistent"]:
                logger.info(f"[REMEDIATION] {shot_id} resolved at iteration {iteration} via {method}.")
                success = True
                break

            logger.warning(f"[REMEDIATION] {shot_id} still failing after iteration {iteration}.")

        if not success:
            logger.error(f"[REMEDIATION] {shot_id} unresolved after {self.max_iterations} iterations. Flagging for human review.")

        # --- MEMORY LEARNING HOOK ---
        if hasattr(self.hermes, "record_outcome"):
            final_error_category = current_audit.get("error_category", "general")
            final_fix = self._iteration_logs[shot_id][-1]["fix_applied"] if self._iteration_logs[shot_id] else ""
            self.hermes.record_outcome(
                shot_id=shot_id,
                concept=director_schema.get("concept", ""),
                kernel_id=director_schema.get("kernel_id", "unknown"),
                success=success,
                iterations_required=len(self._iteration_logs[shot_id]),
                error_category=final_error_category,
                fix_applied=final_fix,
                audit_score=current_audit.get("confidence_score", 0.0),
            )

        return {
            "success": success,
            "iterations": len(self._iteration_logs[shot_id]),
            "asset_path": asset_path,
            "needs_human_review": not success,
            "final_audit": current_audit,
        }

    async def _run_iteration(
        self,
        iteration: int,
        shot_id: str,
        audit_report: Dict[str, Any],
        director_schema: Dict[str, Any],
        lore_paths: List[str],
    ):
        remediation_prompt = audit_report.get("remediation_prompt", "")
        error_category = audit_report.get("error_category", "")
        mismatch = audit_report.get("mismatch_report", "")
        kimi_root_cause: Optional[str] = None

        if iteration == 1:
            method = "skill_registry"
            skill_key = f"{error_category.lower()}_fix"
            known_fix = (
                self.hermes.skill_registry.get_skill(skill_key)
                if self.hermes.skill_registry
                else None
            )
            fix_applied = (
                known_fix.get("fix_template", remediation_prompt)
                if known_fix
                else remediation_prompt
            )
            logger.info(f"[REMEDIATION] iter1 skill_registry fix: {fix_applied[:80]}")

        elif iteration == 2:
            method = "kimi_escalated"
            kimi_root_cause = await self._escalate_to_kimi(
                shot_id, mismatch, remediation_prompt, director_schema, lore_paths
            )
            fix_applied = kimi_root_cause or remediation_prompt
            logger.info(f"[REMEDIATION] iter2 kimi_escalated: {fix_applied[:80]}")

        else:
            method = "kimi_direct_rewrite"
            kimi_root_cause = await self._kimi_direct_rewrite(
                shot_id, mismatch, director_schema, lore_paths
            )
            fix_applied = kimi_root_cause or remediation_prompt
            logger.info(f"[REMEDIATION] iter3 kimi_direct_rewrite: {fix_applied[:80]}")

        return method, fix_applied, kimi_root_cause

    async def _escalate_to_kimi(
        self,
        shot_id: str,
        mismatch: str,
        remediation_prompt: str,
        director_schema: Dict[str, Any],
        lore_paths: List[str],
    ) -> str:
        if not self.hermes.kimi_bridge:
            return remediation_prompt
        try:
            analysis = await self.hermes.kimi_bridge.analyze_failure(
                shot_id=shot_id,
                audit_result={"failure_description": mismatch},
                original_directive={"director_schema": director_schema},
                lore_paths=lore_paths,
                schema=None,
            )
            return analysis.get("fix_prompt", remediation_prompt)
        except Exception as e:
            logger.warning(f"[REMEDIATION] Kimi escalation failed: {e}")
            return remediation_prompt

    async def _kimi_direct_rewrite(
        self,
        shot_id: str,
        mismatch: str,
        director_schema: Dict[str, Any],
        lore_paths: List[str],
    ) -> str:
        if not self.hermes.kimi_bridge:
            return mismatch
        try:
            analysis = await self.hermes.kimi_bridge.analyze_failure(
                shot_id=shot_id,
                audit_result={"failure_description": f"FINAL ATTEMPT — complete prompt rewrite needed. Issue: {mismatch}"},
                original_directive={"director_schema": director_schema},
                lore_paths=lore_paths,
                schema=None,
            )
            return analysis.get("fix_prompt", mismatch)
        except Exception as e:
            logger.warning(f"[REMEDIATION] Kimi direct rewrite failed: {e}")
            return mismatch

    def _persist_log(self, shot_id: str, iteration: int, entry: Dict) -> None:
        session_id = getattr(self.session_manager, "session_id", "default")
        log_dir = os.path.join("data", "reasoning_logs", session_id)
        os.makedirs(log_dir, exist_ok=True)
        path = os.path.join(log_dir, f"{shot_id}_iteration_{iteration}.json")
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(entry, f, indent=2)
        except OSError as e:
            logger.warning(f"[REMEDIATION] Could not persist log: {e}")

    def get_iteration_log(self, shot_id: str) -> List[Dict]:
        return self._iteration_logs.get(shot_id, [])
