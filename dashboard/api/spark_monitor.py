"""
Real-Time Spark Monitor for Forge NPS Dashboard.

Polls ComfyUI queue/history server-side and pushes updates
to all connected WebSocket clients.
"""

import asyncio
import json
import time
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field, asdict

import requests

REPO_ROOT = Path(__file__).parent.parent.parent.resolve()
SPARK_HOST = "http://localhost:8188"
POLL_INTERVAL = 2.0


@dataclass
class SparkJob:
    prompt_id: str
    filename: str
    status: str  # "queued" | "running" | "completed" | "failed" | "error"
    progress: float = 0.0  # 0.0 - 1.0
    current_node: str = ""
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    outputs: List[str] = field(default_factory=list)
    recipe: Optional[Dict[str, Any]] = None


class SparkMonitor:
    """Singleton monitor that polls Spark and broadcasts state."""

    def __init__(self, host: str = SPARK_HOST):
        self.host = host.rstrip("/")
        self.jobs: Dict[str, SparkJob] = {}
        self.running = False
        self._task: Optional[asyncio.Task] = None
        self._callbacks: List[Any] = []
        self._last_queue: Dict = {}
        self.spark_alive = False
        self.last_poll_time = 0.0

    def register_callback(self, callback):
        """Register a coroutine callback(job_id, job) for updates."""
        self._callbacks.append(callback)

    def unregister_callback(self, callback):
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    async def _broadcast(self, job_id: str, job: SparkJob):
        payload = {
            "type": "SPARK_UPDATE",
            "job": asdict(job),
            "spark_alive": self.spark_alive,
            "total_jobs": len(self.jobs),
            "completed_jobs": sum(1 for j in self.jobs.values() if j.status == "completed"),
            "running_jobs": sum(1 for j in self.jobs.values() if j.status == "running"),
            "queued_jobs": sum(1 for j in self.jobs.values() if j.status == "queued"),
            "timestamp": time.time(),
        }
        for cb in list(self._callbacks):
            try:
                await cb(payload)
            except Exception:
                pass

    def add_job(self, recipe: Dict[str, Any], prompt_id: str, filename: str):
        """Called when a job is submitted to ComfyUI."""
        job = SparkJob(
            prompt_id=prompt_id,
            filename=filename,
            status="queued",
            recipe=recipe,
            start_time=time.time(),
        )
        self.jobs[prompt_id] = job
        # Fire-and-forget broadcast
        asyncio.create_task(self._broadcast(prompt_id, job))

    async def _poll_once(self):
        """Single poll cycle: queue + history."""
        try:
            # 1. Queue state
            resp = requests.get(f"{self.host}/queue", timeout=5)
            resp.raise_for_status()
            queue_data = resp.json()
            self._last_queue = queue_data
            self.spark_alive = True
            self.last_poll_time = time.time()

            running = queue_data.get("queue_running", [])
            pending = queue_data.get("queue_pending", [])

            # Mark running jobs
            running_ids = {str(r[1]) for r in running if len(r) > 1}
            for pid, job in self.jobs.items():
                if pid in running_ids and job.status == "queued":
                    job.status = "running"
                    job.progress = 0.1
                    await self._broadcast(pid, job)

            # Mark pending jobs
            pending_ids = {str(p[1]) for p in pending if len(p) > 1}
            for pid, job in self.jobs.items():
                if pid in pending_ids and job.status not in ("running", "completed", "failed"):
                    job.status = "queued"
                    await self._broadcast(pid, job)

            # 2. Check history for completed jobs
            for pid in list(self.jobs.keys()):
                if self.jobs[pid].status in ("completed", "failed"):
                    continue
                try:
                    hist_resp = requests.get(f"{self.host}/history/{pid}", timeout=5)
                    if hist_resp.status_code != 200:
                        continue
                    hist = hist_resp.json()
                    if pid not in hist:
                        continue
                    job_data = hist[pid]
                    status = job_data.get("status", {})
                    if status.get("completed"):
                        job = self.jobs[pid]
                        job.status = "completed"
                        job.progress = 1.0
                        job.end_time = time.time()
                        # Extract output filenames
                        outputs = job_data.get("outputs", {})
                        out_files = []
                        for node_id, node_out in outputs.items():
                            if isinstance(node_out, dict):
                                for key in ("images", "gifs", "files"):
                                    if key in node_out:
                                        out_files.extend([f.get("filename", "") for f in node_out[key]])
                        job.outputs = out_files
                        await self._broadcast(pid, job)
                    elif status.get("status_str") == "error":
                        job = self.jobs[pid]
                        job.status = "failed"
                        job.end_time = time.time()
                        await self._broadcast(pid, job)
                except Exception:
                    pass

        except requests.ConnectionError:
            self.spark_alive = False
        except Exception:
            self.spark_alive = False

    async def _loop(self):
        """Background polling loop."""
        while self.running:
            await self._poll_once()
            await asyncio.sleep(POLL_INTERVAL)

    def start(self):
        if not self.running:
            self.running = True
            self._task = asyncio.create_task(self._loop())

    def stop(self):
        self.running = False
        if self._task:
            self._task.cancel()

    def get_state(self) -> Dict[str, Any]:
        """Current snapshot for REST API."""
        return {
            "spark_alive": self.spark_alive,
            "last_poll": self.last_poll_time,
            "jobs": [asdict(j) for j in self.jobs.values()],
            "summary": {
                "total": len(self.jobs),
                "queued": sum(1 for j in self.jobs.values() if j.status == "queued"),
                "running": sum(1 for j in self.jobs.values() if j.status == "running"),
                "completed": sum(1 for j in self.jobs.values() if j.status == "completed"),
                "failed": sum(1 for j in self.jobs.values() if j.status == "failed"),
            },
        }


# Global singleton
monitor = SparkMonitor()
