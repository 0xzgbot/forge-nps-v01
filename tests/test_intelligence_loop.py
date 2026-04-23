import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from core.orchestrator.forge_orchestrator import ForgeOrchestrator

@pytest.mark.asyncio
async def test_intelligence_loop_remediation_success():
    # 1. Setup Mocks
    mock_config = MagicMock()
    mock_config.get.side_effect = lambda k, default=None: {
        "COSMOS_ENDPOINT": "http://mock-cosmos",
        "COSMOS_API_KEY": "mock-key",
        "DIRECTOR_SCHEMA": {"type": "object"}
    }.get(k, default)

    mock_session = MagicMock()
    mock_session.session_id = "test_session"

    mock_kimi = AsyncMock()
    # Mock Kimi Bridge for director result
    mock_kimi.direct_with_narrative.return_value = {
        "shots": [
            {"shot_id": "shot_001", "description": "A person floating upwards unexpectedly."}
        ]
    }

    mock_hermes = MagicMock()
    mock_hermes.dispatch_shots = AsyncMock(side_effect=[
        # Initial generation result
        [{"shot_id": "shot_001", "description": "A person floating upwards unexpectedly.", "asset_path": "/tmp/fail.png"}],
        # Remediation generation result (the loop calls dispatch_shots again if it were to re-run,
        # but here the orchestrator uses remediation_loop which might or might not call hermes)
    ])

    mock_hermes.skill_registry = MagicMock()

    mock_auditor = AsyncMock()
    # First call fails to trigger remediation, subsequent calls pass
    mock_auditor.audit_asset.side_effect = [
        {"is_consistent": False, "error_category": "Physics", "mismatch_report": "Gravity is inverted.", "confidence_score": 0.3, "remediation_prompt": "A character walking normally on a floor with standard gravity."},
        {"is_consistent": True, "confidence_score": 1.0},
    ]

    mock_remediation = AsyncMock()
    mock_remediation.remediate.return_value = {
        "success": True,
        "iterations": 1,
        "asset_path": "/tmp/success.png",
        "final_prompt": "A person walking on the ground."
    }

    orchestrator = ForgeOrchestrator(
        config_manager=mock_config,
        session_manager=mock_session,
        kimi_bridge=mock_kimi,
        hermes_agent=mock_hermes,
        continuity_auditor=mock_auditor,
        remediation_loop=mock_remediation
    )

    # 2. Execute Workflow
    lore_paths = ["/tmp/lore.md"]

    # We trigger the logic inside 'run'
    await orchestrator.run("fake_script.md", lore_paths)

    # 3. Assertions
    # Check if remediation was called
    mock_remediation.remediate.assert_called()

if __name__ == "__main__":
    pytest.main([__file__])
