# Cinesmith

**A fully local cinematic AI pipeline.** Brief it like an executive producer; it plans, compiles, renders, audits, and remembers. Runs on a DGX Spark plus dual RTX 3090s driving multiple ComfyUI instances.

Cinesmith (formerly Forge NPS) is an agency-shaped production pipeline for film-like stills, stories, and video. A custom Hermes agent — isolated in this repo's `hermes_home/` so it never touches your `~/.hermes` — moves a campaign from brief to finished frames. The heavy lifting stays on hardware you own.

> **Offline by design.** No cloud render path is required for images, characters, videos, or remediation. The Hermes orchestration and all ComfyUI work are local.

---

## Features

- **An agency brain, not a prompt pile.** A custom Hermes agent handles intake, skill routing, prompt compilation, continuity, remediation, and memory writes.
- **Director planning.** Kimi Moonshot produces structured shot plans, critiques coverage before render spend, and hands off to Hermes.
- **Plan → render → audit → remember.** Every campaign runs the same closed loop, and every shot records the results.
- **Images, Stories, and Videos.** Multi-beat stories, multi-episode series, start-frame and first/last-frame pairs, and LTX / Flux / Z-Image workflows.
- **Character continuity.** Sheet-from-photo identity that locks offline.
- **A curated skill pack.** Hundreds of Hermes skill directories for style, lighting, cinematography, continuity, diagnostics, product, and character work (index: [`docs/SKILLS_INDEX.md`](docs/SKILLS_INDEX.md)).
- **Provenance memory.** What fired, what failed, how it was corrected, and what finally passed.

---

## Pipeline

Campaign image generation:

```
brief → Hermes intake → Kimi shot planning → Kimi critique → prompt compiler
     → Spark/ComfyUI render → vision audit → pass? → memory
                                     └ no → remediate → compiler
```

Script Studio video generation:

```
brief → generate videos → locked script package → coverage shot list
     → storyboard plan → 1080p start frames → LTX image-to-video → clips
```

---

## Getting started

Requires Python 3.10+ and a reachable ComfyUI instance (your DGX Spark or a LAN host). Configure one OpenAI-compatible inference provider for the director/planning models.

```bash
python3 -m venv .venv && source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.template .env          # pick a provider + key, set COMFYUI_PRIMARY
python3 scripts/preflight_desktop_spark.py
./scripts/launch_cinesmith.sh        # dev server -- uvicorn with reload
```

Open <http://127.0.0.1:7000>. First load lands on the **Agency** home: brief Hermes live, run an image campaign, or produce a Story. Press `?` for shortcuts.

For a packaged run instead of the reload server:

```bash
./scripts/launch_cinesmith.sh --package
python3 scripts/smoke_cinesmith.py --base-url http://127.0.0.1:7000
```

### Isolation and paths

`launch_cinesmith.sh` sets `HERMES_HOME=<repo>/hermes_home` and never points Hermes at `~/.hermes`. It also picks a portable media root: a sibling `CINESMITH_MEDIA` folder if present, otherwise `<repo>/media`. Allow `CINESMITH_ALLOW_GLOBAL_HERMES=1` only if you deliberately want the global install.

Provider choice and model names live in `.env.template`. `data/config.json` (git-ignored) can override `.env`; use [`data/config.example.json`](data/config.example.json) as the tracked reference shape.

---

## Layout

| Path | What lives there |
| --- | --- |
| [`core/`](core/) | Pipeline engines: genesis, prompt compilation, ComfyUI integration, audit, memory, routing, state. |
| [`dashboard/`](dashboard/) | The FastAPI dashboard and web UI on port 7000. |
| [`agents/`](agents/) | Agent packages: visual, production, audit, audio. |
| [`characters/`](characters/) | Character sheet definitions (`elena.yaml`, test sheets). |
| [`cinesmith_nexus/`](cinesmith_nexus/) | Nexus graph and MCP tooling for the dashboard. |
| [`workflows/`](workflows/) | ComfyUI workflow JSONs: Flux2, LTX, Z-Image, WAN, ernie, and more. |
| [`pipelines/`](pipelines/) | Sub-pipelines: generation, onboarding, training, video. |
| [`scripts/`](scripts/) | Launch, preflight, smoke, hygiene, and maintenance tooling. |
| [`docs/`](docs/) | Architecture, install guide, pipeline contract, changelog, stability checklist. |
| [`hermes_home/`](hermes_home/) | The isolated Hermes home: config, profiles, skills. |
| [`templates/`](templates/), [`prompts/`](prompts/), [`projects/`](projects/) | Project scaffolding and prompt libraries. |

`hermes_engine` is tracked as a git submodule and updated with [`scripts/update_hermes_engine.sh`](scripts/update_hermes_engine.sh).

---

## Verification

```bash
python3 -m pytest tests/                     # unit and integration suite
python3 scripts/pre_push_hygiene.sh         # catches tokens, IPs, config leaks
```

Before a demo, walk [`docs/STABILITY_CHECKLIST.md`](docs/STABILITY_CHECKLIST.md).

---

## Status

**Works now:** the end-to-end campaign loop for images (brief → plan → compile → Spark render → audit → memory), multi-beat Stories and series, start-frame and first/last-frame video, character-sheet continuity from a photo, and the Agency dashboard.

**Held / partial:** storyboard rendering defaults to local Spark/ComfyUI. OpenAI and Gemini image providers are optional extras behind keys, not requirements. A few advanced video controls (retake, IC-LoRA) are hidden until they have end-to-end controls. The test suite runs green; some integration paths need a live ComfyUI to pass.

Older work is logged in [`docs/CHANGELOG.md`](docs/CHANGELOG.md); product intent sits in [`docs/PRODUCT_VISION.md`](docs/PRODUCT_VISION.md).

---

## Documentation

| Doc | Purpose |
| --- | --- |
| [`docs/INSTALLATION_AGENT_GUIDE.md`](docs/INSTALLATION_AGENT_GUIDE.md) | Full setup and runbook. |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Services, boundaries, data flow. |
| [`docs/PIPELINE_CONTRACT_SUMMARY.md`](docs/PIPELINE_CONTRACT_SUMMARY.md) | Event, shot, memory, and fallback contract. |
| [`docs/SKILLS_INDEX.md`](docs/SKILLS_INDEX.md) | Index of the bundled skill set. |
| [`docs/STABILITY_CHECKLIST.md`](docs/STABILITY_CHECKLIST.md) | Pre-demo health and smoke checklist. |
| [`docs/CHANGELOG.md`](docs/CHANGELOG.md) | Dated implementation history. |

Launch the marketing site with `open marketing/index.html`, or the app UI concept with `open marketing/app-ui.html`.

---

## License

No license file is declared in this repository yet. Until one is added, treat the code as not licensed for reuse.
