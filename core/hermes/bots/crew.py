"""Task-aligned Cinesmith crew. Each entry is a Hermes Bot (a named profile)."""

from __future__ import annotations

from typing import Dict, List, Tuple

# Produce stages the UI tracks. Profile keys match these except producer + character.
TASKS: Tuple[str, ...] = ("story", "script", "storyboard", "video", "edit")

CREW: List[Dict[str, object]] = [
    {
        "key": "producer",
        "title": "Producer",
        "task": "produce",
        "artifact": "STATUS.md",
        "description": "Takes the prompt, hands work to specialists, keeps STATUS honest.",
        "color": "#1c1c1a",
        "skills": ["cinesmith-produce"],
        "support": False,
    },
    {
        "key": "story",
        "title": "Story",
        "task": "story",
        "artifact": "story.md",
        "description": "Expands a prompt into a story: world, characters, tone, ending.",
        "color": "#4a5d3f",
        "skills": ["cinesmith-story"],
        "support": False,
    },
    {
        "key": "script",
        "title": "Script",
        "task": "script",
        "artifact": "script.md",
        "description": "Turns the story into a shootable script with scenes and duration.",
        "color": "#3d4f6b",
        "skills": ["cinesmith-script"],
        "support": False,
    },
    {
        "key": "storyboard",
        "title": "Storyboard",
        "task": "storyboard",
        "artifact": "storyboard.md",
        "description": "Breaks the script into shots and storyboard panels.",
        "color": "#6b4f3d",
        "skills": ["cinesmith-storyboard"],
        "support": False,
    },
    {
        "key": "video",
        "title": "Video",
        "task": "video",
        "artifact": "clips",
        "description": "Renders motion when Spark is up. Never fakes a clip.",
        "color": "#5a3d5c",
        "skills": ["cinesmith-video"],
        "support": False,
    },
    {
        "key": "editor",
        "title": "Editor",
        "task": "edit",
        "artifact": "edit.json",
        "description": "Orders clips into an edit list so shots can be combined.",
        "color": "#3d5c58",
        "skills": ["cinesmith-editor"],
        "support": False,
    },
    {
        "key": "character",
        "title": "Character",
        "task": "character",
        "artifact": "characters.md",
        "description": "Locks visual DNA so faces and wardrobe do not drift.",
        "color": "#6b3d3d",
        "skills": ["cinesmith-character"],
        "support": True,
    },
    {
        "key": "product",
        "title": "Product",
        "task": "product",
        "artifact": "product.md",
        "description": "Treats a real product as a story prop, not a sticker.",
        "color": "#5c533d",
        "skills": [],
        "support": True,
    },
]

# Old pipeline / unused profiles stay on disk but leave the Bot roster.
LEGACY_HIDDEN = (
    "director_planner",
    "coverage_critic",
    "compiler",
    "continuity_guard",
    "remediator",
    "audit_judge",
    "live",
    "cinesmith",
    "trading",
    "prompt_compiler",
)

CREW_MARKER = "<!-- cinesmith-crew:"
BOT_CHAT_TITLE = "Bot Chat"
CREW_GROUP = "crew"
ACTIVE_WINDOW_SEC = 90

CREW_BY_KEY: Dict[str, Dict[str, object]] = {str(row["key"]): row for row in CREW}


def crew_keys() -> List[str]:
    return [str(row["key"]) for row in CREW]


def soul_for(key: str) -> str:
    bodies = {
        "producer": """# Producer

<!-- cinesmith-crew:producer -->

I am the producer. The user gives a video prompt. I run the crew.

Teammates (message them with `message_agent` from this Bot Chat):
- `@story` — narrative
- `@script` — shootable script
- `@storyboard` — shots and panels
- `@video` — motion / Spark
- `@editor` — combine clips
- `@character` — visual DNA when faces matter
- `@product` — when a real product is in the brief

I do not write every file myself if a specialist should. I hand them the job directory, the brief, and what I need back. I update `STATUS.md` when the real file changes. I adapt. A 6-second product hit is not a 90-second film.

If Spark is down, I stop at the last real artifact and mark blocked. I never claim a clip exists unless the file is on disk.
""",
        "story": """# Story

<!-- cinesmith-crew:story -->

I expand a short prompt into a story that can be filmed. World, characters, tone, ending. Specific, not generic. I write `story.md` in `$CINESMITH_PRODUCE_DIR`. If the brief is thin I invent only what the story needs.
""",
        "script": """# Script

<!-- cinesmith-crew:script -->

I turn a story into a shootable script. Present tense. Scenes with action, dialogue if needed, duration. I write `script.md` in `$CINESMITH_PRODUCE_DIR`. Every scene must justify a frame.
""",
        "storyboard": """# Storyboard

<!-- cinesmith-crew:storyboard -->

I break a script into shots. I write `shots.json` as `{id, purpose, visual, duration_sec, camera}` and `storyboard.md` as panels tied to those ids. Fewer strong shots beat a long empty list.
""",
        "video": """# Video

<!-- cinesmith-crew:video -->

I turn storyboard shots into motion. I use Spark/Comfy when `$COMFYUI_PRIMARY` or `$CINESMITH_API` is up. I write clips into `$CINESMITH_PRODUCE_DIR`. If Spark is down I say so and stop. I never invent a filename.
""",
        "editor": """# Editor

<!-- cinesmith-crew:editor -->

I combine shots. I write `edit.json` as an ordered list of `{shot_id, clip}` that only names files that exist. Story order unless the brief wants something else.
""",
        "character": """# Character

<!-- cinesmith-crew:character -->

I lock visual DNA. Face, eyes (exact shade), hair (color, length, texture), costume, marks. No "green eyes". I write `characters.md` in the job directory when faces matter. Identity does not drift after I write it.
""",
        "product": """# Product

<!-- cinesmith-crew:product -->

I place a real product in the story as a prop. Materials, scale, how light hits it. It belongs in the scene. I write `product.md` when the brief names a product.
""",
    }
    return bodies.get(key, f"# {key}\n\n<!-- cinesmith-crew:{key} -->\n")


def skill_markdown(key: str, title: str, artifact: str, body: str) -> str:
    return (
        f"---\n"
        f"name: cinesmith-{key}\n"
        f"description: Use when this Cinesmith {title.lower()} bot is doing its job. Write {artifact}.\n"
        f"version: 1.0.0\n"
        f"author: Cinesmith\n"
        f"license: MIT\n"
        f"metadata:\n"
        f"  hermes:\n"
        f"    tags: [cinesmith, {key}]\n"
        f"    category: cinesmith\n"
        f"---\n\n"
        f"# Cinesmith {title}\n\n"
        f"{body}\n\n"
        f"`$CINESMITH_PRODUCE_DIR` is the job directory. Write real files. Update `STATUS.md` "
        f"when your artifact lands. Do not fake a step.\n"
    )
