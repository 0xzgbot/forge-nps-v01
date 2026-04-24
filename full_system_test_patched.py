
import sys
import os
import asyncio
from unittest.mock import MagicMock, AsyncMock

# Force Project Root into path
PROJECT_ROOT = "~/Desktop/forge_nps_v01"
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# --- MONKEY PATCHING START ---
import core.bridge.kimi_bridge as kimi_module
class MockKimiBridge:
    def __init__(self, *args, **kwargs): pass
    async def direct(self, *args, **kwargs): return {"response": "mock"}
    async def direct_with_narrative(self, *args, **kwargs): 
        return {"status": "mocked", "reasoning_trace": "Thinking..."}
    async def analyze_failure(self, *args, **kwargs): return {}

kimi_module.KimiBridge = MockKimiBridge
# --- MONKEY PATCHING END ---

try:
    from core.bridge.config_manager import ConfigManager
    from core.state.session_manager import SessionManager
    from core.bridge.kimi_bridge import KimiBridge # This will now be our mock
    from core.orchestrator.forge_orchestrator import ForgeOrchestrator
    from core.hermes.hermes_agent import HermesAgent
    from agents.auditor.continuity_auditor import ContinuityAuditor
    from core.feedback.remediation_loop import RemediationLoop
    from core.skills.skill_registry_impl import InMemorySkillRegistry
    print("SUCCESS: All modules imported successfully with MonkeyPatch.")
except Exception as e:
    print(f"FAILURE: Import Error - {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

class MockVisualAgent:
    async def dispatch_shots(self, shot_list, directive): return []

async def run_integration_stress_test():
    print("=== STARTING FULL SYSTEM INTEGRATION STRESS TEST ===")
    
    cfg = MagicMock(spec=ConfigManager)
    
    # SCENARIO A: AUTONOMOUS SUCCESS
    print("\n--- SCENARIO A: AUTONOMOUS SUCCESS ---")
    sm_a = SessionManager("stress_test_A")
    mock_auditor_a = AsyncMock(spec=ContinuityAuditor)
    mock_skill_registry_a = InMemorySkillRegistry()
    
    # Setup a known skill for testing autonomous fix
    await mock_skill_registry_a.register_fix(
        error_category="Semantic", 
        shot_type="visual_asset", 
        original_prompt="bad lighting", 
        fix_applied="cinematic moody lighting, high contrast", 
        success=True, 
        kimi_reasoning="The model defaults to flat light in dark scenes."
    )

    # Note: KimiBridge is now the MockKimiBridge from our patch
    kimi = KimiBridge() 
    hermes_a = HermesAgent(
        visual_agent=MockVisualAgent(), 
        skill_registry=mock_skill_registry_a,
        kimi_bridge=kimi,
        session_manager=sm_a
    )
    
    remediation_a = RemediationLoop(hermes_a, mock_auditor_a, sm_a)
    orch_a = ForgeOrchestrator(cfg, "stress_test_A")
    # Inject our prepared components
    orch_a.hermes_agent = hermes_a 
    orch_a.auditor = mock_auditor_a
    orch_a.remediation_loop = remediation_a

    mock_auditor_a.audit_asset.side_effect = [
        {
            "is_consistent": False, 
            "error_category": "Semantic", 
            "mismatch_report": "lighting is bad", 
            "remediation_prompt": "fix lighting"
        },
        {
            "is_consistent": True, 
            "confidence_score": 0.99
        }
    ]
    
    hermes_a.dispatch_shots = AsyncMock(return_value=[
        {"shot_id": "SHOT_AUTO", "description": "bad lighting", "asset_path": None}
    ])

    await orch_a.run("scripts/demo/pilot_script.md", ["data/lore_bible/world_bible.md"])
    
    summary_a = sm_a.get_session_summary()
    if summary_a["shots"]["SHOT_AUTO"]["status"] == "complete":
        print("SUCCESS: Scenario A completed autonomously.")
    else:
        print(f"FAILURE: Scenario A failed with status {summary_a['shots']['SHOT_AUTO']['status']}")

    # SCENARIO B: KIMI ESCALATION
    print("\n--- SCENARIO B: KIMI ESCALATION ---")
    sm_b = SessionManager("stress_test_B")
    mock_auditor_b = AsyncMock(spec=ContinuityAuditor)
    mock_skill_registry_b = InMemorySkillRegistry()

    # Mocking Kimi's behavior for the escalation
    kimi.analyze_failure = AsyncMock(return_value={
        "success": True,
        "iterations": 2,
        "root_cause": "color drift error",
        "fix_applied": "cinematic color grading, high contrast",
        "corrected_directive": {"prompt": "cinematic color grading"},
        "iteration_logs": []
    })

    hermes_b = HermesAgent(
        visual_agent=MockVisualAgent(), 
        skill_registry=mock_skill_registry_b,
        kimi_bridge=kimi,
        session_manager=sm_b
    )
    
    remediation_b = RemediationLoop(hermes_b, mock_auditor_b, sm_b)
    orch_b = ForgeOrchestrator(cfg, "stress_test_B")
    orch_b.hermes_agent = hermes_b 
    orch_b.auditor = mock_auditor_b
    orch_b.remediation_loop = remediation_b

    mock_auditor_b.audit_asset.side_effect = [
        {
            "is_consistent": False, 
            "error_category": "Photometric", 
            "mismatch_report": "color drift error", 
            "remediation_prompt": "fix color"
        },
        {
            "is_consistent": True, 
            "confidence_score": 0.95
        }
    ]
    
    hermes_b.dispatch_shots = AsyncMock(return_value=[
        {"shot_id": "SHOT_KIMI", "description": "color drift error", "asset_path": None}
    ])

    await orch_b.run("scripts/demo/pilot_script.md", ["data/lore_bible/world_bible.md"])
    
    summary_b = sm_b.get_session_summary()
    if summary_b["shots"]["SHOT_KIMI"]["status"] == "complete":
        print("SUCCESS: Scenario B completed via Kimi escalation.")
    else:
        print(f"FAILURE: Scenario B failed with status {summary_b['shots']['SHOT_KIMI']['status']}")

if __name__ == "__main__":
    asyncio.run(run_integration_stress_test())
