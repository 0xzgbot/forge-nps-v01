#!/usr/bin/env python3
"""Add modern Hermes SKILL.md frontmatter to installed skills that lack it."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "hermes_home" / "skills"
MAX_NAME = 64
MAX_DESC = 1024


def parse_frontmatter(text: str) -> tuple[dict | None, str]:
    raw = text.lstrip("\ufeff")
    if not raw.startswith("---"):
        return None, raw
    match = re.search(r"\n---\s*\n", raw[3:])
    if not match:
        return None, raw
    try:
        parsed = yaml.safe_load(raw[3 : match.start() + 3])
    except yaml.YAMLError:
        return None, raw
    if not isinstance(parsed, dict):
        return None, raw
    body = raw[match.end() + 3 :]
    return parsed, body


def slug_name(path: Path) -> str:
    name = path.parent.name.strip().lower().replace("_", "-")
    name = re.sub(r"[^a-z0-9-]+", "-", name).strip("-")
    return (name or "cinesmith-skill")[:MAX_NAME]


def infer_description(body: str, name: str) -> str:
    for line in body.splitlines():
        cleaned = line.strip().lstrip("#").strip()
        if not cleaned:
            continue
        if cleaned.lower().startswith(("skill:", "domain:", "version:", "for:")):
            continue
        if cleaned.startswith("---"):
            continue
        desc = cleaned
        if not desc.endswith("."):
            desc += "."
        if len(desc) < 24:
            desc = f"Use when the task involves {name.replace('-', ' ')}. {desc}"
        return desc[:MAX_DESC]
    return f"Use when Cinesmith production needs {name.replace('-', ' ')}."[:MAX_DESC]


def category_for(path: Path) -> str:
    rel = path.relative_to(SKILLS)
    if len(rel.parts) > 2:
        return rel.parts[0]
    if path.parent.name.startswith(("skill-", "workflow-", "flux", "ltx", "cinematic")):
        return "cinesmith"
    return "cinesmith"


def migrate(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    fm, body = parse_frontmatter(text)
    name = slug_name(path)
    if fm and fm.get("name") and fm.get("description"):
        changed = False
        if "version" not in fm:
            fm["version"] = "1.0.0"
            changed = True
        if "author" not in fm:
            fm["author"] = "Cinesmith"
            changed = True
        if "license" not in fm:
            fm["license"] = "MIT"
            changed = True
        hermes = fm.setdefault("metadata", {}).setdefault("hermes", {}) if isinstance(fm.get("metadata"), dict) or "metadata" not in fm else fm.get("metadata", {}).get("hermes", {})
        if not isinstance(fm.get("metadata"), dict):
            fm["metadata"] = {"hermes": {"tags": [name], "category": category_for(path)}}
            changed = True
        else:
            hermes_meta = fm["metadata"].setdefault("hermes", {})
            if not isinstance(hermes_meta, dict):
                fm["metadata"]["hermes"] = {"tags": [name], "category": category_for(path)}
                changed = True
            else:
                hermes_meta.setdefault("tags", [name])
                hermes_meta.setdefault("category", category_for(path))
        if not changed:
            return "ok"
        dumped = yaml.safe_dump(fm, sort_keys=False, allow_unicode=True).strip()
        path.write_text(f"---\n{dumped}\n---\n\n{body.lstrip()}", encoding="utf-8")
        return "enriched"
    desc = infer_description(body, name)
    payload = {
        "name": name,
        "description": desc,
        "version": "1.0.0",
        "author": "Cinesmith",
        "license": "MIT",
        "metadata": {
            "hermes": {
                "tags": [name, "cinesmith", "production"],
                "category": category_for(path),
            }
        },
    }
    dumped = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True).strip()
    path.write_text(f"---\n{dumped}\n---\n\n{body.lstrip()}", encoding="utf-8")
    return "added"


def main() -> int:
    if not SKILLS.exists():
        print(f"missing {SKILLS}", file=sys.stderr)
        return 1
    counts = {"ok": 0, "enriched": 0, "added": 0}
    for skill in sorted(SKILLS.rglob("SKILL.md")):
        status = migrate(skill)
        counts[status] = counts.get(status, 0) + 1
        if status != "ok":
            print(f"{status:8} {skill.relative_to(SKILLS)}")
    print(
        f"done added={counts['added']} enriched={counts['enriched']} already_modern={counts['ok']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
