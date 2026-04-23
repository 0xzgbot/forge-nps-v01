import requests
import time
import json
import os

class ComfyClient:
    def __init__(self, host, port):
        self.base_url = f"http://{host}:{port}"

    def check_health(self, host, port):
        """Returns True/False + system info"""
        try:
            response = requests.get(f"{self.base_url}/api/system_stats", timeout=5)
            if response.status_code == 200:
                return True, response.json()
            return False, {"error": f"Status code {response.status_code}"}
        except Exception as e:
            return False, {"error": str(e)}

    def list_models(self, host, port, loader_type="diffusion_model"):
        """Queries /object_info/{loader}, returns model list"""
        try:
            # Note: The specific endpoint for models can vary by ComfyUI version/setup. 
            # Usually checking /object_info or searching the output of it is required.
            response = requests.get(f"{self.base_url}/object_info", timeout=5)
            if response.status_code == 200:
                data = response.json()
                # Filter for models that look like loaders or specific model types
                models = []
                for key, val in data.items():
                    if loader_type in str(val).lower():
                        models.append(key)
                return models
            return []
        except Exception as e:
            print(f"Error listing models: {e}")
            return []

    def submit_prompt(self, host, port, workflow_dict):
        """POST to /prompt, returns prompt_id"""
        try:
            response = requests.post(f"{self.base_url}/prompt", json={"prompt": workflow_dict}, timeout=5)
            if response.status_code == 200:
                return response.json().get("prompt_id")
            else:
                print(f"Submission failed: {response.text}")
                return None
        except Exception as e:
            print(f"Error submitting prompt: {e}")
            return None

    def poll_job(self, host, port, prompt_id, timeout_sec=300):
        """Polls /history/{prompt_id} every 5s, returns output filename when done"""
        start_time = time.time()
        while time.time() - start_time < timeout_sec:
            try:
                response = requests.get(f"{self.base_url}/history/{prompt_id}", timeout=5)
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

    def download_output(self, host, port, filename, save_path):
        """GET /view?filename=X&type=output&subfolder=, saves to disk"""
        try:
            url = f"{self.base_url}/view?filename={filename}&type=output&subfolder="
            response = requests.get(url, stream=True, timeout=10)
            if response.status_code == 200:
                with open(save_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                return True
            else:
                print(f"Download failed: Status {response.status_code}")
                return False
        except Exception as e:
            print(f"Error downloading output: {e}")
            return False
