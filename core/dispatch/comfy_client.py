import asyncio
import httpx
import json
import os
import logging
from pathlib import Path
from typing import Optional

from core.dispatch.lora_presets import LORA_PRESETS, available_lora_names, infer_lora_profile

logger = logging.getLogger(__name__)

class ComfyUIClient:
    def __init__(self, base_url: str):
        # base_url should include protocol and host/port, e.g., http://localhost:8188
        self.base_url = base_url.rstrip("/")

    async def check_health(self) -> tuple[bool, dict]:
        """Returns True/False + system info"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.base_url}/system_stats", timeout=5.0)
                if response.status_code == 200:
                    return True, response.json()
                return False, {"error": f"Status code {response.status_code}"}
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False, {"error": str(e)}

    async def list_models(self, loader_type="diffusion_model") -> list[str]:
        """Queries /object_info/{loader}, returns model list"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.base_url}/object_info", timeout=5.0)
                if response.status_code == 200:
                    data = response.json()
                    models = []
                    for key, val in data.items():
                        if loader_type in str(val).lower():
                            models.append(key)
                    return models
                return []
        except Exception as e:
            logger.error(f"Error listing models: {e}")
            return []

    async def submit_prompt(self, workflow_dict: dict) -> dict:
        """POST to /prompt, returns dict with prompt_id or detailed error."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/prompt", 
                    json={"prompt": workflow_dict}, 
                    timeout=5.0
                )
                if response.status_code == 200:
                    return {"ok": True, "prompt_id": response.json().get("prompt_id")}
                logger.error(f"Submission failed ({response.status_code}): {response.text}")
                detail = None
                try:
                    payload = response.json()
                    err = payload.get("error", {})
                    detail = err.get("type") or err.get("message") or response.text
                except Exception:
                    detail = response.text
                return {
                    "ok": False,
                    "status_code": response.status_code,
                    "error": detail or "ComfyUI submission failed",
                    "raw": response.text,
                }
        except Exception as e:
            logger.error(f"Error submitting prompt: {e}")
            return {"ok": False, "error": str(e)}

    async def upload_image(self, image_path: str) -> dict:
        """Upload a local image to ComfyUI input directory."""
        p = Path(image_path)
        if not p.exists():
            return {"ok": False, "error": f"file_not_found:{image_path}"}
        try:
            async with httpx.AsyncClient() as client:
                with open(p, "rb") as f:
                    files = {"image": (p.name, f, "application/octet-stream")}
                    data = {"overwrite": "true", "type": "input"}
                    response = await client.post(f"{self.base_url}/upload/image", files=files, data=data, timeout=30.0)
            if response.status_code == 200:
                payload = response.json() if response.text else {}
                name = payload.get("name") or p.name
                subfolder = payload.get("subfolder", "")
                return {"ok": True, "name": name, "subfolder": subfolder}
            return {"ok": False, "error": f"http_{response.status_code}:{response.text[:200]}"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def load_workflow(self, workflow_name: str) -> dict:
        """Load workflow JSON from repo workflows directory."""
        repo_root = Path(__file__).resolve().parents[2]
        candidates = [
            repo_root / "workflows" / workflow_name,
            repo_root / "workflows" / f"{workflow_name}.json",
            repo_root / "workflows" / f"{workflow_name}_api.json",
        ]
        for c in candidates:
            if c.exists():
                with open(c, "r", encoding="utf-8") as f:
                    return json.load(f)
        raise FileNotFoundError(f"Workflow not found: {workflow_name}")

    async def inject_prompt(self, workflow: dict, prompt_text: str, target_node: str = "6") -> dict:
        """Inject prompt text into target CLIPTextEncode node or first positive node."""
        prompt_block = workflow.get("prompt", workflow)
        target = str(target_node or "6")
        if target in prompt_block and isinstance(prompt_block[target], dict):
            node = prompt_block[target]
            if "inputs" in node and "text" in node["inputs"]:
                node["inputs"]["text"] = prompt_text
                return workflow

        negative_markers = ("blurry", "low quality", "worst quality", "deformed", "watermark", "ugly", "bad anatomy", "bad hands", "negative", "nsfw")
        text_encode_types = ("CLIPTextEncode", "GemmaAPITextEncode", "CLIPTextEncodeFlux", "T5TextEncode")
        for node in prompt_block.values():
            if not isinstance(node, dict):
                continue
            if node.get("class_type") not in text_encode_types:
                continue
            text = str(node.get("inputs", {}).get("text", "")).lower()
            is_negative = sum(1 for m in negative_markers if m in text) >= 1
            if not is_negative:
                node.setdefault("inputs", {})["text"] = prompt_text
                break
        return workflow

    @staticmethod
    def _ensure_output_node(nodes: dict, filename_prefix: str = "render") -> None:
        """Ensure workflow has at least one output node; add SaveImage if needed."""
        output_types = {"SaveImage", "PreviewImage", "VHS_VideoCombine", "SaveAnimatedWEBP", "SaveVideo"}
        has_output = any(
            isinstance(node, dict) and node.get("class_type") in output_types
            for node in nodes.values()
        )
        if has_output:
            return

        # Video workflow fallback: if a VIDEO stream exists, add SaveVideo.
        video_source_id = None
        for node_id, node in nodes.items():
            if not isinstance(node, dict):
                continue
            if node.get("class_type") in ("CreateVideo", "VHS_VideoCombine"):
                video_source_id = str(node_id)
                break
        if video_source_id is not None:
            numeric_ids = [int(k) for k in nodes.keys() if str(k).isdigit()]
            next_id = str(max(numeric_ids) + 1) if numeric_ids else "9999"
            nodes[next_id] = {
                "inputs": {
                    "filename_prefix": filename_prefix,
                    "video": [video_source_id, 0],
                },
                "class_type": "SaveVideo",
                "_meta": {"title": "Save Video (auto)"},
            }
            return

        image_source_id = None
        for node_id, node in nodes.items():
            if not isinstance(node, dict):
                continue
            if node.get("class_type") in ("VAEDecode", "ImageScale", "ImageUpscaleWithModel", "ImageResizeKJ"):
                image_source_id = str(node_id)
                break

        if image_source_id is None:
            return

        numeric_ids = [int(k) for k in nodes.keys() if str(k).isdigit()]
        next_id = str(max(numeric_ids) + 1) if numeric_ids else "9999"
        nodes[next_id] = {
            "inputs": {
                "filename_prefix": filename_prefix,
                "images": [image_source_id, 0],
            },
            "class_type": "SaveImage",
            "_meta": {"title": "Save Image (auto)"},
        }

    async def _get_object_info(self) -> dict:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.base_url}/object_info", timeout=10.0)
                if response.status_code == 200:
                    return response.json()
        except Exception as e:
            logger.warning(f"Failed to fetch object_info: {e}")
        return {}

    @staticmethod
    def _first_choice(object_info: dict, class_type: str, key: str):
        try:
            required = object_info.get(class_type, {}).get("input", {}).get("required", {})
            meta = required.get(key)
            if isinstance(meta, list) and meta and isinstance(meta[0], list) and meta[0]:
                return meta[0][0]
        except Exception:
            return None
        return None

    def _hydrate_workflow_placeholders(self, nodes: dict, prompt: str, object_info: dict) -> None:
        negative_default = "blurry, low quality, worst quality, deformed, watermark"

        for node in nodes.values():
            if not isinstance(node, dict):
                continue
            class_type = node.get("class_type", "")
            inputs = node.get("inputs")
            if not isinstance(inputs, dict):
                continue

            # Fill required fields from Comfy object_info metadata where possible.
            required = object_info.get(class_type, {}).get("input", {}).get("required", {})
            for key, spec in required.items():
                current = inputs.get(key)
                if current not in ("", None):
                    continue
                if isinstance(spec, list) and spec:
                    # Dynamic combo inputs must be sent as the selected key plus
                    # flattened sub-inputs, not as the object_info schema object.
                    if len(spec) > 1 and spec[0] == "COMFY_DYNAMICCOMBO_V3" and isinstance(spec[1], dict):
                        options = spec[1].get("options")
                        if isinstance(options, list) and options:
                            option = options[0]
                            if isinstance(option, dict):
                                selected = option.get("key")
                                if selected:
                                    inputs[key] = selected
                                    nested = option.get("inputs", {}).get("required", {})
                                    if isinstance(nested, dict):
                                        for nested_key, nested_spec in nested.items():
                                            flat_key = f"{key}.{nested_key}"
                                            if flat_key in inputs and inputs[flat_key] not in ("", None):
                                                continue
                                            if (
                                                isinstance(nested_spec, list)
                                                and len(nested_spec) > 1
                                                and isinstance(nested_spec[1], dict)
                                                and "default" in nested_spec[1]
                                            ):
                                                inputs[flat_key] = nested_spec[1]["default"]
                                    continue
                    # COMBO fields in object_info often look like:
                    # ["COMBO", {"options": [...]}]
                    if (
                        len(spec) > 1
                        and isinstance(spec[1], dict)
                        and isinstance(spec[1].get("options"), list)
                        and spec[1]["options"]
                    ):
                        inputs[key] = spec[1]["options"][0]
                        continue
                    # Choice list, e.g. [["euler", ...], {...}]
                    if isinstance(spec[0], list) and spec[0]:
                        inputs[key] = spec[0][0]
                        continue
                    # Typed field, e.g. ["FLOAT", {"default": 1.0}]
                    if len(spec) > 1 and isinstance(spec[1], dict) and "default" in spec[1]:
                        inputs[key] = spec[1]["default"]
                        continue

            # Fill loader model selectors
            if class_type in ("UNETLoader", "VAELoader", "CLIPLoader"):
                field = {
                    "UNETLoader": "unet_name",
                    "VAELoader": "vae_name",
                    "CLIPLoader": "clip_name",
                }[class_type]
                if field in inputs and (inputs[field] == "" or inputs[field] is None):
                    choice = self._first_choice(object_info, class_type, field)
                    if choice:
                        inputs[field] = choice

            # Fill empty prompt text nodes
            if class_type in ("CLIPTextEncode", "GemmaAPITextEncode", "CLIPTextEncodeFlux", "T5TextEncode"):
                if "text" not in inputs:
                    inputs["text"] = ""
                title = str(node.get("_meta", {}).get("title", "")).lower()
                if "neg" in title:
                    inputs["text"] = negative_default
                elif inputs["text"] == "" or inputs["text"] is None:
                    inputs["text"] = prompt or "cinematic still frame"

    @staticmethod
    def _apply_lora_profile(nodes: dict, object_info: dict, profile_key: str = "") -> dict:
        key = (profile_key or "").strip()
        preset = LORA_PRESETS.get(key)
        if not preset:
            return {"requested": key, "applied": False, "reason": "no_profile"}

        installed = available_lora_names(object_info)
        selected = next((name for name in preset.candidates if name in installed), "")
        if not selected:
            return {
                "requested": preset.key,
                "applied": False,
                "reason": "lora_not_installed",
                "candidates": list(preset.candidates),
                "source_url": preset.source_url,
            }

        touched = 0
        for node in nodes.values():
            if not isinstance(node, dict):
                continue
            class_type = str(node.get("class_type", ""))
            if "lora" not in class_type.lower():
                continue
            inputs = node.get("inputs")
            if not isinstance(inputs, dict):
                continue
            lora_keys = [k for k in inputs if "lora" in str(k).lower() and str(k).lower().endswith("name")]
            if not lora_keys:
                lora_keys = [k for k in inputs if "lora" in str(k).lower()]
            for lora_key in lora_keys:
                if isinstance(inputs.get(lora_key), list):
                    continue
                inputs[lora_key] = selected
                touched += 1
            for strength_key in ("strength_model", "strength", "model_strength"):
                if strength_key in inputs and not isinstance(inputs.get(strength_key), list):
                    inputs[strength_key] = preset.default_strength

        return {
            "requested": preset.key,
            "label": preset.label,
            "applied": touched > 0,
            "lora_name": selected,
            "strength": preset.default_strength,
            "source_url": preset.source_url,
            "trigger_words": list(preset.trigger_words),
            "reason": "applied" if touched else "no_lora_node",
        }

    @staticmethod
    def _prepend_lora_triggers(prompt: str, lora_status: dict) -> str:
        if not lora_status.get("applied"):
            return prompt
        triggers = [str(t).strip() for t in lora_status.get("trigger_words", []) if str(t).strip()]
        if not triggers:
            return prompt
        existing = prompt or ""
        missing = [t for t in triggers if t.lower() not in existing.lower()]
        if not missing:
            return existing
        return ", ".join(missing + [existing]).strip(", ")

    def _convert_webui_workflow_to_api(self, workflow: dict, object_info: dict) -> dict:
        """
        Convert Comfy WebUI graph export to API prompt format.
        Supports plain graph exports and wrapper-subgraph exports.
        """
        if not isinstance(workflow, dict):
            return {}
        if "prompt" in workflow and isinstance(workflow["prompt"], dict):
            return workflow["prompt"]

        nodes = workflow.get("nodes")
        links = workflow.get("links")
        if not isinstance(nodes, list):
            return {}

        top_nodes = nodes
        top_links = links if isinstance(links, list) else []
        wrapper_input_slot_sources: dict[int, tuple[str, int]] = {}
        external_origin_ids: set[str] = set()

        # Handle wrapper graph with nested subgraph definitions.
        subgraphs = workflow.get("definitions", {}).get("subgraphs")
        if isinstance(subgraphs, list):
            subgraph_by_id = {sg.get("id"): sg for sg in subgraphs if isinstance(sg, dict) and sg.get("id")}
            top_wrappers = [n for n in nodes if isinstance(n, dict) and n.get("type") in subgraph_by_id]
            if top_wrappers:
                wrapper = top_wrappers[0]
                wrapper_id = wrapper.get("id")
                # Capture top-level links feeding wrapper inputs, so we can map
                # subgraph interface links (-10 origins) back to real nodes.
                for l in top_links:
                    if isinstance(l, list) and len(l) >= 5 and l[3] == wrapper_id:
                        src_id = str(l[1])
                        src_slot = int(l[2]) if str(l[2]).isdigit() else 0
                        dst_slot = int(l[4]) if str(l[4]).isdigit() else 0
                        wrapper_input_slot_sources[dst_slot] = (src_id, src_slot)
                        external_origin_ids.add(src_id)
                sg = subgraph_by_id[wrapper["type"]]
                nodes = sg.get("nodes", [])
                links = sg.get("links", [])

        if not isinstance(links, list):
            links = []

        # Normalize links into map: link_id -> (origin_id, origin_slot, target_id, target_slot)
        link_map = {}
        for item in links:
            if isinstance(item, list) and len(item) >= 5:
                link_map[item[0]] = (item[1], item[2], item[3], item[4])
            elif isinstance(item, dict) and {"id", "origin_id", "origin_slot", "target_id", "target_slot"} <= set(item.keys()):
                link_map[item["id"]] = (item["origin_id"], item["origin_slot"], item["target_id"], item["target_slot"])

        prompt_nodes: dict = {}
        node_by_id = {
            str(n.get("id")): n
            for n in nodes
            if isinstance(n, dict) and n.get("id") is not None
        }

        def _resolve_origin(origin_id: object, origin_slot: object) -> tuple[str, int] | None:
            # Reroute nodes are editor plumbing and should be flattened to their real source.
            visited: set[str] = set()
            cur_id = str(origin_id)
            cur_slot = int(origin_slot) if str(origin_slot).isdigit() else 0
            while True:
                if cur_id in visited:
                    return None
                visited.add(cur_id)
                src_node = node_by_id.get(cur_id)
                if not isinstance(src_node, dict):
                    return None
                if src_node.get("type") != "Reroute":
                    return cur_id, cur_slot
                reroute_inputs = src_node.get("inputs") or []
                if not reroute_inputs:
                    return None
                reroute_link = reroute_inputs[0].get("link") if isinstance(reroute_inputs[0], dict) else None
                if reroute_link not in link_map:
                    return None
                prev_origin_id, prev_origin_slot, _, _ = link_map[reroute_link]
                cur_id = str(prev_origin_id)
                cur_slot = int(prev_origin_slot) if str(prev_origin_slot).isdigit() else 0

        for node in nodes:
            if not isinstance(node, dict):
                continue
            class_type = node.get("type")
            node_id = node.get("id")
            if node_id is None or not class_type:
                continue
            # Skip annotation/wrapper nodes and unknown aliases.
            if class_type in ("MarkdownNote", "Note", "Reroute"):
                continue

            converted = {"class_type": class_type, "inputs": {}}

            # Build widget-name -> value map from WebUI node metadata.
            # Handles control-after-generate tokens (e.g. seed randomization mode).
            widget_values = list(node.get("widgets_values", []) or [])
            widget_names = [
                inp.get("name")
                for inp in (node.get("inputs", []) or [])
                if isinstance(inp, dict) and isinstance(inp.get("widget"), dict) and inp.get("name")
            ]
            control_tokens = {"fixed", "randomize", "increment", "decrement"}
            widget_map: dict[str, object] = {}
            vi = 0
            for wname in widget_names:
                if vi >= len(widget_values):
                    break
                widget_map[wname] = widget_values[vi]
                vi += 1
                # Many Comfy widgets (notably seed) store an extra mode token.
                if wname == "seed" and vi < len(widget_values) and isinstance(widget_values[vi], str) and widget_values[vi] in control_tokens:
                    converted["inputs"]["control_after_generate"] = widget_values[vi]
                    vi += 1

            # Some primitive nodes (PrimitiveInt/Float/Boolean/String) expose
            # required input "value" but may not publish a named widget entry.
            # In that case, fallback to first widget_values element.
            if "value" not in widget_map and widget_values:
                first_val = widget_values[0]
                if not (isinstance(first_val, str) and first_val in control_tokens):
                    widget_map["value"] = first_val

            # Connected inputs
            for inp in node.get("inputs", []) or []:
                if not isinstance(inp, dict):
                    continue
                name = inp.get("name")
                link_id = inp.get("link")
                if name and link_id in link_map:
                    origin_id, origin_slot, _, _ = link_map[link_id]
                    # Subgraph wrapper pseudo-nodes use negative ids (e.g. -10, -20).
                    # These are not real runtime nodes in Comfy API payloads.
                    try:
                        if int(origin_id) < 0:
                            if int(origin_id) == -10:
                                slot_index = int(origin_slot) if str(origin_slot).isdigit() else 0
                                mapped = wrapper_input_slot_sources.get(slot_index)
                                if mapped:
                                    mapped_id, mapped_slot = mapped
                                    converted["inputs"][name] = [mapped_id, mapped_slot]
                            continue
                    except Exception:
                        pass
                    resolved = _resolve_origin(origin_id, origin_slot)
                    if resolved is None:
                        continue
                    resolved_id, resolved_slot = resolved
                    converted["inputs"][name] = [resolved_id, resolved_slot]

            # Widget/default inputs from schema order
            schema = object_info.get(class_type, {}).get("input", {})
            required = list((schema.get("required") or {}).keys())
            optional = list((schema.get("optional") or {}).keys())
            ordered_keys = required + optional
            if not widget_names and widget_values and ordered_keys:
                unconnected_keys = [key for key in ordered_keys if key not in converted["inputs"]]
                for idx, key in enumerate(unconnected_keys):
                    if idx >= len(widget_values):
                        break
                    widget_map.setdefault(key, widget_values[idx])
            for key in ordered_keys:
                if key in converted["inputs"]:
                    continue
                if key in widget_map:
                    converted["inputs"][key] = widget_map[key]

            # Comfy dynamic widgets are exported as a compact widgets_values
            # list, not named node inputs. Preserve the actual selected runtime
            # values for ResizeImageMaskNode instead of letting object_info
            # hydration inject the schema object.
            if class_type == "ResizeImageMaskNode" and widget_values:
                resize_type = str(widget_values[0] or "").strip()
                if resize_type:
                    converted["inputs"]["resize_type"] = resize_type
                    if resize_type == "scale dimensions":
                        if len(widget_values) > 1:
                            converted["inputs"]["resize_type.width"] = widget_values[1]
                        if len(widget_values) > 2:
                            converted["inputs"]["resize_type.height"] = widget_values[2]
                        if len(widget_values) > 3:
                            converted["inputs"]["resize_type.crop"] = widget_values[3]
                        if len(widget_values) > 4:
                            converted["inputs"]["scale_method"] = widget_values[4]
                    elif resize_type == "scale longer dimension":
                        if len(widget_values) > 1:
                            converted["inputs"]["resize_type.longer_size"] = widget_values[1]
                        if len(widget_values) > 2:
                            converted["inputs"]["scale_method"] = widget_values[2]
                    elif resize_type == "scale shorter dimension":
                        if len(widget_values) > 1:
                            converted["inputs"]["resize_type.shorter_size"] = widget_values[1]
                        if len(widget_values) > 2:
                            converted["inputs"]["scale_method"] = widget_values[2]
                    elif resize_type == "scale width":
                        if len(widget_values) > 1:
                            converted["inputs"]["resize_type.width"] = widget_values[1]
                        if len(widget_values) > 2:
                            converted["inputs"]["scale_method"] = widget_values[2]
                    elif resize_type == "scale height":
                        if len(widget_values) > 1:
                            converted["inputs"]["resize_type.height"] = widget_values[1]
                        if len(widget_values) > 2:
                            converted["inputs"]["scale_method"] = widget_values[2]

            prompt_nodes[str(node_id)] = converted

        # Include any top-level source nodes that feed subgraph interface inputs
        # (commonly LoadImage for i2v workflows).
        if external_origin_ids:
            for node in top_nodes:
                if not isinstance(node, dict):
                    continue
                node_id = node.get("id")
                class_type = node.get("type")
                if node_id is None or not class_type:
                    continue
                node_id_str = str(node_id)
                if node_id_str in prompt_nodes or node_id_str not in external_origin_ids:
                    continue
                if class_type in ("MarkdownNote", "Note", "Reroute"):
                    continue
                converted = {"class_type": class_type, "inputs": {}}
                widget_values = list(node.get("widgets_values", []) or [])
                widget_names = [
                    inp.get("name")
                    for inp in (node.get("inputs", []) or [])
                    if isinstance(inp, dict) and isinstance(inp.get("widget"), dict) and inp.get("name")
                ]
                for idx, key in enumerate(widget_names):
                    if idx < len(widget_values):
                        converted["inputs"][key] = widget_values[idx]
                prompt_nodes[node_id_str] = converted

        return prompt_nodes

    async def poll_job(self, prompt_id: str, timeout_sec: int = 300) -> str | None:
        """Polls /history/{prompt_id} every 5s, returns output filename when done"""
        start_time = asyncio.get_event_loop().time()
        async with httpx.AsyncClient() as client:
            while (asyncio.get_event_loop().time() - start_time) < timeout_sec:
                try:
                    response = await client.get(f"{self.base_url}/history/{prompt_id}", timeout=5.0)
                    if response.status_code == 200:
                        data = response.json()
                        if prompt_id in data:
                            # Job complete, extract filenames from outputs
                            outputs = data[prompt_id].get("outputs", {})
                            for node_id, node_output in outputs.items():
                                if "images" in node_output and len(node_output["images"]) > 0:
                                    return node_output["images"][0]["filename"]
                    await asyncio.sleep(5)
                except Exception as e:
                    logger.error(f"Error polling job: {e}")
                    await asyncio.sleep(5)
        return None

    async def download_outputs(self, job_id: str, output_dir: str) -> list[str]:
        """
        Downloads all output images for a completed job.
        Returns list of saved file paths.
        Creates output_dir if it doesn't exist.
        """
        saved_files = []
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        try:
            async with httpx.AsyncClient() as client:
                # First, get history to find the filenames for this job_id
                response = await client.get(f"{self.base_url}/history/{job_id}", timeout=5.0)
                if response.status_code != 200:
                    logger.error(f"Failed to fetch history for job {job_id}")
                    return []

                history = response.json()
                if job_id not in history:
                    logger.error(f"Job ID {job_id} not found in history")
                    return []

                outputs = history[job_id].get("outputs", {})
                logger.info(
                    "download_outputs: job %s output keys per node: %s",
                    job_id,
                    ", ".join(
                        f"{nid}={list(no.keys())}"
                        for nid, no in outputs.items()
                        if isinstance(no, dict)
                    ),
                )
                media_keys = ("images", "gifs", "videos", "animated", "files")
                for node_id, node_output in outputs.items():
                    if not isinstance(node_output, dict):
                        continue
                    for media_key in media_keys:
                        items = node_output.get(media_key)
                        if not items:
                            continue
                        if isinstance(items, dict):
                            items = [items]
                        if not isinstance(items, list):
                            continue
                        for img_data in items:
                            if not isinstance(img_data, dict):
                                continue
                            filename = img_data.get("filename")
                            if not filename:
                                continue
                            subfolder = img_data.get("subfolder", "")
                            file_type = img_data.get("type", "output")

                            download_url = f"{self.base_url}/view"
                            params = {
                                "filename": filename,
                                "type": file_type,
                                "subfolder": subfolder,
                            }

                            try:
                                resp = await client.get(download_url, params=params, timeout=60.0)
                            except Exception as e:
                                logger.error(f"download_outputs: GET /view failed for {filename}: {e}")
                                continue
                            if resp.status_code == 200:
                                target_file = output_path / filename
                                with open(target_file, "wb") as f:
                                    f.write(resp.content)
                                saved_files.append(str(target_file))
                                logger.info(f"download_outputs: saved {target_file}")
                            else:
                                logger.error(f"Failed to download {filename}: Status {resp.status_code}")

        except Exception as e:
            logger.error(f"Error in download_outputs: {e}")

        return saved_files

    async def submit_prompt_for_shot(
        self,
        shot_id: str | None = None,
        prompt: str = "",
        workflow_path: str | None = None,
        seed: int | None = None,
        output_dir: str | None = None,
        image_path: Optional[str] = None,
        image_paths: Optional[list[str]] = None,
        wait_for_output: bool = True,
        width: int | None = None,
        height: int | None = None,
        duration: int | None = None,
        fps: int | None = None,
        lora_profile: str | None = None,
    ) -> dict:
        """Load a workflow, inject prompt/seed, submit, poll, and optionally download outputs."""
        import random

        repo_root = Path(__file__).resolve().parents[2]
        if not workflow_path:
            candidates = [
                repo_root / "workflows" / "01_flux2_text_to_image.json",
                repo_root / "workflows" / "08_flux2_klein_9b_text_to_image.json",
            ]
            workflow_path = next((str(path) for path in candidates if path.exists()), None)

        if not workflow_path or not os.path.exists(workflow_path):
            logger.error("No workflow file found")
            return {"status": "error", "error": "No workflow file found"}

        try:
            with open(workflow_path, "r", encoding="utf-8") as f:
                workflow = json.load(f)
        except Exception as e:
            logger.error("Failed to load workflow: %s", e)
            return {"status": "error", "error": f"Failed to load workflow: {e}"}

        object_info = await self._get_object_info()
        nodes = self._convert_webui_workflow_to_api(workflow, object_info)
        if not isinstance(nodes, dict) or not nodes:
            return {"status": "error", "error": "Workflow is not ComfyUI API format"}
        self._ensure_output_node(nodes, filename_prefix=shot_id or "render")
        self._hydrate_workflow_placeholders(nodes, prompt, object_info)
        lora_key = (lora_profile or infer_lora_profile(workflow_path, prompt)).strip()
        lora_status = self._apply_lora_profile(nodes, object_info, lora_key) if lora_key else {
            "requested": "",
            "applied": False,
            "reason": "none",
        }
        prompt = self._prepend_lora_triggers(prompt, lora_status)

        requested_image_paths = [str(p) for p in (image_paths or []) if str(p or "").strip()]
        if image_path and not requested_image_paths:
            requested_image_paths = [image_path]
        uploaded_names: list[str] = []
        for requested_image_path in requested_image_paths:
            up = await self.upload_image(requested_image_path)
            if up.get("ok"):
                uploaded_names.append(str(up.get("name") or ""))
            else:
                logger.warning("Image upload failed for %s: %s", requested_image_path, up.get("error"))
        uploaded_name = uploaded_names[0] if uploaded_names else None

        chosen_seed = seed if seed is not None else random.randint(1, 2**32 - 1)
        negative_markers = ("blurry", "low quality", "worst quality", "deformed", "watermark", "ugly", "bad anatomy", "bad hands", "negative", "nsfw")
        target_width = int(width or 0)
        target_height = int(height or 0)
        target_fps = int(fps or 0)
        target_duration = int(duration or 0)
        target_frames = target_duration * target_fps if target_duration and target_fps else 0

        load_image_slots = []
        for node in nodes.values():
            if not isinstance(node, dict):
                continue
            inputs = node.get("inputs")
            if not isinstance(inputs, dict):
                continue

            class_type = node.get("class_type", "")
            if class_type in ("CLIPTextEncode", "GemmaAPITextEncode", "CLIPTextEncodeFlux", "T5TextEncode") and "text" in inputs:
                existing = str(inputs.get("text", "")).lower()
                is_negative = sum(1 for m in negative_markers if m in existing) >= 1
                if not is_negative:
                    inputs["text"] = prompt
            if uploaded_name and class_type in ("LoadImage", "LoadImageMask", "VHS_LoadImagePath"):
                load_image_slots.append(inputs)
            if class_type in ("KSampler", "SamplerCustom", "SamplerCustomAdvanced") and "seed" in inputs:
                inputs["seed"] = chosen_seed
            if class_type in ("RandomNoise", "FluxNoise") and "noise_seed" in inputs:
                inputs["noise_seed"] = chosen_seed
            for key in list(inputs.keys()):
                current = inputs.get(key)
                if isinstance(current, list):
                    continue
                lower_key = str(key).lower()
                if target_width and (lower_key == "width" or lower_key.endswith(".width")):
                    inputs[key] = target_width
                elif target_height and (lower_key == "height" or lower_key.endswith(".height")):
                    inputs[key] = target_height
                elif target_fps and lower_key in {"fps", "frame_rate", "framerate", "video_fps"}:
                    inputs[key] = target_fps
                elif target_frames and lower_key in {"frames", "num_frames", "frame_count", "length"}:
                    inputs[key] = target_frames
                elif target_duration and lower_key in {"duration", "duration_sec", "duration_seconds", "seconds", "clip_duration"}:
                    inputs[key] = target_duration
            if class_type in ("SaveImage", "SaveVideo", "VHS_VideoCombine") and shot_id:
                inputs["filename_prefix"] = shot_id

        if uploaded_names and load_image_slots:
            for idx, slot in enumerate(load_image_slots):
                slot["image"] = uploaded_names[idx] if idx < len(uploaded_names) else uploaded_names[0]

        submit_result = await self.submit_prompt(nodes)
        if not submit_result.get("ok"):
            return {
                "status": "error",
                "error": submit_result.get("error", "Submission returned no prompt_id"),
                "status_code": submit_result.get("status_code"),
                "raw": submit_result.get("raw"),
                "lora": lora_status,
            }
        prompt_id = submit_result.get("prompt_id")
        if not prompt_id:
            return {"status": "error", "error": "Submission returned no prompt_id", "lora": lora_status}

        if not wait_for_output:
            return {
                "shot_id": shot_id,
                "status": "success",
                "prompt_id": prompt_id,
                "seed": chosen_seed,
                "queued": True,
                "uploaded_image": uploaded_name,
                "uploaded_images": uploaded_names,
                "lora": lora_status,
            }

        output_filename = await self.poll_job(prompt_id, timeout_sec=600)
        if not output_filename:
            return {"status": "error", "prompt_id": prompt_id, "error": f"Poll timed out for prompt {prompt_id}", "lora": lora_status}

        saved = []
        if output_dir:
            saved = await self.download_outputs(prompt_id, output_dir)

        return {
            "shot_id": shot_id,
            "status": "success",
            "prompt_id": prompt_id,
            "seed": chosen_seed,
            "output_filename": output_filename,
            "saved_files": saved,
            "uploaded_image": uploaded_name,
            "uploaded_images": uploaded_names,
            "lora": lora_status,
        }
