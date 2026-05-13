import json

import pytest

from core.dispatch.comfy_client import ComfyUIClient


@pytest.mark.asyncio
async def test_submit_prompt_rewrites_linked_dimension_primitives(tmp_path, monkeypatch):
    workflow = {
        "prompt": {
            "10": {"class_type": "PrimitiveInt", "inputs": {}},
            "11": {"class_type": "PrimitiveInt", "inputs": {}},
            "20": {
                "class_type": "EmptyFlux2LatentImage",
                "inputs": {"width": ["10", 0], "height": ["11", 0]},
            },
            "30": {"class_type": "SaveImage", "inputs": {"images": ["20", 0]}},
        }
    }
    workflow_path = tmp_path / "linked-dimensions.json"
    workflow_path.write_text(json.dumps(workflow), encoding="utf-8")

    captured = {}

    async def fake_object_info(self):
        return {}

    async def fake_submit_prompt(self, nodes):
        captured["nodes"] = nodes
        return {"ok": True, "prompt_id": "prompt-123"}

    monkeypatch.setattr(ComfyUIClient, "_get_object_info", fake_object_info)
    monkeypatch.setattr(ComfyUIClient, "submit_prompt", fake_submit_prompt)

    result = await ComfyUIClient("http://spark.local:8188").submit_prompt_for_shot(
        prompt="test",
        workflow_path=str(workflow_path),
        wait_for_output=False,
        width=1920,
        height=1080,
    )

    assert result["status"] == "success"
    assert captured["nodes"]["10"]["inputs"]["value"] == 1920
    assert captured["nodes"]["11"]["inputs"]["value"] == 1080
