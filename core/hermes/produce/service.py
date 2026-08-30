"""Hermes-led produce jobs: the agent expands a prompt and writes artifacts.

This is not a fixed stage machine. Hermes runs with tools and skills and
decides what to write next. The UI only watches the job directory.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from core.bridge.llm_endpoint import resolve_llm_endpoint
from core.cinesmith_env import hermes_isolated_env, repo_root
from core.hermes.bots.crew import CREW_BY_KEY
from core.hermes.bots.runtime import BotRuntime
from core.hermes.bots.store import BotStore
from core.hermes.produce import queue as produce_queue
from core.hermes.produce import render as produce_render

STAGES = ("story", "script", "storyboard", "video", "edit", "done", "blocked")


class ProduceService:
    def __init__(self, root: Optional[Path] = None) -> None:
        self.root = root or repo_root()
        self.jobs_dir = self.root / "data" / "produce"
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.bots = BotStore(self.root)
        self.runtime = BotRuntime(self.root, store=self.bots)

    def job_dir(self, job_id: str) -> Path:
        return self.jobs_dir / job_id

    def start(self, prompt: str, profile: str = "producer", produce_mode: str = "shoot") -> Dict[str, Any]:
        brief = (prompt or "").strip()
        if not brief:
            raise ValueError("prompt required")
        self.bots.ensure_crew()
        lead = (profile or "producer").strip() or "producer"
        if not self.bots.profile_dir(lead).is_dir():
            raise ValueError(f"unknown profile: {lead}")
        job_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
        path = self.job_dir(job_id)
        path.mkdir(parents=True, exist_ok=True)
        (path / "prompt.md").write_text(brief + "\n", encoding="utf-8")
        (path / "STATUS.md").write_text(
            f"story — @{lead} is reading the brief.\n", encoding="utf-8"
        )
        meta = {
            "job_id": job_id,
            "prompt": brief,
            "created_at": time.time(),
            "status": "running",
            "pid": None,
            "profile": lead,
            "produce_mode": "scout" if str(produce_mode or "").strip().lower() == "scout" else "shoot",
            "bots": [],
        }
        self._write_meta(path, meta)
        return self.snapshot(job_id)

    def snapshot(self, job_id: str) -> Dict[str, Any]:
        path = self.job_dir(job_id)
        if not path.exists():
            raise FileNotFoundError(job_id)
        meta = self._read_meta(path)
        files = {}
        for name in ("prompt.md", "story.md", "script.md", "shots.json", "storyboard.md", "edit.json", "STATUS.md", "characters.md", "product.md", "queue.json"):
            target = path / name
            if target.exists():
                files[name] = target.read_text(encoding="utf-8")[:20000]
        media = produce_render.list_media(path)
        clips = media["clips"]
        stills = media["stills"]
        shots = produce_render.load_shots(path)
        edit = produce_render.load_edit(path)
        queue = produce_queue.load_queue(path)
        stage = self._stage_from_status(files.get("STATUS.md", ""))
        if (path / "cut.mp4").exists():
            stage = "done" if stage != "blocked" else stage
        elif files.get("edit.json") and clips:
            stage = "edit" if stage not in {"done", "blocked"} else stage
        elif clips:
            if stage in {"story", "script", "storyboard"}:
                stage = "video"
        elif files.get("storyboard.md") or files.get("shots.json"):
            if stage in {"story", "script"}:
                stage = "storyboard"
        elif files.get("script.md") and stage == "story":
            stage = "script"
        return {
            "job_id": job_id,
            "status": meta.get("status") or "running",
            "stage": stage,
            "prompt": meta.get("prompt") or files.get("prompt.md", "").strip(),
            "files": files,
            "clips": clips,
            "stills": stills,
            "shots": shots,
            "edit": edit,
            "queue": queue,
            "queue_eta_sec": produce_queue.queue_eta_sec(queue),
            "produce_mode": produce_render.produce_mode(path),
            "color_pass": bool(produce_render.load_job_meta(path).get("color_pass")),
            "identity": produce_render.list_identity(path),
            "cut": "cut.mp4" if (path / "cut.mp4").exists() else "",
            "error": meta.get("error") or "",
            "llm": meta.get("llm") or {},
            "profile": meta.get("profile") or "producer",
            "bots": meta.get("bots") or [],
            "active": self.runtime.active_names(),
        }

    def list_jobs(self) -> list[Dict[str, Any]]:
        rows = []
        for child in sorted(self.jobs_dir.iterdir(), reverse=True):
            if not child.is_dir() or not (child / "job.json").exists():
                continue
            snap = self.snapshot(child.name)
            rows.append(
                {
                    "job_id": snap["job_id"],
                    "status": snap["status"],
                    "stage": snap["stage"],
                    "prompt": (snap["prompt"] or "")[:160],
                }
            )
        return rows[:40]

    async def _run_hermes(self, job_id: str, brief: str) -> None:
        path = self.job_dir(job_id)
        llm = resolve_llm_endpoint()
        meta = self._read_meta(path)
        meta["llm"] = {"source": llm.source, "model": llm.model, "base_url": llm.base_url}
        self._write_meta(path, meta)
        if not llm.ready:
            meta["status"] = "blocked"
            meta["error"] = "Connect a language model in Settings (local or any OpenAI-compatible endpoint)."
            self._write_meta(path, meta)
            (path / "STATUS.md").write_text("blocked — no language model connected.\n", encoding="utf-8")
            return

        lead = str(meta.get("profile") or "producer")
        instruction = self._agent_prompt(brief, path, lead, produce_mode=produce_render.produce_mode(path))
        query = path / "query.txt"
        query.write_text(instruction, encoding="utf-8")
        env = hermes_isolated_env(
            extra={
                "CINESMITH_PRODUCE_DIR": str(path),
                "CINESMITH_API": os.getenv("CINESMITH_API", "http://127.0.0.1:7000"),
                "OPENAI_BASE_URL": llm.base_url,
                "CUSTOM_BASE_URL": llm.base_url,
                "OPENAI_API_KEY": llm.api_key or "not-needed",
                "CUSTOM_API_KEY": llm.api_key or "not-needed",
            },
            root=self.root,
        )
        cmd = self.runtime.chat_argv(lead, query, model=llm.model or "")
        log = path / "hermes.log"
        stop = asyncio.Event()
        drain_task = asyncio.create_task(self._queue_watch(job_id, stop))
        try:
            with log.open("ab") as handle:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    cwd=str(self.root),
                    env=env,
                    stdout=handle,
                    stderr=handle,
                )
            meta["pid"] = proc.pid
            meta["bots"] = [{"name": lead, "pid": proc.pid, "title": "Bot Chat"}]
            self._write_meta(path, meta)
            self.runtime._track(lead, proc.pid, job_id=job_id, title="Bot Chat")
            code = await proc.wait()
            self.runtime._untrack(lead, proc.pid)
            try:
                await produce_queue.drain_pending(path)
            except Exception:
                pass
            meta = self._read_meta(path)
            if code != 0 and meta.get("status") != "blocked":
                meta["status"] = "blocked"
                meta["error"] = f"@{lead} exited {code}. See hermes.log."
                (path / "STATUS.md").write_text(
                    f"blocked — @{lead} exited {code}.\n", encoding="utf-8"
                )
            else:
                meta["status"] = "done" if (path / "story.md").exists() else meta.get("status") or "done"
            self._write_meta(path, meta)
        except Exception as exc:
            meta = self._read_meta(path)
            meta["status"] = "blocked"
            meta["error"] = str(exc)
            self._write_meta(path, meta)
            (path / "STATUS.md").write_text(f"blocked — {exc}\n", encoding="utf-8")
        finally:
            stop.set()
            try:
                await drain_task
            except Exception:
                pass

    async def _queue_watch(self, job_id: str, done: asyncio.Event) -> None:
        path = self.job_dir(job_id)
        while not done.is_set():
            try:
                await produce_queue.drain_pending(path)
            except Exception:
                pass
            try:
                await asyncio.wait_for(done.wait(), timeout=3.0)
            except asyncio.TimeoutError:
                continue

    def _agent_prompt(self, brief: str, path: Path, lead: str = "producer", produce_mode: str = "shoot") -> str:
        role = CREW_BY_KEY.get(lead, {})
        artifact = role.get("artifact") or "the job files"
        mates = ", ".join(f"@{k}" for k in CREW_BY_KEY if k != lead)
        grammar = (
            "Scout mode: no boards. Queue render_take with mode t2va."
            if produce_mode == "scout"
            else "Shoot mode: queue render_board on the 3090s, then render_take. Use fl2va when a shot has end_still, else i2va. r2va when identity refs exist."
        )
        return (
            f"You are @{lead} in a Hermes Bot Chat. This is your canonical forever-chat.\n"
            "Use message_agent to hand work to teammates when they should do the job.\n"
            f"Teammates: {mates}\n\n"
            "The user asked for a video from this prompt:\n\n"
            f"{brief}\n\n"
            f"Job directory (already created): {path}\n"
            f"Produce mode: {produce_mode}. {grammar}\n"
            f"Your usual artifact is {artifact}. The producer keeps STATUS.md honest.\n"
            "Write real files. Prefer appending GPU work to queue.json over hoping a curl lands:\n"
            "  queue.json = {items:[{id, action, shot_id, mode, status: pending}]}\n"
            "  actions: render_board | render_take | assemble\n"
            "A worker drains queue.json when hosts are up. If Spark/3090s are down, items stay "
            "pending (waiting_for_host). Never mark done without a file on disk.\n"
            "You may also POST $CINESMITH_API:\n"
            f"  /api/produce/{path.name}/queue        {{action, shot_id, mode}}\n"
            f"  /api/produce/{path.name}/queue/plan\n"
            f"  /api/produce/{path.name}/queue/run\n"
            "Comfy presets live in workflows/ — inject the shot prompt, do not invent a new graph.\n"
            "If hosts stay down, stop at the last real file and mark STATUS blocked. "
            "Adapt. Do not run a fake checklist."
        )

    def _write_meta(self, path: Path, meta: Dict[str, Any]) -> None:
        (path / "job.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    def _read_meta(self, path: Path) -> Dict[str, Any]:
        target = path / "job.json"
        if not target.exists():
            return {}
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _stage_from_status(text: str) -> str:
        first = (text or "").strip().splitlines()[0] if text else ""
        token = first.split("—")[0].split("-")[0].strip().lower()
        if token in STAGES:
            return token
        return "story"
