import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipelines.comfy_client import ComfyClient


class DummyResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text
        self.content = text.encode("utf-8")

    def json(self):
        return self._payload


def test_check_health_uses_system_stats_endpoint(monkeypatch):
    seen = {}

    def fake_get(url, timeout=0):
        seen["url"] = url
        seen["timeout"] = timeout
        return DummyResponse(payload={"system_stats": {"ok": True}})

    monkeypatch.setattr("pipelines.comfy_client.httpx.get", fake_get)

    ok, stats = ComfyClient("localhost", 8188).check_health()

    assert ok is True
    assert seen["url"] == "http://localhost:8188/system_stats"
    assert stats["system_stats"]["ok"] is True


def test_list_models_extracts_nested_object_info_choices(monkeypatch):
    object_info = {
        "UNETLoader": {
            "input": {
                "required": {
                    "unet_name": [
                        [
                            "flux2_dev_fp8mixed.safetensors",
                            "z_image_turbo_bf16.safetensors",
                        ],
                        {},
                    ]
                }
            }
        },
        "VAELoader": {
            "input": {
                "required": {
                    "vae_name": [["full_encoder_small_decoder.safetensors"], {}]
                }
            }
        },
    }

    def fake_get(url, timeout=0):
        return DummyResponse(payload=object_info)

    monkeypatch.setattr("pipelines.comfy_client.httpx.get", fake_get)

    models = ComfyClient("localhost", 8188).list_models()

    assert "flux2_dev_fp8mixed.safetensors" in models
    assert "z_image_turbo_bf16.safetensors" in models
    assert "full_encoder_small_decoder.safetensors" in models
