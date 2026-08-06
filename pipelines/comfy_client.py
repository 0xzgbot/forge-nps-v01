import time
from pathlib import Path
from urllib.parse import urlencode

import httpx

class ComfyClient:
    def __init__(self, host, port):
        self.base_url = f"http://{host}:{port}"

    def check_health(self, host=None, port=None):
        """Returns True/False + system info"""
        try:
            response = httpx.get(f"{self.base_url}/system_stats", timeout=5)
            if response.status_code == 200:
                return True, response.json()
            return False, {"error": f"Status code {response.status_code}"}
        except Exception as e:
            return False, {"error": str(e)}

    def list_models(self, host=None, port=None, loader_type="diffusion_model"):
        """Query /object_info and return model/file choices exposed by ComfyUI."""
        try:
            response = httpx.get(f"{self.base_url}/object_info", timeout=5)
            if response.status_code == 200:
                data = response.json()
                return self._extract_model_choices(data, loader_type=loader_type)
            return []
        except Exception as e:
            print(f"Error listing models: {e}")
            return []

    @staticmethod
    def _extract_model_choices(object_info, loader_type="diffusion_model"):
        """Extract model choices from ComfyUI object_info without assuming one node schema."""
        needles = {
            str(loader_type or "").lower(),
            "model",
            "ckpt",
            "unet",
            "vae",
            "clip",
            "lora",
        }
        extensions = (".safetensors", ".ckpt", ".pt", ".pth", ".gguf")
        found = set()

        def walk(value, path=""):
            if isinstance(value, dict):
                for key, child in value.items():
                    walk(child, f"{path}.{key}" if path else str(key))
                return
            if isinstance(value, list):
                for child in value:
                    walk(child, path)
                return
            if not isinstance(value, str):
                return

            lowered = value.lower()
            path_lowered = path.lower()
            if lowered.endswith(extensions) or any(needle and needle in path_lowered for needle in needles):
                found.add(value)

        walk(object_info)
        return sorted(found, key=str.lower)

    def submit_prompt(self, host=None, port=None, workflow_dict=None):
        """POST to /prompt, returns prompt_id"""
        if isinstance(host, dict) and workflow_dict is None:
            workflow_dict = host
        if workflow_dict is None:
            workflow_dict = {}
        try:
            response = httpx.post(f"{self.base_url}/prompt", json={"prompt": workflow_dict}, timeout=5)
            if response.status_code == 200:
                return response.json().get("prompt_id")
            else:
                print(f"Submission failed: {response.text}")
                return None
        except Exception as e:
            print(f"Error submitting prompt: {e}")
            return None

    def poll_job(self, host=None, port=None, prompt_id=None, timeout_sec=300):
        """Polls /history/{prompt_id} every 5s, returns output filename when done"""
        if isinstance(host, str) and port is None and prompt_id is None:
            prompt_id = host
        if not prompt_id:
            return None
        start_time = time.time()
        while time.time() - start_time < timeout_sec:
            try:
                response = httpx.get(f"{self.base_url}/history/{prompt_id}", timeout=5)
                if response.status_code == 200:
                    data = response.json()
                    if prompt_id in data:
                        # Job complete, extract filenames from outputs
                        outputs = data[prompt_id].get("outputs", {})
                        for node_id, node_output in outputs.items():
                            if "images" in node_output:
                                return node_output["images"][0]["filename"]
                time.sleep(5)
            except Exception as e:
                print(f"Error polling job: {e}")
                time.sleep(5)
        return None

    def download_output(self, host=None, port=None, filename=None, save_path=None):
        """GET /view?filename=X&type=output&subfolder=, saves to disk"""
        if filename is None and save_path is None and isinstance(host, str) and isinstance(port, str):
            filename = host
            save_path = port
        if not filename or not save_path:
            return False
        try:
            query = urlencode({"filename": filename, "type": "output", "subfolder": ""})
            response = httpx.get(f"{self.base_url}/view?{query}", timeout=10)
            if response.status_code == 200:
                Path(save_path).write_bytes(response.content)
                return True
            else:
                print(f"Download failed: Status {response.status_code}")
                return False
        except Exception as e:
            print(f"Error downloading output: {e}")
            return False
