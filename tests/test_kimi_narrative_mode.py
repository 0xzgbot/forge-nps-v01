import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import os
import json
import asyncio
from pydantic import BaseModel
from core.bridge.kimi_bridge import KimiBridge

class DirectorSchemaV2(BaseModel):
    narrative_reasoning_trace: str
    shots: list[dict]

class TestKimiNarrativeMode(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from unittest.mock import MagicMock
        self.endpoint = "http://localhost:8080/v1/chat/completions"
        self.api_key = "test-key"
        mock_config = MagicMock()
        self.bridge = KimiBridge(self.endpoint, self.api_key, mock_config)
        
        # Create dummy files for testing
        self.script_path = "/tmp/test_script.md"
        with open(self.script_path, "w", encoding="utf-8") as f:
            f.write("# SCRIPT: Test Pilot\n## SCENE 1: The Awakening\n**Characters:** Elara Vance\n**Visuals:** A dark room.\n**Action:** She wakes up.")
        
        self.lore_path = "/tmp/test_lore.md"
        with open(self.lore_path, "w", encoding="utf-8") as f:
            f.write("WORLD BIBLE: The planet is called Xylos.")
            
        self.session_id = "test_session_123"

    async def asyncTearDown(self):
        if os.path.exists(self.script_path):
            os.remove(self.script_path)
        if os.path.exists(self.lore_path):
            os.remove(self.lore_path)
        # Clean up reasoning logs if created
        log_dir = f"/Users/zgbot/Desktop/forge_nps_v01/data/reasoning_logs/{self.session_id}"
        if os.path.exists(log_dir):
            import shutil
            shutil.rmtree(log_dir)

    @patch("core.bridge.kimi_bridge.httpx.AsyncClient.post")
    async def test_direct_with_narrative_flow(self, mock_post):
        # Mock Kimi's response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_content = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "narrative_reasoning_trace": "This is a reasoning trace.",
                        "shots": [{"id": "shot_1", "directive": "do something"}]
                    })
                }
            }]
        }
        mock_response.json.return_value = mock_content
        mock_post.return_value = mock_response

        # Mock SkillRegistry
        mock_registry = MagicMock()
        mock_registry.data = {"fixes": {"Test:Shot": {"prompt_modifier": "fix", "kimi_reasoning": "why"}}}

        # Execute
        result = await self.bridge.direct_with_narrative(
            script_path=self.script_path,
            lore_paths=[self.lore_path],
            session_id=self.session_id,
            schema=DirectorSchemaV2,
            skill_registry=mock_registry
        )

        # Verify results
        self.assertEqual(result["narrative_reasoning_trace"], "This is a reasoning trace.")
        self.assertTrue(len(result["shots"]) > 0)

        # Verify Reasoning Log creation
        expected_log = f"/Users/zgbot/Desktop/forge_nps_v01/data/reasoning_logs/{self.session_id}/full_analysis_reasoning.md"
        self.assertTrue(os.path.exists(expected_log))
        with open(expected_log, "r", encoding="utf-8") as f:
            content = f.read()
            self.assertIn("This is a reasoning trace.", content)

    @patch("core.bridge.kimi_bridge.httpx.AsyncClient.post")
    async def test_mega_prompt_structure(self, mock_post):
        # We want to check if the prompt contains all sections in order.
        # Since we can't easily see what was sent unless we intercept the payload in mock_post
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_content = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "narrative_reasoning_trace": "Trace",
                        "shots": []
                    })
                }
            }]
        }
        mock_response.json.return_value = mock_content
        mock_post.return_value = mock_response

        # Setup capture
        captured_payload = {}

        async def side_effect(*args, **kwargs):
            nonlocal captured_payload
            captured_payload = kwargs['json']
            return mock_response

        mock_post.side_effect = side_effect

        await self.bridge.direct_with_narrative(
            script_path=self.script_path,
            lore_paths=[self.lore_path],
            session_id=self.session_id,
            schema=DirectorSchemaV2
        )

        user_content = captured_payload["messages"][1]["content"]
        
        # Check order: [WORLD BIBLE] -> [CHARACTER REGISTRY] -> [FULL SCRIPT] -> [DIRECTOR TASK (v2)]
        idx_bible = user_content.find("[WORLD BIBLE]")
        idx_char = user_content.find("[CHARACTER REGISTRY]")
        idx_script = user_content.find("[FULL SCRIPT]")
        idx_task = user_content.find("[DIRECTOR TASK (v2)]")

        self.assertTrue(idx_bible != -1 and idx_char != -1 and idx_script != -1 and idx_task != -1)
        self.assertTrue(idx_bible < idx_char < idx_script < idx_task)

if __name__ == "__main__":
    unittest.main()
