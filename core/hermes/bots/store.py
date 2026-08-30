"""Hermes Bot profiles on disk — roster, SOUL, hide, chat log."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.cinesmith_env import cinesmith_hermes_home, repo_root
from core.hermes.bots.crew import (
    ACTIVE_WINDOW_SEC,
    CREW,
    CREW_BY_KEY,
    CREW_GROUP,
    CREW_MARKER,
    LEGACY_HIDDEN,
    crew_keys,
    skill_markdown,
    soul_for,
)

_CONFIG_SNIPPET = """model:
  default: ""
  provider: custom
  base_url: ""
providers: {}
fallback_providers: []
toolsets:
- hermes-cli
agent:
  max_turns: 80
  gateway_timeout: 1800
  bot_mode_protocol: true
terminal:
  backend: local
  modal_mode: auto
  cwd: .
  timeout: 180
  auto_source_bashrc: true
"""


def _yaml_load(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        import yaml

        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _yaml_dump(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import yaml

        path.write_text(
            yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
    except Exception:
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")


class BotStore:
    def __init__(self, root: Optional[Path] = None) -> None:
        self.root = root or repo_root()
        self.home = cinesmith_hermes_home(self.root)
        self.profiles_dir = self.home / "profiles"

    def profile_dir(self, name: str) -> Path:
        return self.profiles_dir / name

    def ensure_crew(self) -> List[str]:
        """Create or refresh task-aligned Bot profiles. Idempotent."""
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        self._write_shared_skills()
        created = []
        for row in CREW:
            key = str(row["key"])
            self._ensure_bot(key, row, hidden=False)
            created.append(key)
        for name in LEGACY_HIDDEN:
            path = self.profile_dir(name)
            if path.is_dir():
                self._ensure_legacy_hidden(name)
        return created

    def list_roster(self, *, include_hidden: bool = False) -> List[Dict[str, Any]]:
        self.ensure_crew()
        rows: List[Dict[str, Any]] = []
        if not self.profiles_dir.is_dir():
            return rows
        seen = set()
        for child in sorted(self.profiles_dir.iterdir()):
            if not child.is_dir():
                continue
            row = self._row_from_dir(child)
            if not row:
                continue
            if row.get("hidden") and not include_hidden:
                continue
            rows.append(row)
            seen.add(row["name"])
        # Crew first, in task order, then extras.
        order = {k: i for i, k in enumerate(crew_keys())}
        rows.sort(key=lambda r: (0 if r["name"] in order else 1, order.get(r["name"], 99), r["name"]))
        return rows

    def get(self, name: str) -> Dict[str, Any]:
        path = self.profile_dir(name)
        if not path.is_dir():
            raise FileNotFoundError(name)
        row = self._row_from_dir(path)
        if not row:
            raise FileNotFoundError(name)
        row["soul"] = self.read_soul(name)
        row["routines"] = self.list_routines(name)
        row["chat"] = self.read_chat(name, limit=40)
        return row

    def read_soul(self, name: str) -> str:
        path = self.profile_dir(name) / "SOUL.md"
        if not path.is_file():
            return ""
        return path.read_text(encoding="utf-8")

    def write_soul(self, name: str, text: str) -> None:
        path = self.profile_dir(name)
        if not path.is_dir():
            raise FileNotFoundError(name)
        (path / "SOUL.md").write_text(text.strip() + "\n", encoding="utf-8")

    def set_hidden(self, name: str, hidden: bool) -> Dict[str, Any]:
        path = self.profile_dir(name)
        if not path.is_dir():
            raise FileNotFoundError(name)
        meta = _yaml_load(path / "profile.yaml")
        ui = meta.setdefault("ui_meta", {})
        if not isinstance(ui, dict):
            ui = {}
            meta["ui_meta"] = ui
        bots = ui.setdefault("hermes-bots", {})
        if not isinstance(bots, dict):
            bots = {}
            ui["hermes-bots"] = bots
        bots["hidden"] = bool(hidden)
        _yaml_dump(path / "profile.yaml", meta)
        return self._row_from_dir(path)

    def create_bot(
        self,
        name: str,
        *,
        title: str = "",
        description: str = "",
        soul: str = "",
        clone_from: str = "",
    ) -> Dict[str, Any]:
        key = _safe_name(name)
        dest = self.profile_dir(key)
        if dest.exists():
            raise FileExistsError(key)
        row = {
            "key": key,
            "title": title.strip() or key.replace("-", " ").title(),
            "task": key,
            "artifact": "",
            "description": description.strip() or f"Custom bot {key}.",
            "color": "#6b6964",
            "skills": [],
            "support": True,
        }
        if clone_from:
            src = self.profile_dir(_safe_name(clone_from))
            if not src.is_dir():
                raise FileNotFoundError(clone_from)
            dest.mkdir(parents=True, exist_ok=True)
            for fname in ("config.yaml", "SOUL.md"):
                src_file = src / fname
                if src_file.is_file():
                    (dest / fname).write_text(src_file.read_text(encoding="utf-8"), encoding="utf-8")
        self._ensure_bot(key, row, hidden=False)
        if soul.strip():
            self.write_soul(key, soul)
        return self.get(key)

    def delete_bot(self, name: str) -> None:
        key = _safe_name(name)
        if key in CREW_BY_KEY:
            raise ValueError("crew bots cannot be deleted; hide them instead")
        path = self.profile_dir(key)
        if not path.is_dir():
            raise FileNotFoundError(key)
        import shutil

        shutil.rmtree(path)

    def append_chat(self, name: str, role: str, text: str, *, job_id: str = "") -> None:
        path = self.profile_dir(name)
        path.mkdir(parents=True, exist_ok=True)
        line = {
            "ts": time.time(),
            "role": role,
            "text": (text or "")[:16000],
            "job_id": job_id,
        }
        with (path / "bot_chat.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(line, ensure_ascii=False) + "\n")

    def read_chat(self, name: str, limit: int = 40) -> List[Dict[str, Any]]:
        path = self.profile_dir(name) / "bot_chat.jsonl"
        if not path.is_file():
            return []
        lines = path.read_text(encoding="utf-8").splitlines()
        out = []
        for raw in lines[-limit:]:
            try:
                row = json.loads(raw)
            except Exception:
                continue
            if isinstance(row, dict):
                out.append(row)
        return out

    def last_active(self, name: str) -> float:
        path = self.profile_dir(name) / "bot_chat.jsonl"
        try:
            return path.stat().st_mtime
        except OSError:
            return 0.0

    def list_routines(self, name: str) -> List[Dict[str, Any]]:
        from core.hermes.bots.routines import list_routines

        return list_routines(self.profile_dir(name), name)

    def _row_from_dir(self, path: Path) -> Optional[Dict[str, Any]]:
        meta = _yaml_load(path / "profile.yaml")
        ui = meta.get("ui_meta") if isinstance(meta.get("ui_meta"), dict) else {}
        bots = ui.get("hermes-bots") if isinstance(ui.get("hermes-bots"), dict) else {}
        if not bots and path.name not in CREW_BY_KEY:
            return None
        crew = CREW_BY_KEY.get(path.name, {})
        title = str(bots.get("title") or crew.get("title") or path.name)
        description = str(
            bots.get("description") or meta.get("description") or crew.get("description") or ""
        )
        hidden = bool(bots.get("hidden", False))
        groups = bots.get("groups") if isinstance(bots.get("groups"), list) else [CREW_GROUP]
        last = self.last_active(path.name)
        return {
            "name": path.name,
            "title": title,
            "description": description,
            "task": crew.get("task") or path.name,
            "artifact": crew.get("artifact") or "",
            "color": bots.get("color") or crew.get("color") or "#6b6964",
            "hidden": hidden,
            "groups": [str(g) for g in groups],
            "support": bool(crew.get("support", True)),
            "crew": path.name in CREW_BY_KEY,
            "last_active": last,
            "active": (time.time() - last) < ACTIVE_WINDOW_SEC if last else False,
            "handle": f"@{path.name}",
        }

    def _ensure_bot(self, key: str, row: Dict[str, object], *, hidden: bool) -> None:
        path = self.profile_dir(key)
        path.mkdir(parents=True, exist_ok=True)
        soul_path = path / "SOUL.md"
        if not soul_path.is_file() or _should_replace_soul(soul_path, key):
            soul_path.write_text(soul_for(key), encoding="utf-8")
        cfg_path = path / "config.yaml"
        if not cfg_path.is_file():
            cfg_path.write_text(_CONFIG_SNIPPET, encoding="utf-8")
        else:
            _ensure_bot_mode_protocol(cfg_path)
        self._link_skills(path)
        meta = _yaml_load(path / "profile.yaml")
        meta["description"] = str(row.get("description") or meta.get("description") or "")
        meta["display_name"] = str(row.get("title") or meta.get("display_name") or key)
        ui = meta.setdefault("ui_meta", {})
        if not isinstance(ui, dict):
            ui = {}
            meta["ui_meta"] = ui
        bots = ui.setdefault("hermes-bots", {})
        if not isinstance(bots, dict):
            bots = {}
            ui["hermes-bots"] = bots
        bots.setdefault("title", str(row.get("title") or key))
        bots.setdefault("description", str(row.get("description") or ""))
        bots.setdefault("color", str(row.get("color") or "#6b6964"))
        bots.setdefault("groups", [CREW_GROUP])
        bots.setdefault("created", int(time.time() * 1000))
        bots["hidden"] = bool(bots.get("hidden", hidden))
        _yaml_dump(path / "profile.yaml", meta)

    def _ensure_legacy_hidden(self, name: str) -> None:
        path = self.profile_dir(name)
        meta = _yaml_load(path / "profile.yaml")
        ui = meta.setdefault("ui_meta", {})
        if not isinstance(ui, dict):
            ui = {}
            meta["ui_meta"] = ui
        bots = ui.setdefault("hermes-bots", {})
        if not isinstance(bots, dict):
            bots = {}
            ui["hermes-bots"] = bots
        bots.setdefault("title", name.replace("_", " ").title())
        bots.setdefault("description", "Legacy pipeline profile. Hidden from the crew roster.")
        bots["hidden"] = True
        if "description" not in meta:
            meta["description"] = bots["description"]
        _yaml_dump(path / "profile.yaml", meta)

    def _link_skills(self, path: Path) -> None:
        skills = path / "skills"
        shared = self.home / "skills"
        if skills.exists() or not shared.is_dir():
            return
        try:
            os.symlink(os.path.relpath(shared, path), skills, target_is_directory=True)
        except OSError:
            pass

    def _write_shared_skills(self) -> None:
        skills_root = self.home / "skills"
        skills_root.mkdir(parents=True, exist_ok=True)
        texts = {
            "story": "Expand the prompt into `story.md`. Specific world, characters, tone, ending.",
            "script": "Write `script.md` from the story. Scenes, action, dialogue, duration.",
            "storyboard": "Write `shots.json` and `storyboard.md`. Panels tied to shot ids.",
            "video": "Render clips when Spark is up. Never invent filenames.",
            "editor": "Write `edit.json` listing only clips that exist.",
            "character": "Write `characters.md` with locked visual DNA.",
        }
        for key, body in texts.items():
            row = CREW_BY_KEY.get(key, {})
            folder = skills_root / f"cinesmith-{key}"
            folder.mkdir(parents=True, exist_ok=True)
            skill = folder / "SKILL.md"
            if skill.exists():
                continue
            skill.write_text(
                skill_markdown(key, str(row.get("title") or key), str(row.get("artifact") or ""), body),
                encoding="utf-8",
            )


def _safe_name(name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in (name or "").strip().lower())
    cleaned = cleaned.strip("-_") or ""
    if not cleaned or not cleaned[0].isalnum():
        raise ValueError("invalid bot name")
    return cleaned[:64]


def _should_replace_soul(path: Path, key: str) -> bool:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return True
    if f"{CREW_MARKER}{key}" in text:
        return False
    # Legacy Kimi / campaign souls get replaced once.
    lowered = text.lower()
    return "kimi" in lowered or "cinesmith —" in lowered or "hermes script" in lowered


def _ensure_bot_mode_protocol(cfg_path: Path) -> None:
    text = cfg_path.read_text(encoding="utf-8")
    if "bot_mode_protocol" in text:
        return
    if "\nagent:\n" in text or text.startswith("agent:"):
        text = text.replace("agent:\n", "agent:\n  bot_mode_protocol: true\n", 1)
    else:
        text = text.rstrip() + "\nagent:\n  bot_mode_protocol: true\n"
    cfg_path.write_text(text, encoding="utf-8")
