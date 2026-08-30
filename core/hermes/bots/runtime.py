"""Spin Hermes Bots via their canonical Bot Chat (same transport as Hermes Bot Mode)."""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.bridge.llm_endpoint import resolve_llm_endpoint
from core.cinesmith_env import cinesmith_hermes_cli_argv, hermes_isolated_env, repo_root
from core.hermes.bots.crew import BOT_CHAT_TITLE, CREW_GROUP
from core.hermes.bots.store import BotStore

_MENTION_RE = re.compile(r"@([a-zA-Z0-9][a-zA-Z0-9_-]{0,63})")


class BotRuntime:
    def __init__(self, root: Optional[Path] = None, store: Optional[BotStore] = None) -> None:
        self.root = root or repo_root()
        self.store = store or BotStore(self.root)
        self.state_dir = self.root / "data" / "bots"
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def chat_argv(
        self,
        profile: str,
        query_file: Path,
        *,
        title: str = BOT_CHAT_TITLE,
        model: str = "",
    ) -> List[str]:
        args = [
            "-p",
            profile,
            "chat",
            "-c",
            title,
            "--create-if-missing",
            "-Q",
            "--query-file",
            str(query_file),
        ]
        if model:
            args.extend(["--model", model])
        args.extend(["--provider", "custom"])
        return cinesmith_hermes_cli_argv(*args, root=self.root)

    def isolated_env(self, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        llm = resolve_llm_endpoint()
        payload = {
            "OPENAI_BASE_URL": llm.base_url,
            "CUSTOM_BASE_URL": llm.base_url,
            "OPENAI_API_KEY": llm.api_key or "not-needed",
            "CUSTOM_API_KEY": llm.api_key or "not-needed",
            "CINESMITH_API": os.getenv("CINESMITH_API", "http://127.0.0.1:7000"),
        }
        if extra:
            payload.update(extra)
        return hermes_isolated_env(extra=payload, root=self.root)

    async def send(
        self,
        profile: str,
        message: str,
        *,
        job_id: str = "",
        title: str = BOT_CHAT_TITLE,
        produce_dir: str = "",
    ) -> Dict[str, Any]:
        """One turn in the bot's canonical chat. Returns stdout reply."""
        brief = (message or "").strip()
        if not brief:
            raise ValueError("message required")
        name = profile.strip()
        if not self.store.profile_dir(name).is_dir():
            self.store.ensure_crew()
        if not self.store.profile_dir(name).is_dir():
            raise FileNotFoundError(name)
        llm = resolve_llm_endpoint()
        if not llm.ready:
            raise RuntimeError("Connect a language model first.")
        extra: Dict[str, str] = {}
        job_dir = Path(produce_dir) if produce_dir else None
        if job_id and job_dir is None:
            candidate = self.root / "data" / "produce" / job_id
            if candidate.is_dir():
                job_dir = candidate
        if job_dir and job_dir.is_dir():
            extra["CINESMITH_PRODUCE_DIR"] = str(job_dir)
            from core.hermes.produce import desk as produce_desk

            ctx = produce_desk.compose_bot_context(job_dir, name)
            if ctx:
                brief = ctx + "\n\nUser:\n" + brief
        self.store.append_chat(name, "user", brief, job_id=job_id)
        query_dir = self.state_dir / "inbox"
        query_dir.mkdir(parents=True, exist_ok=True)
        query_file = query_dir / f"{name}-{int(time.time() * 1000)}.txt"
        query_file.write_text(brief, encoding="utf-8")
        cmd = self.chat_argv(name, query_file, title=title, model=llm.model or "")
        env = self.isolated_env(extra)
        log_path = self.store.profile_dir(name) / "cinesmith-bot.log"
        try:
            with log_path.open("ab") as handle:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    cwd=str(self.root),
                    env=env,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=handle,
                )
            self._track(name, proc.pid, job_id=job_id, title=title)
            stdout_b, _ = await proc.communicate()
            reply = (stdout_b or b"").decode("utf-8", errors="replace").strip()
            self._untrack(name, proc.pid)
            if proc.returncode not in (0, None) and not reply:
                reply = f"(Hermes exited {proc.returncode}. See {log_path.name}.)"
            self.store.append_chat(name, "bot", reply, job_id=job_id)
            if job_dir and job_dir.is_dir():
                from core.hermes.produce import desk as produce_desk

                produce_desk.mark_handoffs_sent(job_dir, name)
            return {
                "name": name,
                "title": title,
                "reply": reply,
                "exit_code": proc.returncode,
                "pid": proc.pid,
            }
        finally:
            try:
                query_file.unlink(missing_ok=True)
            except OSError:
                pass

    async def mention_or_send(self, speaker: str, message: str, *, job_id: str = "") -> Dict[str, Any]:
        """If the message @mentions another bot, deliver there; else talk to speaker."""
        mentions = parse_mentions(message)
        roster = {row["name"] for row in self.store.list_roster(include_hidden=True)}
        targets = [m for m in mentions if m in roster and m != speaker]
        if targets:
            results = []
            for target in targets[:3]:
                composed = (
                    f"Message from @{speaker}. The user pointed this at you:\n\n{message}"
                )
                results.append(await self.send(target, composed, job_id=job_id))
            return {"routed": True, "targets": targets, "results": results}
        return {"routed": False, "targets": [speaker], "results": [await self.send(speaker, message, job_id=job_id)]}

    async def group_round(
        self,
        message: str,
        *,
        group: str = CREW_GROUP,
        members: Optional[List[str]] = None,
        job_id: str = "",
        produce_dir: str = "",
    ) -> Dict[str, Any]:
        """Serial member turns — same caps as Hermes Bot Mode groups (3 rounds, 10 msgs)."""
        roster = self.store.list_roster()
        mentioned = parse_mentions(message)
        if members:
            names = [m for m in members if any(r["name"] == m for r in roster)]
        elif mentioned:
            names = [m for m in mentioned if any(r["name"] == m for r in roster)]
        else:
            names = [r["name"] for r in roster if not r.get("support") and not r.get("hidden")]
        if not names:
            names = [r["name"] for r in roster[:3]]
        room = self._group_path(group)
        self._append_group(room, "user", message)
        turns = []
        remaining = 10
        for _round in range(3):
            spoke = False
            for name in names:
                if remaining <= 0:
                    break
                prompt = (
                    f"You are in group chat `{group}` with {', '.join('@' + n for n in names)}.\n"
                    f"User: {message}\n"
                    "Reply only if you have something new. Otherwise reply PASS."
                )
                result = await self.send(
                    name,
                    prompt,
                    job_id=job_id,
                    title=f"Group: {group}",
                    produce_dir=produce_dir,
                )
                remaining -= 1
                text = (result.get("reply") or "").strip()
                if text.upper() == "PASS" or not text:
                    continue
                spoke = True
                self._append_group(room, name, text)
                turns.append(result)
            if not spoke:
                break
        return {"group": group, "members": names, "turns": turns, "messages": self.read_group(group)}

    def running(self) -> List[Dict[str, Any]]:
        rows = self._load_running()
        live = []
        changed = False
        for row in rows:
            pid = int(row.get("pid") or 0)
            if pid and _pid_alive(pid):
                live.append(row)
            else:
                changed = True
        if changed:
            self._save_running(live)
        return live

    def active_names(self) -> List[str]:
        now = time.time()
        names = {str(r.get("name") or "") for r in self.running() if r.get("name")}
        for row in self.store.list_roster(include_hidden=True):
            last = float(row.get("last_active") or 0)
            if last and (now - last) < 90:
                names.add(row["name"])
        return sorted(n for n in names if n)

    def read_group(self, group: str = CREW_GROUP) -> List[Dict[str, Any]]:
        path = self._group_path(group)
        if not path.is_file():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return []
        msgs = data.get("messages") if isinstance(data, dict) else None
        return msgs if isinstance(msgs, list) else []

    def _track(self, name: str, pid: int, *, job_id: str = "", title: str = "") -> None:
        rows = self.running()
        rows.append(
            {
                "name": name,
                "pid": pid,
                "job_id": job_id,
                "title": title,
                "started_at": time.time(),
            }
        )
        self._save_running(rows)

    def _untrack(self, name: str, pid: int) -> None:
        rows = [r for r in self._load_running() if not (r.get("name") == name and r.get("pid") == pid)]
        self._save_running(rows)

    def _load_running(self) -> List[Dict[str, Any]]:
        path = self.state_dir / "running.json"
        if not path.is_file():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _save_running(self, rows: List[Dict[str, Any]]) -> None:
        (self.state_dir / "running.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")

    def _group_path(self, group: str) -> Path:
        safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in group) or "crew"
        path = self.home_groups() / f"{safe}.json"
        return path

    def home_groups(self) -> Path:
        path = self.store.home / "groups"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _append_group(self, path: Path, role: str, text: str) -> None:
        data: Dict[str, Any] = {"messages": []}
        if path.is_file():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict) and isinstance(loaded.get("messages"), list):
                    data = loaded
            except Exception:
                pass
        data["messages"].append({"ts": time.time(), "role": role, "text": (text or "")[:8000]})
        data["messages"] = data["messages"][-80:]
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def parse_mentions(text: str) -> List[str]:
    found = []
    for match in _MENTION_RE.finditer(text or ""):
        name = match.group(1).lower()
        if name == "user":
            continue
        if name not in found:
            found.append(name)
    return found


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False
