"""
Tests for ComfyPayloadValidator and ComfyRemediationHarness.
"""

import pytest
import json
import os
import tempfile
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
if PROJECT_ROOT not in os.sys.path:
    os.sys.path.insert(0, PROJECT_ROOT)

from core.dispatch.comfy_payload_validator import ComfyPayloadValidator, ValidationReport


# ── Fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def validator():
    return ComfyPayloadValidator()


@pytest.fixture
def valid_api_workflow():
    """Minimal valid ComfyUI API workflow."""
    return {
        "prompt": {
            "1": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": "model.safetensors"}
            },
            "6": {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": "a photo", "clip": ["1", 1]}
            },
            "7": {
                "class_type": "EmptyLatentImage",
                "inputs": {"width": 512, "height": 512, "batch_size": 1}
            },
            "8": {
                "class_type": "KSampler",
                "inputs": {
                    "model": ["1", 0],
                    "positive": ["6", 0],
                    "negative": ["6", 0],
                    "latent_image": ["7", 0],
                    "seed": 42,
                    "steps": 20,
                    "cfg": 7.0,
                    "sampler_name": "euler",
                    "scheduler": "normal",
                    "denoise": 1.0
                }
            },
            "9": {
                "class_type": "VAEDecode",
                "inputs": {"samples": ["8", 0], "vae": ["1", 2]}
            },
            "10": {
                "class_type": "SaveImage",
                "inputs": {"images": ["9", 0], "filename_prefix": "test_output"}
            }
        }
    }


@pytest.fixture
def webui_format_workflow():
    """Web UI format (should be rejected)."""
    return {
        "nodes": [
            {"id": 1, "type": "CheckpointLoaderSimple", "widgets_values": ["model.safetensors"]},
            {"id": 6, "type": "CLIPTextEncode", "widgets_values": ["a photo"]},
        ],
        "links": [[1, 6, 0, 0]],
        "groups": []
    }


@pytest.fixture
def missing_class_type_workflow():
    """API format but one node lacks class_type."""
    return {
        "prompt": {
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {}},
            "71": {"inputs": {"text": "broken"}},  # missing class_type
        }
    }


@pytest.fixture
def orphaned_connection_workflow():
    """References a node that doesn't exist."""
    return {
        "prompt": {
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {}},
            "6": {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": "hello", "clip": ["99", 0]}  # 99 doesn't exist
            },
            "7": {"class_type": "EmptyLatentImage", "inputs": {}},
            "8": {
                "class_type": "KSampler",
                "inputs": {
                    "model": ["1", 0],
                    "positive": ["6", 0],
                    "negative": ["6", 0],
                    "latent_image": ["7", 0],
                    "seed": 42, "steps": 20, "cfg": 7.0,
                    "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0
                }
            },
            "10": {"class_type": "SaveImage", "inputs": {"images": ["9", 0], "filename_prefix": "test"}}
        }
    }


@pytest.fixture
def video_descriptor():
    """Video content descriptor (not a workflow yet)."""
    return {
        "type": "VIDEO_PROMPT",
        "status": "awaiting_ltx_workflow",
        "filename_prefix": "Prompt_01_Video_01",
        "anchor_image": "Prompt_01_Video_01_ANCHOR.png",
        "prompt_text": "A cinematic drone shot tracking a canyon crest."
    }


# ── Validation Tests ─────────────────────────────────────────────────

class TestComfyPayloadValidator:

    def test_valid_workflow_passes(self, validator, valid_api_workflow):
        report = validator.validate(valid_api_workflow)
        assert report.is_valid is True
        assert len(report.errors) == 0

    def test_webui_format_rejected(self, validator, webui_format_workflow):
        report = validator.validate(webui_format_workflow)
        assert report.is_valid is False
        assert any("Web UI format" in e for e in report.errors)

    def test_missing_class_type_caught(self, validator, missing_class_type_workflow):
        report = validator.validate(missing_class_type_workflow)
        assert report.is_valid is False
        assert any("no class_type" in e for e in report.errors)
        assert any("71" in e for e in report.errors)

    def test_orphaned_connection_caught(self, validator, orphaned_connection_workflow):
        report = validator.validate(orphaned_connection_workflow)
        assert report.is_valid is False
        assert any("non-existent node '99'" in e for e in report.errors)
        assert "99" in report.orphaned_nodes

    def test_missing_required_nodes_caught(self, validator):
        payload = {"prompt": {"1": {"class_type": "CheckpointLoaderSimple", "inputs": {}}}}
        report = validator.validate(payload)
        assert report.is_valid is False
        assert any("Missing required node types" in e for e in report.errors)
        assert "KSampler" in report.missing_required_nodes
        assert "SaveImage" in report.missing_required_nodes

    def test_model_reference_checked(self, validator, valid_api_workflow):
        report = validator.validate(valid_api_workflow, models_available=["other_model.safetensors"], strict=True)
        assert report.is_valid is False
        assert "model.safetensors" in report.missing_models

    def test_model_reference_warning_when_not_strict(self, validator, valid_api_workflow):
        report = validator.validate(valid_api_workflow, models_available=["other_model.safetensors"], strict=False)
        assert report.is_valid is True  # warning, not error
        assert len(report.warnings) > 0
        assert "model.safetensors" in report.missing_models

    def test_video_descriptor_accepted(self, validator, video_descriptor):
        report = validator.validate(video_descriptor)
        assert report.is_valid is True
        assert len(report.errors) == 0

    def test_seed_warning_on_ksampler(self, validator, valid_api_workflow):
        # Remove seed to trigger warning
        del valid_api_workflow["prompt"]["8"]["inputs"]["seed"]
        report = validator.validate(valid_api_workflow)
        assert report.is_valid is True
        assert any("no seed" in w for w in report.warnings)

    def test_saveimage_prefix_warning(self, validator):
        payload = {
            "prompt": {
                "1": {"class_type": "CheckpointLoaderSimple", "inputs": {}},
                "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "x", "clip": ["1", 1]}},
                "7": {"class_type": "EmptyLatentImage", "inputs": {"width": 512, "height": 512, "batch_size": 1}},
                "8": {
                    "class_type": "KSampler",
                    "inputs": {
                        "model": ["1", 0], "positive": ["6", 0], "negative": ["6", 0],
                        "latent_image": ["7", 0], "seed": 42, "steps": 20, "cfg": 7.0,
                        "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0
                    }
                },
                "10": {"class_type": "SaveImage", "inputs": {"images": ["8", 0], "filename_prefix": "ComfyUI"}}
            }
        }
        report = validator.validate(payload)
        assert report.is_valid is True
        assert any("generic filename_prefix" in w for w in report.warnings)


class TestValidationReport:

    def test_add_error_marks_invalid(self):
        r = ValidationReport()
        assert r.is_valid is True
        r.add_error("something broke")
        assert r.is_valid is False
        assert r.errors == ["something broke"]

    def test_add_warning_keeps_valid(self):
        r = ValidationReport()
        r.add_warning("just a heads up")
        assert r.is_valid is True
        assert r.warnings == ["just a heads up"]


class TestFileValidation:

    def test_validate_missing_file(self, validator):
        report = validator.validate_file("/nonexistent/path.json")
        assert report.is_valid is False
        assert "not found" in report.errors[0].lower()

    def test_validate_real_file(self, validator, valid_api_workflow, tmp_path):
        path = tmp_path / "test.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(valid_api_workflow, f)
        report = validator.validate_file(path)
        assert report.is_valid is True

    def test_validate_malformed_json(self, validator, tmp_path):
        path = tmp_path / "bad.json"
        with open(path, "w", encoding="utf-8") as f:
            f.write("not json at all {{{")
        report = validator.validate_file(path)
        assert report.is_valid is False
        assert "Invalid JSON" in report.errors[0]
