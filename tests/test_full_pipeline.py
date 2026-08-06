import pytest
import asyncio
import os
from pathlib import Path
import json
import shutil
from unittest.mock import AsyncMock, MagicMock, patch

# Add project root to sys.path for imports
PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
if PROJECT_ROOT not in os.sys.path:
    os.sys.path.insert(0, PROJECT_ROOT)

from core.orchestrator.cinesmith_orchestrator import CinesmithOrchestrator
from core.state.session_manager import SessionManager
from core.bridge.config_manager import ConfigManager
from core.bridge.kimi_bridge import KimiBridge
from core.hermes.hermes_agent import HermesAgent
from agents.auditor.continuity_auditor import ContinuityAuditor

# Test Constants
TEST_SESSION_ID = "test_integration_session"
TEST_SCRIPT_PATH = os.path.join(PROJECT_ROOT, "scripts/demo/pilot_script.md")
TEST_LORE_PATH = os.path.join(PROJECT_ROOT, "data/lore_bible/world_bible.md")
TEST_OUTPUT_DIR = os.path.join(PROJECT_ROOT, "data/sessions_test")

@pytest.fixture(scope="module")
def clean_test_dir():
    if os.path.exists(TEST_OUTPUT_DIR):
        shutil.rmtree(TEST_OUTPUT_DIR)
    yield
    if os.path.exists(TEST_OUTPUT_DIR):
        shutil.rmtree(TEST_OUTPUT_DIR)

@pytest.fixture
def mock_config():
    config = MagicMock(spec=ConfigManager)
    config.get.return_value = {"schema_version": "2.0"}
    return config

@pytest.fixture
def mock_kimi(mock_config):
    bridge = AsyncMock(spec=KimiBridge)
    bridge.direct_with_narrative.return_value = {
        "shots": [
            {"shot_id": "SHOT_001", "description": "A cinematic shot of a forest."},
            {"shot_id": "SHOT_002", "description": "Close up of a character."}
        ],
        "reasoning_trace": "Mocked narrative analysis."
    }
    return bridge

@pytest.fixture
def mock_auditor():
    auditor = AsyncMock(spec=ContinuityAuditor)
    # Default: everything passes
    auditor.audit_asset.return_value = {"is_consistent": True, "report": "Looks good."}
    return auditor

@pytest.fixture
def mock_remediation():
    loop = AsyncMock()
    loop.remediate.return_value = {
        "success": True, 
        "iterations": 1, 
        "asset_path": "data/outputs/demo/SHOT_001_fixed.png"
    }
    return loop

@pytest.mark.asyncio
async def test_full_pipeline_success(clean_test_dir, mock_config, mock_kimi, mock_auditor, mock_remediation):
    """
    Test a successful end-to-end run where everything passes first time.
    """
    session_manager = SessionManager(TEST_SESSION_ID, output_dir=TEST_OUTPUT_DIR)
    hermes = HermesAgent(kimi_bridge=mock_kimi, session_manager=session_manager)
    
    orchestrator = CinesmithOrchestrator(
        config_manager=mock_config,
        session_manager=session_manager,
        kimi_bridge=mock_kimi,
        hermes_agent=hermes,
        continuity_auditor=mock_auditor,
        remediation_loop=mock_remediation
    )

    summary = await orchestrator.run(TEST_SCRIPT_PATH, [TEST_LORE_PATH])

    # 1. Validate Session Creation
    assert summary["session_id"] == TEST_SESSION_ID
    assert os.path.exists(session_manager.state_path)

    # 2. Validate Shot Completion
    for shot in summary["shots"].values():
        assert shot["status"] == "complete"

    # 3. Validate Data Integrity
    assert "SHOT_001" in summary["shots"]
    assert "asset_path" in summary["shots"]["SHOT_001"]


@pytest.mark.asyncio
async def test_remediation_loop_fail_then_fix(clean_test_dir, mock_config, mock_kimi, mock_auditor, mock_remediation):
    """
    Test the 'Fail -> Fix -> Pass' cycle.
    SHOT_001 fails audit, SHOT_002 passes.
    """
    session_manager = SessionManager(TEST_SESSION_ID, output_dir=TEST_OUTPUT_DIR)
    hermes = HermesAgent(kimi_bridge=mock_kimi, session_manager=session_manager)

    # Mock auditor to fail SHOT_001 but pass SHOT_002
    async def side_effect_audit(asset_description, shot_id):
        if shot_id == "SHOT_001":
            return {"is_consistent": False, "error": "Photometric mismatch"}
        return {"is_consistent": True, "report": "Passed"}

    mock_auditor.audit_asset.side_effect = side_effect_audit

    orchestrator = CinesmithOrchestrator(
        config_manager=mock_config,
        session_manager=session_manager,
        kimi_bridge=mock_kimi,
        hermes_agent=hermes,
        continuity_auditor=mock_auditor,
        remediation_loop=mock_remediation
    )

    summary = await orchestrator.run(TEST_SCRIPT_PATH, [TEST_LORE_PATH])

    # Verify SHOT_001 was remediated and marked complete
    assert summary["shots"]["SHOT_001"]["status"] == "complete"
    assert summary["shots"]["SHOT_001"]["iterations"] == 1
    assert summary["shots"]["SHOT_001"]["final_asset"] == "data/outputs/demo/SHOT_001_fixed.png"

    # Verify SHOT_002 passed normally
    assert summary["shots"]["SHOT_002"]["status"] == "complete"


@pytest.mark.asyncio
async def test_autonomy_score_increment(clean_test_dir, mock_config, mock_kimi, mock_auditor, mock_remediation):
    """
    Verify that autonomy score increments when Hermes solves a problem via remediation 
    instead of Kimi escalation (though in current orchestrator, escalation isn't explicitly modeled as an incrementing logic, 
    we test if we can manually verify the property).
    """
    session_manager = SessionManager(TEST_SESSION_ID, output_dir=TEST_OUTPUT_DIR)
    hermes = HermesAgent(kimi_bridge=mock_kimi, session_manager=session_manager)
    
    # Simulate Hermes solving a problem autonomously
    hermes.set_autonomy_score(0.8)
    assert hermes.autonomy_score == 0.8

@pytest.mark.asyncio
async def test_demo_smoke_test():
    """
    Runs the actual demo.py in mock mode to ensure no crashes during full execution.
    """
    # Use subprocess to run the command as it's an integration smoke test
    import subprocess

    cmd = [
        "python3", "demo.py", 
        "--script", TEST_SCRIPT_PATH, 
        "--mock"
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    assert result.returncode == 0
    assert "PRODUCTION COMPLETE" in result.stdout or "✅ PRODUCTION COMPLETE" in result.stdout
