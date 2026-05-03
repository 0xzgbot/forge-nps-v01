---
name: sienna-nomad-anchor-payload-builder
description: Builds and submits ComfyUI JSON payloads for the Sienna Nomad project using pre-built Python scripts. Do NOT attempt to build payloads manually or read workflow JSON files — always use the scripts.
---

# Sienna Nomad — Payload Pipeline

## CRITICAL RULE
Never build JSON payloads manually. Never read the workflow JSON into context.
Always use the scripts below. They handle all parsing, formatting, and submission.

---

## Script 1 — Build all JSON payloads
**When:** Any time payloads need to be built or rebuilt from .md files.

```bash
python3 /Users/zgbot/Desktop/Sienna_Nomad_Project/build_payloads.py
```

Options:
- `--rebuild` — overwrite all existing payloads (use after .md files change)
- `--dry-run` — show what would be built without writing anything
- `--type anchor|photo|video` — build only one type

This script scans the entire project automatically. It handles all 3 prompt formats
(standard CINEMATIC CONTEXT, markdown bullets, plain key:value). No batch files needed.
Run once, it builds everything.

---

## Script 2 — Submit to ComfyUI and retrieve PNGs
**When:** ComfyUI is online and renders are needed.
**Order:** Always run images first, videos separately when LTX workflow is ready.

```bash
# Step 1 — anchors + photos (z-image-turbo):
python3 /Users/zgbot/Desktop/Sienna_Nomad_Project/submit_to_comfyui.py --type image

# Step 2 — videos (run later when LTX workflow is configured):
python3 /Users/zgbot/Desktop/Sienna_Nomad_Project/submit_to_comfyui.py --type video
```

Options:
- `--resume` — skip files whose PNG already exists (safe to re-run after interruption)
- `--dry-run` — list files without submitting
- `--port 8188` — restrict to one GPU

---

## ComfyUI endpoints
- Port 8188: `http://localhost:8188`
- Port 8189: `http://localhost:8189`
- Health check: `GET http://localhost:8188/api/system_stats`

---

## Project layout
- Prompts: `/Users/zgbot/Desktop/Sienna_Nomad_Project/04_Prompt_Library/`
- Each episode: `EP##_Name/` with `JSON_PAYLOADS/` subfolder
- Workflow template: `/Users/zgbot/workflows/hermes_z_image_turbo_api.json`
- Build log: `/Users/zgbot/Desktop/Sienna_Nomad_Project/build_log.txt`
- Submit log: `/Users/zgbot/Desktop/Sienna_Nomad_Project/submit_log.txt`

---

## Typical full run
1. `python3 build_payloads.py --rebuild` — build all JSONs
2. Start ComfyUI on Windows machine
3. `python3 submit_to_comfyui.py --type image` — render all anchors + photos
4. PNGs save automatically to each episode folder
