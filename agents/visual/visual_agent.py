import logging
import json
import asyncio
from typing import Dict, Any, Optional
from pathlib import Path

from core.routing.architect_router import ArchitectRouter
from core.dispatch.dispatcher import ComfyDispatcher
from data.character_banks.bank_loader import get_quality_constants
from core.consistency.character_consistency_engine import CharacterConsistencyEngine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("VisualAgent")

class VisualAgent:
    def __init__(self, comfyui_url: str, character_engine: CharacterConsistencyEngine = None):
        self.comfyui_url = comfyui_url.rstrip('/')
        self.router = ArchitectRouter()
        self.dispatcher = ComfyDispatcher([self.comfyui_url])
        self.character_engine = character_engine
        self._connectivity_checked = False

    async def _ensure_connectivity(self):
        if not self._connectivity_checked:
            is_online = await self.dispatcher.check_connectivity()
            if not is_online:
                logger.warning("VisualAgent initialized but ComfyUI connection check FAILED. Proceeding with caution.")
            self._connectivity_checked = True

    async def _build_kernel_payload(self, shot_data: dict, model_hint: str = "flux_2_dev") -> dict:
        """
        Uses ArchitectRouter to get kernel/prompt and appends quality constants.
        Injects character consistency descriptors if a CharacterEngine is attached.
        """
        concept = f"{shot_data.get('visual_prompt', {}).get('subject', '')}, {shot_data.get('visual_prompt', {}).get('action', '')}"
        intent = shot_data.get('intent', 'high_fidelity_image')

        # --- CHARACTER CONSISTENCY: enrich prompt before routing ---
        if self.character_engine:
            description = shot_data.get('description', concept)
            enriched = self.character_engine.enrich_prompt(description, detect=True)
            if enriched != description:
                concept = enriched
                logger.info(f"[CONSISTENCY] Prompt enriched for character lock")

        result = self.router.route(intent, concept)
        
        if result["status"] == "error":
            raise ValueError(f"Routing failed: {result['message']}")
        
        payload = result["payload"]
        prompt_text = result["prompt"]
        
        # Append quality constants
        quality = get_quality_constants()
        
        if "prompt" in payload and isinstance(payload["prompt"], dict):
             for key in payload["prompt"]:
                 if isinstance(payload["prompt"][key], str):
                     payload["prompt"][key] += f", {quality}"
        elif isinstance(payload["prompt"], str):
             payload["prompt"] = f"{payload['prompt']}, {quality}"

        # --- CHARACTER CONSISTENCY: inject deterministic seed ---
        if self.character_engine:
            char_names = self.character_engine.detect_characters(shot_data.get('description', concept))
            shot_idx = shot_data.get('shot_index', 0)
            seed = self.character_engine.get_seed_for_shot(char_names, shot_idx)
            if seed >= 0 and "parameters" in payload:
                payload["parameters"]["seed"] = seed
                logger.info(f"[CONSISTENCY] Seed locked to {seed} for characters {char_names}")

        return payload

    async def load_workflow(self, kernel: str) -> dict:
        """Loads JSON workflow from repo workflows/."""
        wf_path = Path(__file__).parent.parent.parent / "workflows" / f"{kernel}.json"
        if not wf_path.exists():
            logger.warning(f"Workflow {wf_path} not found.")
            return {}
        with open(wf_path, 'r', encoding="utf-8") as f:
            return json.load(f)

    async def generate(self, shot_id: str, description: str, director_schema: Dict[str, Any]) -> Dict[str, Any]:
        """
        IMPLEMENTATION OF STEP 5: High-precision image/video generation via ComfyUI.
        Uses Hermes-3 prompts and handles both T2I (Flux) and I2V (LTX).
        """
        logger.info(f"[VisualAgent] Starting generation for shot {shot_id}")
        await self._ensure_connectivity()

        # 1. Prepare base data
        shot_data = {
            "id": shot_id,
            "description": description,
            "visual_prompt": {"subject": description}, # Fallback mapping
            "intent": director_schema.get("intent", "high_fidelity_image"),
            "shot_index": director_schema.get("shot_index", 0)
        }

        # 2. Determine workflow type (Image vs Video)
        is_video = shot_data["intent"] == "video_generation" or "ltx" in description.lower()
        kernel = "ltx_2_3" if is_video else "flux_2_dev"

        try:
            # 3. Load the target workflow
            workflow = await self.load_workflow(kernel)
            if not workflow:
                return {"status": "ERROR", "message": f"Could not load workflow for kernel: {kernel}"}

            # 4. Build enriched payload (handles prompt enrichment & character locking)
            payload = await self._build_kernel_payload(shot_data, model_hint=kernel)

            # 5. Inject the generated/enriched prompt into the workflow nodes
            target_node_id = None
            prompt_dict = workflow.get("prompt", {})
            if isinstance(prompt_dict, dict):
                for node_id, node_info in prompt_dict.items():
                    # Target CLIPTextEncode for images or similar text input nodes for video
                    if isinstance(node_info, dict) and node_info.get("class_type") in ["CLIPTextEncode", "FluxGuidance"]:
                        target_node_id = node_id
                        break
            
            if not target_node_id:
                 return {"status": "ERROR", "message": "No text encoding node found in workflow."}

            # Inject the final prompt string from our payload
            final_prompt_text = payload.get("prompt", "")
            if isinstance(payload.get("prompt"), dict):
                final_prompt_text = payload["prompt"].get("text", str(payload["prompt"]))
            
            workflow["prompt"][target_node_id]["inputs"]["text"] = str(final_prompt_text)

            # 6. Handle I2V (Image-to-Video) if anchor image is provided in schema/data
            if is_video and shot_data.get("anchor_image_path"):
                img_p = shot_data["anchor_image_path"]
                for node_id, node_info in workflow["prompt"].items():
                    if node_info.get("class_type") == "LoadImage":
                        node_info["inputs"]["image"] = Path(img_p).name # Comfy expects filename if in input dir
                        break

            # 7. Submit to ComfyUI via Dispatcher
            logger.info(f"[VisualAgent] Submitting {kernel} job for shot {shot_id}")
            response = await self.dispatcher.dispatch(workflow)

            if response["status"] == "success":
                return {
                    "status": "SUCCESS",
                    "asset_path": response["response"].get("filename"), # Comfy returns filename in response
                    "prompt_used": final_prompt_text,
                    "metadata": response["response"]
                }
            else:
                return {"status": "FAILED", "message": response.get("reason", "ComfyUI dispatch error")}

        except Exception as e:
            logger.error(f"[VisualAgent] Generation failed for {shot_id}: {e}")
            return {"status": "ERROR", "message": str(e)}

    async def submit_to_comfy(self, shot_data: dict, workflow: dict):
        """Legacy/Helper method to submit raw workflows."""
        await self._ensure_connectivity()
        payload = await self._build_kernel_payload(shot_data)
        
        if "prompt" in workflow and isinstance(workflow["prompt"], dict):
            full_payload = workflow
        else:
            full_payload = {"prompt": workflow}
        
        # --- CHARACTER CONSISTENCY: inject Redux anchor if available ---
        if self.character_engine:
            char_names = self.character_engine.detect_characters(shot_data.get('description', ''))
            for char in char_names:
                if self.character_engine.get_anchor_path(char):
                    full_payload = self.character_engine.inject_redux_anchor(full_payload, char)
                    break  # Only inject first character anchor for now
        
        # Inject the generated prompt into the workflow (targeting CLIPTextEncode)
        target_node_id = None
        prompt_dict = full_payload.get("prompt", {})
        if isinstance(prompt_dict, dict):
            for node_id, node_info in prompt_dict.items():
                if isinstance(node_info, dict) and node_info.get("class_type") == "CLIPTextEncode":
                    target_node_id = node_id
                    break
        
        if target_node_id:
            prompt_content = payload.get("prompt", "")
            if isinstance(payload.get("prompt"), dict):
                 prompt_content = payload["prompt"].get("text", "")
            
            full_payload["prompt"][target_node_id]["inputs"]["text"] = str(prompt_content)
        else:
            return {"status": "ERROR", "message": f"Node not found. Prompt keys: {list(prompt_dict.keys()) if isinstance(prompt_dict, dict) else 'not a dict'}"}

        try:
            response = await self.dispatcher.dispatch(full_payload)
            if response["status"] == "success":
                return {"status": "SUCCESS", "data": response["response"]}
            else:
                return {"status": "FAILED", "message": response.get("reason", "unknown error")}
        except Exception as e:
            return {"status": "ERROR", "message": str(e)}

    async def submit_video_to_comfy(self, shot_data: dict, anchor_image_path: str = None) -> dict:
        """
        Submits an image-to-video or text-to-video job using LTX 2.3.
        Supports frame_guidance and motion_strength.
        """
        await self._ensure_connectivity()
        intent = "video_generation" # Default for video
        payload = await self._build_kernel_payload(shot_data, model_hint="ltx_2_3")
        
        # Extract parameters (frame_guidance, motion_strength) from shot_data if present
        motion_strength = shot_data.get("motion_strength", 0.5)
        frame_guidance = shot_data.get("frame_guidance", 0.7)
        
        # We assume the workflow is loaded elsewhere or passed in? 
        # Requirement C4 doesn't specify how to get the video workflow, but says "supporting I2V and T2V".
        # Let's try to load it if not provided.
        workflow = await self.load_workflow("ltx_2_3")
        if not workflow:
            return {"status": "ERROR", "message": "No LTX workflow found"}

        full_payload = {"prompt": workflow}
        # Injecting parameters into the payload for ComfyUI nodes
        # This is highly dependent on node IDs in ltx_2_3.json, 
        # but we'll follow a generic injection pattern.
        for node_id, node_info in full_payload["prompt"].items():
            if "motion_strength" in node_info.get("inputs", {}):
                node_info["inputs"]["motion_strength"] = motion_strength
            if "frame_guidance" in node_info.get("inputs", {}):
                node_info["inputs"]["frame_guidance"] = frame_guidance

        # If I2V (anchor image provided), we'd need to handle the load_image node too.
        if anchor_image_path:
            for node_id, node_info in full_payload["prompt"].items():
                if node_info.get("class_type") == "LoadImage":
                    node_info["inputs"]["image"] = Path(anchor_image_path).name
                    break

        try:
            response = await self.dispatcher.dispatch(full_payload)
            return {"status": "SUCCESS" if response["status"] == "success" else "FAILED", "data": response}
        except Exception as e:
            return {"status": "ERROR", "message": str(e)}
