import asyncio
import json
import sys
import os

sys.path.append("/Users/zgbot/Desktop/forge_nps_v01")
from agents.visual.visual_agent import VisualAgent

async def run_test():
    agent = VisualAgent("http://localhost:8188")
    mock_shot = {
        "shot_id": "SHOT_001",
        "visual_prompt": {
            "subject": "Elara Vance, walking through neon rain",
            "environment": "Cyberpunk alleyway",
            "camera": {"movement": "dolly"},
            "lens_specs": {"focal_length": "35mm"}
        }
    }
    # Use a dummy workflow structure for testing injection logic
    dummy_wf = {
        "prompt": {
            "6": {"class_type": "CLIPTextEncode", "inputs": {"text": ""}}
        }
    }
    print("Testing Injection...")
    # Since we aren't running a real server, we check the internal logic manually
    p = agent._map_to_prompt(mock_shot)
    print(f"Generated Prompt: {p}")
    if "Elara Vance" in p: print("✅ PROMPT OK")
    else: print("❌ PROMPT FAIL")

if __name__ == "__main__":
    asyncio.run(run_test())
