import asyncio
import httpx
import json
import os
import logging
from pathlib import Path

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

    async def submit_prompt(self, workflow_dict: dict) -> str | None:
        """POST to /prompt, returns prompt_id"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/prompt", 
                    json={"prompt": workflow_dict}, 
                    timeout=5.0
                )
                if response.status_code == 200:
                    return response.json().get("prompt_id")
                else:
                    logger.error(f"Submission failed: {response.text}")
                    return None
        except Exception as e:
            logger.error(f"Error submitting prompt: {e}")
            return None

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
                for node_id, node_output in outputs.items():
                    if "images" in node_output:
                        for img_data in node_output["images"]:
                            filename = img_data["filename"]
                            subfolder = img_data.get("subfolder", "")
                            
                            # URL for downloading
                            download_url = f"{self.base_url}/view"
                            params = {
                                "filename": filename,
                                "type": "output",
                                "subfolder": subfolder
                            }

                            resp = await client.get(download_url, params=params, timeout=10.0)
                            if resp.status_code == 200:
                                target_file = output_path / filename
                                with open(target_file, "wb") as f:
                                    f.write(resp.content)
                                saved_files.append(str(target_file))
                            else:
                                logger.error(f"Failed to download {filename}: Status {resp.status_code}")

        except Exception as e:
            logger.error(f"Error in download_outputs: {e}")

        return saved_files
