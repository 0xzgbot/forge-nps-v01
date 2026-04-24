import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pydantic import BaseModel, Field
import json
import sys
import os

# Add the project root to sys.path so we can import modules correctly
sys.path.append("/Users/zgbot/Desktop/forge_nps_v01")

from core.bridge.kimi_bridge import KimiBridge, StrictSchemaGuard

class DummySchema(BaseModel):
    name: str
    age: int
    tags: list[str] = Field(default_factory=list)

class NarrativeSchema(BaseModel):
    reasoning_trace: str
    status: str

class FailureSchema(BaseModel):
    root_cause: str
    fix_type: str
    corrected_directive: dict
    skill_update: dict

@pytest.mark.asyncio
async def test_direct_with_narrative_success():
    # Mock files
    script_path = "/tmp/script.txt"
    lore_path = "/tmp/lore.txt"
    session_id = "test_session_123"
    
    with open(script_path, 'w', encoding="utf-8") as f: f.write("Scene 1: Elara enters.")
    with open(lore_path, 'w', encoding="utf-8") as f: f.write("Elara is a warrior.")

    mock_response_content = json.dumps({
        "reasoning_trace": "I analyzed the script and lore.",
        "status": "complete"
    })
    mock_response_data = {
        "choices": [{"message": {"content": mock_response_content}}]
    }

    mock_config = MagicMock()
    bridge = KimiBridge(endpoint_url="http://fake-api.com", api_key="fake-key", config_manager=mock_config)

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        result = await bridge.direct_with_narrative(
            script_path=script_path,
            lore_paths=[lore_path],
            session_id=session_id,
            schema=NarrativeSchema
        )

        assert result["status"] == "complete"
        assert result["reasoning_trace"] == "I analyzed the script and lore."
        
        # Verify log file creation
        log_path = f"/Users/zgbot/Desktop/forge_nps_v01/data/reasoning_logs/{session_id}/full_analysis_reasoning.md"
        assert os.path.exists(log_path)
        with open(log_path, 'r', encoding="utf-8") as f:
            content = f.read()
            assert "I analyzed the script and lore." in content

    # Cleanup
    os.remove(script_path)
    os.remove(lore_path)

@pytest.mark.asyncio
async def test_analyze_failure_success():
    lore_path = "/tmp/lore_fail.txt"
    with open(lore_path, 'w', encoding="utf-8") as f: f.write("Lore content.")

    mock_response_content = json.dumps({
        "root_cause": "Lighting mismatch",
        "fix_type": "prompt_adjustment",
        "corrected_directive": {"lighting": "warm"},
        "skill_update": {"model": "flux-v2"}
    })
    mock_response_data = {
        "choices": [{"message": {"content": mock_response_content}}]
    }

    mock_config = MagicMock()
    bridge = KimiBridge(endpoint_url="http://fake-api.com", api_key="fake-key", config_manager=mock_config)

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        result = await bridge.analyze_failure(
            shot_id="shot_001",
            audit_result={"error": "too dark"},
            original_directive={"lighting": "bright"},
            lore_paths=[lore_path],
            schema=FailureSchema
        )

        assert result["root_cause"] == "Lighting mismatch"
        assert result["fix_type"] == "prompt_adjustment"
        assert result["corrected_directive"]["lighting"] == "warm"

    os.remove(lore_path)

if __name__ == "__main__":
    pytest.main([__file__])
