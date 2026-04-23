import asyncio
import logging
import json
import os
from pathlib import Path
from typing import List, Dict, Any, Optional

logger = logging.getLogger("ComfyUIIntegration")

class ComfyUIBatchSubmitter:
    """
    J8: ComfyUI API Integration & Submission Layer.
    Handles dual-host load balancing, payload submission, 
    and polling/retrieval for the Forge production pipeline.
    """

    def __init__(self, 
                 hosts: List[str] = ["http://localhost:8188", "http://localhost:8189"],
                 poll_interval: int = 5):
        self.hosts = hosts
        self.poll_interval = poll_interval
        self.active_jobs = []

    async def submit_batch(self, prompt_payloads: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Submits a batch of prompts across available hosts using round-robin distribution.
        Returns a list of results containing status and output paths.
        """
        logger.info(f"Starting submission for {len(prompt_payloads)} payloads.")
        
        # 1. Distribute tasks to host queues
        host_queues = {host: [] for host in self.hosts}
        for i, payload in enumerate(prompt_payloads):
            target_host = self.hosts[i % len(self.hosts)]
            host_queues[target_host].append(payload)

        # 2. Execute parallel submission via sub-tasks (simulated here as asyncio tasks)
        submission_tasks = []
        for host, queue in host_queues.items():
            if queue:
                submission_tasks.append(self._process_host_queue(host, queue))

        results = await asyncio.gather(*submission_tasks)
        # Flatten results list of lists
        flattened_results = [item for sublist in results for item in sublist]
        
        logger.info(f"Batch submission complete. {len(flattened_results)} jobs processed.")
        return flattened_results

    async def _process_host_queue(self, host: str, queue: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Processes all payloads assigned to a specific host."""
        host_results = []
        for payload in queue:
            try:
                # In real implementation, this calls the ComfyUI /prompt endpoint
                # We simulate the async lifecycle: Submit -> Poll -> Download
                result = await self._execute_lifecycle(host, payload)
                host_results.append({"status": "success", "payload_id": payload['id'], **result})
            except Exception as e:
                logger.error(f"Failed to process {payload['id']} on {host}: {e}")
                host_results.append({"status": "failed", "payload_id": payload['id'], "error": str(e)})
        return host_results

    async def _execute_lifecycle(self, host: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Simulates the full lifecycle of a single ComfyUI job."""
        # 1. Submit (simulated)
        logger.info(f"[{host}] Submitting {payload['id']}...")
        await asyncio.sleep(0.5) # Simulate network latency
        prompt_id = f"mock_pid_{payload['id']}"

        # 2. Poll (simulated)
        logger.info(f"[{host}] Polling for {prompt_id}...")
        await asyncio.sleep(1.0) # Simulate generation time

        # 3. Download/Save (simulated)
        output_filename = f"{payload['id']}.png"
        output_path = f"~/Desktop/forge_nps_v01/outputs/{output_filename}"
        
        return {
            "prompt_id": prompt_id,
            "output_file": output_filename,
            "local_path": output_path
        }

# --- UNIT TEST ---
if __name__ == "__main__":
    async def test():
        logging.basicConfig(level=logging.INFO)
        submitter = ComfyUIBatchSubmitter()
        
        mock_payloads = [
            {"id": "shot_01", "base_prompt": "a cat"},
            {"id": "shot_02", "base_prompt": "a dog"},
            {"id": "shot_03", "base_prompt": "a bird"},
        ]
        
        results = await submitter.submit_batch(mock_payloads)
        print("\n--- TEST RESULTS ---")
        for r in results:
            print(r)

    asyncio.run(test())
