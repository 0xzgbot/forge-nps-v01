import asyncio
import httpx
import json
import os
import logging
from pathlib import Path
from typing import Optional

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

        negative_markers = ("blurry", "low quality", "worst quality", "deformed", "watermark")
        for node in prompt_block.values():
            if not isinstance(node, dict):
                continue
            if node.get("class_type") != "CLIPTextEncode":
                continue
            text = str(node.get("inputs", {}).get("text", "")).lower()
            is_negative = sum(1 for m in negative_markers if m in text) >= 2
            if not is_negative:
                node.setdefault("inputs", {})["text"] = prompt_text
                break
        return workflow

    @staticmethod
    def _ensure_output_node(nodes: dict, filename_prefix: str = "render") -> None:
        """Ensure workflow has at least one output node; add SaveImage if needed."""
        output_types = {"SaveImage", "PreviewImage", "VHS_VideoCombine", "SaveAnimatedWEBP"}
        has_output = any(
            isinstance(node, dict) and node.get("class_type") in output_types
            for node in nodes.values()
        )
        if has_output:
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
            if class_type == "CLIPTextEncode":
                # Ensure text field exists even when the workflow converter did not
                # attach a widget/default (common with subgraph exports).
                if "text" not in inputs:
                    inputs["text"] = ""
                title = str(node.get("_meta", {}).get("title", "")).lower()
                if "neg" in title:
                    inputs["text"] = negative_default
                elif inputs["text"] == "" or inputs["text"] is None:
                    inputs["text"] = prompt or "cinematic still frame"

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

        # Handle wrapper graph with nested subgraph definitions.
        subgraphs = workflow.get("definitions", {}).get("subgraphs")
        if isinstance(subgraphs, list):
            subgraph_by_id = {sg.get("id"): sg for sg in subgraphs if isinstance(sg, dict) and sg.get("id")}
            top_wrappers = [n for n in nodes if isinstance(n, dict) and n.get("type") in subgraph_by_id]
            if top_wrappers:
                sg = subgraph_by_id[top_wrappers[0]["type"]]
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
        known_types = set(object_info.keys())
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
            if known_types and class_type not in known_types:
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
                            continue
                    except Exception:
                        pass
                    converted["inputs"][name] = [str(origin_id), int(origin_slot)]

            # Widget/default inputs from schema order
            schema = object_info.get(class_type, {}).get("input", {})
            required = list((schema.get("required") or {}).keys())
            optional = list((schema.get("optional") or {}).keys())
            ordered_keys = required + optional
            for key in ordered_keys:
                if key in converted["inputs"]:
                    continue
                if key in widget_map:
                    converted["inputs"][key] = widget_map[key]

            prompt_nodes[str(node_id)] = converted

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
                logger.info(f"download_outputs: job {job_id} output keys per node: " + ", ".join(f"{nid}={list(no.keys())}" for nid, no in outputs.items()))
                media_keys = ("images", "gifs", "videos", "animated", "files")
                for node_id, node_output in outputs.items():
                    for media_key in media_keys:
                        items = node_output.get(media_key)
                        if not items:
                            continue
                        for img_data in items:
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
        wait_for_output: bool = True,
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
        self._hydrate_workflow_placeholders(nodes, prompt, object_info)

        uploaded_name = None
        if image_path:
            up = await self.upload_image(image_path)
            if up.get("ok"):
                uploaded_name = str(up.get("name") or "")
            else:
                logger.warning("Image upload failed for %s: %s", image_path, up.get("error"))

        chosen_seed = seed if seed is not None else random.randint(1, 2**32 - 1)
        negative_markers = ("blurry", "low quality", "worst quality", "deformed", "watermark")

        load_image_slots = []
        for node in nodes.values():
            if not isinstance(node, dict):
                continue
            inputs = node.get("inputs")
            if not isinstance(inputs, dict):
                continue

            class_type = node.get("class_type", "")
            if class_type == "CLIPTextEncode" and "text" in inputs:
                existing = str(inputs.get("text", "")).lower()
                if not any(marker in existing for marker in negative_markers):
                    inputs["text"] = prompt
            if uploaded_name and class_type in ("LoadImage", "LoadImageMask", "VHS_LoadImagePath"):
                load_image_slots.append(inputs)
            if class_type in ("KSampler", "SamplerCustom", "SamplerCustomAdvanced") and "seed" in inputs:
                inputs["seed"] = chosen_seed
            if class_type in ("RandomNoise", "FluxNoise") and "noise_seed" in inputs:
                inputs["noise_seed"] = chosen_seed
            if class_type == "SaveImage" and shot_id:
                inputs["filename_prefix"] = shot_id

        if uploaded_name and load_image_slots:
            # Primary source image for i2v workflows.
            load_image_slots[0]["image"] = uploaded_name
            # Optional second source (e.g., first/last-frame workflows): reuse image.
            if len(load_image_slots) > 1:
                load_image_slots[1]["image"] = uploaded_name

        self._ensure_output_node(nodes, filename_prefix=shot_id or "render")
        submit_result = await self.submit_prompt(nodes)
        if not submit_result.get("ok"):
            return {
                "status": "error",
                "error": submit_result.get("error", "Submission returned no prompt_id"),
                "status_code": submit_result.get("status_code"),
                "raw": submit_result.get("raw"),
            }
        prompt_id = submit_result.get("prompt_id")
        if not prompt_id:
            return {"status": "error", "error": "Submission returned no prompt_id"}

        if not wait_for_output:
            return {
                "shot_id": shot_id,
                "status": "success",
                "prompt_id": prompt_id,
                "seed": chosen_seed,
                "queued": True,
                "uploaded_image": uploaded_name,
            }

        output_filename = await self.poll_job(prompt_id, timeout_sec=600)
        if not output_filename:
            return {"status": "error", "prompt_id": prompt_id, "error": f"Poll timed out for prompt {prompt_id}"}

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
        }
