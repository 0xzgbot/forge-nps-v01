from core.dispatch.comfy_client import ComfyUIClient
from core.dispatch.lora_presets import available_lora_names, infer_lora_profile


def test_infer_lora_profile_for_character_sheet_workflow():
    assert infer_lora_profile("/tmp/02_flux2_multi_reference_character_sheet.json") == "flux2_multi_angle"
    assert infer_lora_profile("/tmp/01_flux2_text_to_image.json", "storyboard panel with camera angles") == "flux2_multi_angle"


def test_apply_lora_profile_only_when_installed():
    object_info = {
        "LoraLoaderModelOnly": {
            "input": {
                "required": {
                    "lora_name": [["flux-multi-angles-v2-72poses-comfy.safetensors"], {}],
                    "strength_model": ["FLOAT", {"default": 1.0}],
                }
            }
        }
    }
    nodes = {
        "1": {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {
                "model": ["0", 0],
                "lora_name": "Flux_2-Turbo-LoRA_comfyui.safetensors",
                "strength_model": 1.0,
            },
        }
    }
    assert "flux-multi-angles-v2-72poses-comfy.safetensors" in available_lora_names(object_info)
    result = ComfyUIClient._apply_lora_profile(nodes, object_info, "flux2_multi_angle")
    assert result["applied"] is True
    assert nodes["1"]["inputs"]["lora_name"] == "flux-multi-angles-v2-72poses-comfy.safetensors"
    assert nodes["1"]["inputs"]["strength_model"] == 0.65


def test_apply_lora_profile_falls_back_when_missing():
    nodes = {"1": {"class_type": "LoraLoaderModelOnly", "inputs": {"lora_name": "existing.safetensors"}}}
    result = ComfyUIClient._apply_lora_profile(nodes, {}, "flux2_multi_angle")
    assert result["applied"] is False
    assert result["reason"] == "lora_not_installed"
    assert nodes["1"]["inputs"]["lora_name"] == "existing.safetensors"


def test_lora_trigger_words_are_prepended_once():
    prompt = ComfyUIClient._prepend_lora_triggers(
        "wide storyboard panel of a desert road",
        {"applied": True, "trigger_words": ["SSGMFV2"]},
    )
    assert prompt.startswith("SSGMFV2, wide storyboard")
    assert ComfyUIClient._prepend_lora_triggers(prompt, {"applied": True, "trigger_words": ["SSGMFV2"]}) == prompt
