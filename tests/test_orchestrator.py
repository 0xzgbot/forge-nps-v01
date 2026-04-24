import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio

# Import the class to test
# Since we are in a script context, we need to ensure paths are correct
import sys
import os
sys.path.append("/Users/zgbot/Desktop/forge_nps_v01")

from core.orchestrator.forge_orchestrator import ForgeOrchestrator

class TestForgeOrchestrator(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        # Mock dependencies
        self.mock_config = MagicMock()
        self.mock_session_manager = MagicMock()
        self.mock_kimi_bridge = AsyncMock()
        self.mock_hermes_agent = AsyncMock()
        # record_outcome is a sync method on HermesAgent; prevent AsyncMock from making it a coroutine
        self.mock_hermes_agent.record_outcome = MagicMock()
        self.mock_auditor = AsyncMock()
        self.mock_remediation_loop = AsyncMock()

        # Setup session manager mock behavior
        self.mock_session_manager.session_id = "test_session_123"
        self.mock_session_manager.get_session_summary.return_value = {
            "session_id": "test_session_123",
            "total_shots": 2,
            "completed_shots": 2,
            "autonomy_score": 0.8,
            "total_fixes": 1
        }

        # Set up ConfigManager mock for the schema
        self.mock_config.get.return_value = MagicMock()

        # Instantiate orchestrator with mocks
        self.orchestrator = ForgeOrchestrator(
            config_manager=self.mock_config,
            session_manager=self.mock_session_manager,
            kimi_bridge=self.mock_kimi_bridge,
            hermes_agent=self.mock_hermes_agent,
            continuity_auditor=self.mock_auditor,
            remediation_loop=self.mock_remediation_loop
        )

    async def test_run_success_path(self):
        """
        Scenario: 2 shots. 
        Shot 1: Passes audit immediately.
        Shot 2: Fails once, passes on remediation.
        Verify session manager updates and summary return.
        """
        # 1. Mock Narrative Analysis (Kimi)
        director_schema = MagicMock()
        self.mock_kimi_bridge.direct_with_narrative.return_value = {
            "shots": [
                {"shot_id": "shot_001", "description": "A peaceful forest"},
                {"shot_id": "shot_002", "description": "A man with wrong color eyes"} # Will trigger audit failure
            ]
        }

        # 2. Mock Shot Dispatching (Hermes)
        self.mock_hermes_agent.dispatch_shots.return_value = [
            {"shot_id": "shot_001", "description": "A peaceful forest", "asset_path": "/assets/s1.png"},
            {"shot_id": "shot_002", "description": "A man with wrong color eyes", "asset_path": "/assets/s2.png"}
        ]

        # 3. Mock Auditor
        # Shot 1: Success
        # Shot 2: Failure
        self.mock_auditor.audit_asset.side_effect = [
            {"is_consistent": True, "consistency_score": 95, "reasoning_trace": ["Looks good"]},
            {"is_consistent": False, "consistency_score": 40, "reasoning_trace": ["Wrong color"]}
        ]

        # 4. Mock Remediation Loop
        self.mock_remediation_loop.remediate.return_value = {
            "success": True,
            "iterations": 1,
            "asset_path": "/assets/s2_fixed.png"
        }

        # EXECUTE
        result = await self.orchestrator.run(
            script_path="dummy_script.md",
            lore_paths=["dummy_lore.md"]
        )

        # VERIFY
        # Check session initialization
        self.mock_session_manager.create_session.assert_called_with("dummy_script.md", ["dummy_lore.md"])

        # Check shot 1 status (Immediate success)
        self.mock_session_manager.update_shot_status.assert_any_call(
            shot_id="shot_001",
            status="complete",
            data={"asset_path": "/assets/s1.png", "audit_history": [{"is_consistent": True, "consistency_score": 95, "reasoning_trace": ["Looks good"]}]}
        )

        # Check shot 2 status (After remediation)
        self.mock_session_manager.update_shot_status.assert_any_call(
            shot_id="shot_002",
            status="complete",
            data={"iterations": 1, "final_asset": "/assets/s2_fixed.png", "audit_history": [{"is_consistent": False, "consistency_score": 40, "reasoning_trace": ["Wrong color"]}]}
        )

        # Verify summary structure
        self.assertEqual(result["session_id"], "test_session_123")
        self.assertEqual(result["total_shots"], 2)
        self.assertEqual(result["completed_shots"], 2)

    async def test_run_shot_failure_doesnt_crash_pipeline(self):
        """Ensure a single shot failure doesn't halt the entire process."""
        self.mock_kimi_bridge.direct_with_narrative.return_value = {
            "shots": [{"shot_id": "fail_shot", "description": "error"}]
        }
        self.mock_hermes_agent.dispatch_shots.return_value = [
            {"shot_id": "fail_shot", "description": "error"}
        ]
        # Simulate a crash in auditor
        self.mock_auditor.audit_asset.side_effect = Exception("Auditor Exploded")

        # EXECUTE
        await self.orchestrator.run("script.md", [])

        # VERIFY
        self.mock_session_manager.update_shot_status.assert_called_with(shot_id="fail_shot", status="failed")

if __name__ == "__main__":
    unittest.main()
