import os
import json
import re
from datetime import datetime
from hermes_tools import terminal, json_parse

# --- CONFIGURATION ---
COMFYUI_HOST = "localhost"
COMFYUI_PORT = 8188  # Primary GPU (Image Gen)
WORKFLOW_PATH = "/Users/zgbot/Desktop/forge_nps_v01/workflows/flux_redux_api.json"

class FluxReduxGenerator:
    def __init__(self, host=COMFYUI_HOST, port=COMFYUI_PORT):
        self.base_url = f"http://{host}:{port}"

    def upload_image(self, image_path):
        """Uploads an image to ComfyUI and returns the filename."""
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Reference image not found: {image_path}")
        
        # Using curl via terminal for robust upload handling
        filename = os.path.basename(image_path)
        cmd = f"curl -X POST -F 'image=@{image_path}' {self.base_url}/upload/image"
        result = terminal(command=cmd)
        if result['exit_code'] != 0:
            raise Exception(f"Failed to upload image: {result['output']}")
        
        # ComfyUI returns JSON like {"name": "filename.png", "subfolder": "", "type": "input"}
        resp = json_parse(result['output'])
        return resp['name']

    def generate_with_redux(self, project_slug, character_key, prompt_text, output_name, 
                           width=1024, height=576, pose="neutral", view="front", 
                           crop="medium", lighting="natural", bg="white"):
        """
        Generates consistent image using Flux Redux and encodes metadata into filename.
        """
        # 1. Load Reference Image (Head Sheet)
        ref_image_path = f"/Users/zgbot/Desktop/forge_nps_v01/projects/{project_slug}/assets/head_sheet.png"
        uploaded_filename = self.upload_image(ref_image_path)

        # 2. Prepare Workflow
        if not os.path.exists(WORKFLOW_PATH):
            raise FileNotFoundError(f"Workflow template missing: {WORKFLOW_PATH}")
        
        with open(WORKFLOW_PATH, 'r') as f:
            workflow = json.load(f)

        # 3. Inject Parameters (Mapping to standard Flux Redux node indices - MUST VERIFY LATER)
        # Note: These IDs are placeholders for the actual workflow structure
        # Node 6: CLIP Text Encode (Prompt)
        # Node X: Image Input (the uploaded reference)
        workflow["prompt"]["6"]["inputs"]["text"] = prompt_text
        workflow["prompt"]["X"]["inputs"]["image"] = uploaded_filename # Placeholder ID
        workflow["prompt"]["Y"]["inputs"]["width"] = width             # Placeholder ID
        workflow["prompt"]["Z"]["inputs"]["height"] = height           # Placeholder ID

        # 4. Submit Job
        payload = {"prompt": workflow}
        cmd = f"curl -X POST -H 'Content-Type: application/json' -d '{json.dumps(payload)}' {self.base_url}/prompt"
        result = terminal(command=cmd)
        if result['exit_code'] != 0:
            raise Exception(f"Failed to submit prompt: {result['output']}")
        
        resp = json_parse(result['output'])
        prompt_id = resp['prompt_id']

        # 5. Poll for completion
        print(f"Job submitted (ID: {prompt_id}). Polling...")
        output_filename = self._poll_job(prompt_id)

        # 6. Download and Save with Encoded Metadata (Option A)
        # Pattern: {slug}_{char}_{output_name}_{pose}_{view}_{crop}_{lighting}_{bg}.png
        encoded_filename = f"{project_slug}_{character_key}_{output_name}_{pose}_{view}_{crop}_{lighting}_{bg}.png"
        save_path = f"/Users/zgbot/Desktop/forge_nps_v01/projects/{project_slug}/generations/anchors/{encoded_filename}"
        
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        self._download_output(output_filename, save_path)
        
        print(f"Success: Saved to {save_path}")
        return save_path

    def _poll_job(self, prompt_id, timeout_sec=1800):
        """Polls /history/{prompt_id} until complete."""
        import time
        start_time = time.time()
        while (time.time() - start_time) < timeout_sec:
            result = terminal(command=f"curl -s {self.base_url}/history/{prompt_id}")
            if result['exit_code'] == 0:
                data = json_parse(result['output'])
                # If history exists for this prompt_id, it's done
                if str(prompt_id) in data or data:
                    # Extract filename from outputs (simplified)
                    # In real implementation, traverse the JSON to find 'filename'
                    try:
                        return data[str(prompt_id)]['outputs'][0]['images'][0]['filename']
                    except (KeyError, IndexError):
                        raise Exception("Job completed but output metadata not found in history.")
            time.sleep(5)
        raise TimeoutError(f"Job {prompt_id} timed out after {timeout_sec}s")

    def _download_output(self, filename, save_path):
        """Downloads file from /view endpoint."""
        cmd = f"curl -L {self.base_url}/view?filename={filename}&type=output"
        result = terminal(command=cmd)
        if result['exit_code'] != 0:
            raise Exception(f"Failed to download output: {result['output']}")
        
        with open(save_path, 'wb') as f:
            f.write(result['output'].encode('latin-1')) # Note: terminal() returns string, might need raw binary handling via script if file is large/binary

if __name__ == "__main__":
    # Example usage for testing once ComfyUI is live
    gen = FluxReduxGenerator()
    try:
        gen.generate_with_redux(
            project_slug="test-proj",
            character_key="char1",
            prompt_text="a beautiful woman in a sunlit field, cinematic lighting",
            output_name="hero_shot",
            pose="standing",
            view="front",
            crop="medium",
            lighting="golden_hour",
            bg="natural"
        )
    except Exception as e:
        print(f"Error: {e}")
