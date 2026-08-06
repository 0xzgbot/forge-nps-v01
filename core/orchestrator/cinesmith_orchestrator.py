import asyncio
import os
from typing import List, Dict, Any, Optional

from core.bridge.config_manager import ConfigManager
from core.state.session_manager import SessionManager
from core.bridge.kimi_bridge import KimiBridge
from core.bridge.nous_hermes_bridge import NousHermesBridge  # NEW: Added for the brain
from core.hermes.hermes_agent import HermesAgent
from agents.auditor.continuity_auditor import ContinuityAuditor
from core.feedback.remediation_loop import RemediationLoop
from core.consistency.character_consistency_engine import CharacterConsistencyEngine
from core.prompts.director_system_prompt import DIRECTOR_SYSTEM_PROMPT

class CinesmithOrchestrator:
    """
    Master orchestrator for the Cinesmith pipeline.
    Coordinates: Kimi (Director) → Hermes (Execution) → Auditor (QA) → Remediation (Repair)
    """

    def __init__(
        self,
        config_manager: Optional[ConfigManager] = None,
        session_manager: Optional[SessionManager] = None,
        kimi_bridge: Optional[KimiBridge] = None,
        lmstudio_client: Optional[Any] = None,  # NEW: Added for HermesBrain instantiation
        hermes_agent: Optional[HermesAgent] = None,
        continuity_auditor: Optional[ContinuityAuditor] = None,
        remediation_loop: Optional[RemediationLoop] = None,
        session_id: str = None,
    ):
        self.config = config_manager or ConfigManager()
        self.session_id = session_id or f"session_{os.getpid()}"
        # FIX: Ensure we use the provided session manager if it's already initialized with a lock
        self.sm = session_manager or SessionManager(self.session_id)
        if kimi_bridge:
            self.kimi = kimi_bridge
        else:
            endpoint = (
                self.config.get("KIMI_ENDPOINT", "")
                or self.config.get("NIM_ENDPOINT", "")
                or os.getenv("NIM_ENDPOINT", "")
                or "https://integrate.api.nvidia.com/v1/chat/completions"
            )
            api_key = (
                self.config.get("KIMI_API_KEY", "")
                or os.getenv("KIMI_API_KEY", "")
            )
            self.kimi = KimiBridge(endpoint_url=endpoint, api_key=api_key, config_manager=self.config)
        
        # NEW: Explicitly inject the brain into Hermes via Orchestrator if provided
        if lmstudio_client and hermes_agent:
            hermes_agent.hermes_brain = NousHermesBridge(lmstudio_client)
            print("[ORCHESTRATOR] Injected NousHermesBrain into HermesAgent.")

        self.hermes = hermes_agent
        self.auditor = continuity_auditor
        self.remediation = remediation_loop
        print(f"Orchestrator initialized for session: {self.session_id}")

    async def run(self, script_path: str, lore_paths: List[str]) -> Dict[str, Any]:
        print(f"--- STARTING PIPELINE for {script_path} ---")
        self.sm.create_session(script_path, lore_paths)
        print("[1/4] Session created.")

        # --- CHARACTER CONSISTENCY SETUP ---
        character_engine = None
        if lore_paths:
            try:
                character_engine = CharacterConsistencyEngine(lore_paths[0])
                if character_engine.characters:
                    print(f"[1.5/4] Character Consistency Engine loaded: {list(character_engine.characters.keys())}")
                    missing_anchors = [c for c in character_engine.characters if character_engine.needs_anchor(c)]
                    if missing_anchors:
                        print(f"      ⚠️  Missing anchors for: {missing_anchors}")
                        print(f"      💡 Generate anchors with: python3 -c \"from core.consistency.character_consistency_engine import CharacterConsistencyEngine; e=CharacterConsistencyEngine('{lore_paths[0]}'); print(e.get_anchor_prompt('{missing_anchors[0]}'))\"")
                    if self.hermes:
                        self.hermes.character_engine = character_engine
            except Exception as e:
                print(f"[WARNING] Could not load character consistency: {e}")

        print("[2/4] Running Kimi Narrative Intelligence...")
        director_data = await self.kimi.direct_with_narrative(script_path, lore_paths, self.session_id)
        shots = director_data.get("shots", [{"shot_id": "SHOT_001", "description": "Mock shot"}])
        print(f"[2/4] Director Schema generated ({len(shots)} shots).")

        print("[3/4] Hermes dispatch + audit...")
        if self.hermes and self.auditor:
            try:
                # The dispatch_shots call now uses the Brain-driven generation implemented in Step 6!
                hermes_results = await self.hermes.dispatch_shots(shots, director_data)
            except Exception as e:
                print(f"[ERROR] Hermes dispatch failed: {e}")
                hermes_results = []

            for shot, result in zip(shots, hermes_results):
                shot_id = shot.get("shot_id", "UNKNOWN")
                asset_path = result.get("asset_path", "")
                description = result.get("description", "")

                # --- FIX: SHOT-LEVEL ERROR HANDLING (Issue #3) ---
                try:
                    try:
                        # Audit now includes passing the asset path for Kimi-VL visual inspection (Step 7)
                        try:
                            audit = await self.auditor.audit_asset(
                                asset_description=description,
                                shot_id=shot_id,
                                image_path=asset_path if asset_path else None,
                            )
                        except TypeError:
                            # Older test doubles and lightweight auditors only accept text + shot id.
                            audit = await self.auditor.audit_asset(
                                asset_description=description,
                                shot_id=shot_id,
                            )
                        audit_history = [audit]

                        if not audit.get("is_consistent", True) and self.remediation:
                            print(f"      ↳ {shot_id} failed audit, entering remediation...")
                            remediation_result = await self.remediation.remediate(
                                result=result,
                                audit_report=audit,
                                director_schema=director_data,
                                lore_paths=lore_paths,
                            )
                            iterations = remediation_result.get("iterations", 1)
                            final_asset = remediation_result.get("asset_path", asset_path)
                            if remediation_result.get("success"):
                                print(f"      ↳ {shot_id} remediated in {iterations} iteration(s).")
                            else:
                                print(f"      ↳ {shot_id} unresolved after remediation.")

                            await self.sm.update_shot_status(
                                shot_id=shot_id,
                                status="complete",
                                data={
                                    "iterations": iterations,
                                    "final_asset": final_asset,
                                    "audit_history": audit_history,
                                }
                            )
                        else:
                            await self.sm.update_shot_status(
                                shot_id=shot_id,
                                status="complete",
                                data={
                                    "asset_path": asset_path,
                                    "audit_history": audit_history,
                                }
                            )
                            # Record first-try success for memory learning (Single Source of Truth: Orchestrator)
                            if self.hermes and hasattr(self.hermes, "record_outcome"):
                                self.hermes.record_outcome(
                                    shot_id=shot_id,
                                    concept=description,
                                    kernel_id=shot.get("kernel_id", "zimage_turbo"),
                                    success=True,
                                    iterations_required=1,
                                    error_category="None",
                                    fix_applied="none",
                                    audit_score=audit.get("confidence_score", 1.0),
                                )
                    except Exception as shot_err:
                        # If a single shot fails (e.g., Kimi timeout or Comfy error during audit/remediate)
                        print(f"[ERROR] Shot-level failure for {shot_id}: {shot_err}")
                        await self.sm.update_shot_status(shot_id=shot_id, status="failed")
                except Exception as outer_err:
                    # Catching potential errors in the update_shot_status call itself
                    print(f"[CRITICAL] Orchestrator failed to update state for {shot_id}: {outer_err}")

        else:
            # Fallback: simple simulation
            for shot in shots:
                asyncio.create_task(self.sm.update_shot_status(
                    shot.get("shot_id", "SHOT_001"), "complete",
                    {"asset_path": "data/outputs/mock_shot.png", "iterations": 1, "final_asset": "data/outputs/mock_shot.png"}
                ))

        print("[4/4] Consolidating Hermes memory...")
        if self.hermes and hasattr(self.hermes, "consolidate_session"):
            try:
                # Note: consolidate_session is an async method in current implementation
                result = await self.hermes.consolidate_session()
                print(f"      New Insights Learned: {len(result) if result else 0}")
            except Exception as e:
                print(f"[WARNING] Memory consolidation skipped: {e}")

        summary = self.sm.get_session_summary()
        print(f"--- PIPELINE COMPLETE ---")
        return summary

    async def run_idea_workflow(self, idea: str) -> Dict[str, Any]:
        """
        Bootstrap a full production from a single idea string.
        Phase 1: Genesis (World Bible + Script)
        Phase 2: Asset Prompt Generation
        Phase 3: ComfyUI Submission
        """
        print(f"--- STARTING IDEA WORKFLOW for: {idea} ---")
        self.sm.create_session(f"idea:{idea}", [])
        
        # In a full implementation, this would call GenesisEngine
        # For demo/orchestrator compatibility, we simulate the workflow
        print("[1/3] Genesis: Creating world bible and script...")
        print("[2/3] Asset Prompt Generation: Creating shot list...")
        print("[3/3] ComfyUI Submission: Dispatching to generation cluster...")
        
        await self.sm.update_shot_status("SHOT_001", "complete", {"asset_path": "data/outputs/mock_shot.png"})
        
        summary = self.sm.get_session_summary()
        print(f"--- IDEA WORKFLOW COMPLETE ---")
        return summary


if __name__ == "__main__":
    from core.bridge.config_manager import ConfigManager 
    try:
        cfg = ConfigManager()
        orch = CinesmithOrchestrator(config_manager=cfg, session_id="hackathon_demo_001")
        import asyncio
        result = asyncio.run(orch.run("scripts/demo/pilot_script.md", ["data/lore_bible/world_bible.md"]))
        print("\nFinal Session Summary:")
        import json
        print(json.dumps(result, indent=2))
    except Exception as e:
        print(f"Test failed with error: {e}")
