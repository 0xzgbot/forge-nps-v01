import json
from pathlib import Path

import pytest

from core.affiliate.local_spark_media import LocalSparkMediaAdapter


class FakeComfy:
    def __init__(self, base_url):
        self.base_url = base_url

    async def submit_prompt_for_shot(self, **kwargs):
        return {
            "status": "success",
            "prompt_id": "prompt_fake_123",
            "seed": kwargs.get("seed") or 123,
            "queued": True,
            "uploaded_image": None,
        }


def _adapter(tmp_path, monkeypatch):
    monkeypatch.setattr("core.affiliate.local_spark_media.ComfyUIClient", FakeComfy)
    workflow = tmp_path / "workflow.json"
    workflow.write_text("{}", encoding="utf-8")
    return LocalSparkMediaAdapter(
        repo_root=tmp_path,
        media_root=tmp_path / "media",
        media_images=tmp_path / "media" / "images",
        comfy_url="http://localhost:8188",
        workflow_file_for_id=lambda workflow_id: workflow,
        resolve_image_path=lambda value: Path(value) if Path(value).exists() else None,
    )


@pytest.mark.asyncio
async def test_generate_image_returns_spark_media_shaped_job_set(tmp_path, monkeypatch):
    adapter = _adapter(tmp_path, monkeypatch)

    job = await adapter.generate_image(
        prompt="A clean product hero shot",
        style_id="forge-commercial-product",
        seed=42,
    )

    assert job["type"] == "text2image_local"
    assert job["status"] == "queued"
    assert job["jobs"][0]["prompt_id"] == "prompt_fake_123"
    assert job["input_params"]["style_id"] == "forge-commercial-product"
    assert Path(job["local_output_dir"]).exists()
    assert (tmp_path / "media" / "local_spark_media" / "jobs" / f"{job['id']}.json").exists()


@pytest.mark.asyncio
async def test_create_character_stores_local_reference(tmp_path, monkeypatch):
    adapter = _adapter(tmp_path, monkeypatch)
    source = tmp_path / "face.png"
    source.write_bytes(b"fake-image")

    character = await adapter.create_character(name="Creator Face", image_urls=[str(source)])
    loaded = adapter.get_character(character["id"])
    listed = adapter.list_characters()

    assert character["status"] == "completed"
    assert loaded["id"] == character["id"]
    assert listed["total"] == 1
    assert Path(loaded["local_images"][0]).exists()


def test_style_and_motion_presets_are_available(tmp_path, monkeypatch):
    adapter = _adapter(tmp_path, monkeypatch)

    assert any(item["id"] == "forge-commercial-product" for item in adapter.list_styles())
    assert any(item["id"] == "subtle_push_in" for item in adapter.list_motions())
