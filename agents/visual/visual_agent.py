import logging
import json
import asyncio
from typing import Dict, Any, Optional
from pathlib import Path

from core.routing.architect_router import ArchitectRouter
from core.dispatch.dispatcher import ComfyDispatcher
from core.dispatch.comfy_client import ComfyUIClient
from data.character_banks.bank_loader import get_quality_constants

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("VisualAgent")

class VisualAgent:
    def __init__(self, comfyui_url: str):
        self.comfyui_url = comfyui_url.rstrip('/')
        self.router = ArchitectRouter()
        self.dispatcher = ComfyDispatcher([self.comfyui_url])
        # We don't await in __init__, so we might need a setup method or handle it in calls
        # But requirements say "Add a pre-flight call... in the agent's initialization (log warning if offline, don't crash)."
        # Since __init__ cannot be async, we will trigger it as a background task or handle connectivity check on first use.
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
        """
        concept = f"{shot_data.get('visual_prompt', {}).get('subject', '')}, {shot_data.get('visual_prompt', {}).get('action', '')}"
        # Use the intent mapping from router or fallback to model_hint as intent
        # The requirement says: Use ArchitectRouter to get kernel/prompt.
        # We'll assume shot_data might contain an 'intent'. If not, we map it.
        intent = shot_data.get('intent', 'high_fidelity_image') 
        if model_hint in ["z_image_turbo", "flux_2_dev"]: # mapping hint to intent if needed
             # This is a bit fuzzy but following the requirement's logic
             pass

        result = self.router.route(intent, concept)
        
        if result["status"] == "error":
            raise ValueError(f"Routing failed: {result['message']}")
        
        payload = result["payload"]
        prompt_text = result["prompt"]
        
        # Append quality constants
        quality = get_quality_constants()
        
        # Injecting into the payload structure based on typical ComfyUI workflow patterns
        # The requirement implies we are building a payload for the dispatcher.
        # Since different kernels return different structures, we'll normalize them here or 
        # let the router handle it. The ArchitectRouter returns 'payload'.
        
        if "prompt" in payload and isinstance(payload["prompt"], dict):
             # For Flux-style: {"text": "...", "clip_l": "..."}
             for key in payload["prompt"]:
                 if isinstance(payload["prompt"][key], str):
                     payload["prompt"][key] += f", {quality}"
        elif isinstance(payload["prompt"], str):
             # For simple string prompts (Z-Image)
             payload["prompt"] = f"{payload['prompt']}, {quality}"

        return payload

    async def load_workflow(self, kernel: str) -> dict:
        """Loads JSON workflow from ~/Desktop/forge_nps/workflows/."""
        wf_path = Path("~/Desktop/forge_nps/workflows") / f"{kernel}.json"
        if not wf_path.exists():
            # Fallback for testing if specific kernel file isn't there, 
            # though B1 should have copied them.
            logger.warning(f"Workflow {wf_path} not found.")
            return {}
        with open(wf_path, 'r') as f:
            return json.load(f)

    async def submit_to_comfy(self, shot_data: dict, workflow: dict):
        await self._ensure_connectivity()
        payload = await self._build_kernel_payload(shot_data)
        
        # The requirement says "Update 'submit_to_comfy()' to use 'ComfyDispatcher.dispatch()' instead of bare httpx calls."
        # We need to combine the workflow and the prompt-specific payload.
        
        # Standard ComfyUI API expects {"prompt": {node_id: { ... }}}
        # If the provided workflow is already the dict of nodes, we wrap it.
        # If the workflow is already {"prompt": {nodes}}, we use it directly.
        if "prompt" in workflow and isinstance(workflow["prompt"], dict):
            full_payload = workflow
        else:
            full_payload = {"prompt": workflow}
        
        # Inject the generated prompt into the workflow (targeting CLIPTextEncode)
        target_node_id = None
        prompt_dict = full_payload.get("prompt", {})
        if isinstance(prompt_dict, dict):
            for node_id, node_info in prompt_dict.items():
                if isinstance(node_info, dict) and node_info.get("class_type") == "CLIPTextEncode":
                    target_node_id = node_id
                    break
        
        if target_node_id:
            # If payload has a text field (Flux) or is just a string (Z-Image)
            prompt_content = payload.get("prompt", "")
            if isinstance(payload.get("prompt"), dict): # Flux case
                 # The router already returns the 'text' in result['prompt']
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
