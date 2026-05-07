# Forge NPS Installation Guide for Agents

This guide is for an agent or engineer bringing Forge NPS up on a new machine or restoring it on the current machine.

## Non-Negotiable Runtime Contract

- Hermes is the pipeline brain for campaign intake, prompt compilation, continuity, and remediation.
- Kimi is used at max capability for planning and critique.
- FastAPI routes are thin adapters around pipeline services.
- Production must not hide broken behavior behind silent fallbacks.
- LM Studio load tuning is not controlled by Forge. Forge loads the selected model and lets LM Studio apply its model defaults.

## What Must Be Running

Forge NPS is not a standalone single-process app. It expects these services:

| Component | Purpose | Default |
|-----------|---------|---------|
| Forge dashboard | FastAPI UI and pipeline API | `http://localhost:7000` |
| NVIDIA/Kimi-compatible API | Director planning and critique | `https://integrate.api.nvidia.com/v1/chat/completions` |
| LM Studio | Hermes local chat/profile calls and optional local vision | `http://localhost:1234` |
| ComfyUI/Spark | Image/video render execution | `http://localhost:8188` |
| Media root | Rendered images/videos served by dashboard | `~/Desktop/FORGE_NPS_MEDIA` |

## Repository Setup

Clone with submodules:

```bash
cd ~/Desktop
git clone --recurse-submodules https://github.com/0xzgbot/forge-nps-v01.git forge_nps_v01
cd ~/Desktop/forge_nps_v01
```

If the repo is already cloned, repair submodules:

```bash
git submodule update --init --recursive
```

The `hermes_engine` directory is a submodule. Do not make ad-hoc product fixes inside upstream Hermes internals unless the task is specifically to update the engine pointer.

## Python Environment

Use Python 3.11 or newer.

```bash
cd ~/Desktop/forge_nps_v01
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Quick import check:

```bash
python -m py_compile dashboard/forge_dashboard.py core/hermes/pipeline/campaign_service.py
```

## Required Configuration

Create `.env` from the template if needed:

```bash
cp .env.template .env
```

Required values:

```bash
KIMI_API_KEY=your_api_key_here
NIM_ENDPOINT=https://integrate.api.nvidia.com/v1/chat/completions
KIMI_INSTRUCT_MODEL=moonshotai/kimi-k2-instruct
KIMI_THINKING_MODEL=moonshotai/kimi-k2.6
KIMI_VISUAL_MODEL=qwen3.6-35b-a3b@q6_k

LMSTUDIO_HOST=http://localhost:1234
LMSTUDIO_PORT=1234
LMSTUDIO_CHAT_MODEL=qwen3.6-35b-a3b@q6_k
LMSTUDIO_VISION_MODEL=qwen3.6-35b-a3b@q6_k

COMFYUI_PRIMARY=http://localhost:8188
COMFYUI_SECONDARY=http://localhost:8189
FORGE_MEDIA_ROOT=~/Desktop/FORGE_NPS_MEDIA
```

Notes:

- `data/config.json` can override `.env` values because the Settings page persists there.
- `data/config.json` is ignored by git; [data/config.example.json](data/config.example.json) is the tracked reference shape.
- Do not commit real API keys, private IPs, or machine-specific endpoint URLs unless the repo owner explicitly accepts that risk.
- If settings appear wrong in the UI, inspect both `.env` and `data/config.json`.
- The LM Studio host can be saved as `http://host` plus `LMSTUDIO_PORT=1234`; the app normalizes it.

## Media Directories

Create the media root:

```bash
mkdir -p ~/Desktop/FORGE_NPS_MEDIA/images
mkdir -p ~/Desktop/FORGE_NPS_MEDIA/videos
mkdir -p ~/Desktop/FORGE_NPS_MEDIA/imports
mkdir -p ~/Desktop/FORGE_NPS_MEDIA/legacy
```

Forge reindexes media at dashboard startup. If ComfyUI produced files that are missing from the UI, restart the dashboard or use the import/reindex controls in the UI.

## LM Studio Setup

Start LM Studio server on the configured machine and expose the OpenAI-compatible API on port `1234`.

Required behavior:

- `GET /v1/models` must return loaded models.
- `POST /v1/chat/completions` must accept the selected `LMSTUDIO_CHAT_MODEL`.
- Forge does not send context length, eval batch size, flash attention, or KV-cache overrides.

Health check:

```bash
curl -sS http://localhost:1234/v1/models | python3 -m json.tool
```

Load model through Forge:

```bash
curl -sS -X POST http://localhost:7000/api/lmstudio/load \
  -H 'Content-Type: application/json' \
  -d '{"host":"http://localhost:1234","port":1234,"model":"qwen3.6-35b-a3b@q6_k"}' \
  | python3 -m json.tool
```

Known LM Studio compatibility issue:

- Do not use `response_format: {"type":"json_object"}` with this server. It rejects that shape.
- Hermes profile calls rely on prompt-level JSON instructions and parser validation.
- If the model returns reasoning-only output, the app should surface that instead of pretending it worked.

## ComfyUI/Spark Setup

Start ComfyUI on the render host, listening on `0.0.0.0:8188`.

Minimum health check:

```bash
curl -sS http://localhost:8188/system_stats | python3 -m json.tool
```

Dashboard health check:

```bash
curl -sS -X POST http://localhost:7000/api/test/comfyui \
  -H 'Content-Type: application/json' \
  -d '{"host":"http://localhost:8188"}' \
  | python3 -m json.tool
```

Workflows live under:

```text
~/Desktop/forge_nps_v01/workflows/
```

Campaign render flow expects `COMFYUI_PRIMARY` to be reachable before Spark dispatch.

## Start the Dashboard

From repo root:

```bash
cd ~/Desktop/forge_nps_v01
source .venv/bin/activate
python3 -m dashboard.forge_dashboard
```

Expected startup signs:

```text
[FORGE] Media shots reindexed at startup: ...
[FORGE] LM Studio auto-detected model: ...
Uvicorn running on http://0.0.0.0:7000
```

Open:

```text
http://localhost:7000
```

If port `7000` is busy:

```bash
lsof -ti tcp:7000
kill <pid>
```

## Dashboard Settings Checklist

In the Settings panel:

1. Confirm NVIDIA/Kimi endpoint and key.
2. Click **Test Connection** for the Kimi/NVIDIA provider.
3. Confirm LM Studio host, port, and model.
4. Click **Test & Detect Models**.
5. Click **Load Model** only if no model is loaded or the selected model changed.
6. Confirm ComfyUI primary host.
7. Click **Test ComfyUI + Spark**.
8. Save settings only after tests show the intended values.

## Smoke Tests

Stats:

```bash
curl -sS http://localhost:7000/api/stats | python3 -m json.tool
```

Config:

```bash
curl -sS http://localhost:7000/api/config | python3 -m json.tool
```

Hermes chat:

```bash
curl -sS -N -X POST http://localhost:7000/api/hermes/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"Say hello in one sentence.","profile":"live"}'
```

Campaign stream without using the UI:

```bash
curl -sS -N -X POST http://localhost:7000/api/hermes/run-campaign \
  -H 'Content-Type: application/json' \
  -d '{
    "brief":"A single figure standing on an empty dirt path, back to camera, pale morning sun casting long shadows, overcast sky, ground-level framing, desaturated tones.",
    "workflow_ids":["01_flux2_text_to_image"],
    "append_to_campaign":false
  }'
```

Expected early event order:

```text
backend_stream_open
Hermes / Campaign Intake starting.
Hermes / Campaign Intake complete.
Kimi: Generating shot list...
kimi_director_plan
kimi_raw
```

Cancel a running campaign:

```bash
curl -sS -X POST http://localhost:7000/api/hermes/cancel
```

Idea board fallback:

```bash
curl -sS http://localhost:7000/api/hermes/idea-board | python3 -m json.tool
```

If the running backend is older and does not expose `/api/hermes/idea-board`, the browser UI falls back to `/api/shots` and should still render the Ideas board.

## Common Failures and Fixes

### Generate Images Button Appears Dead

The button is usually firing if the log shows `backend_stream_open`. Check the stream for the first failure.

If it stops at Hermes intake:

- Check LM Studio is reachable.
- Check `LMSTUDIO_CHAT_MODEL` is loaded.
- Check `core/hermes/pipeline/profile_cli.py` is not sending incompatible `json_object` response format.

### Hermes Chat Says Offline

Check:

```bash
curl -sS http://localhost:1234/v1/models | python3 -m json.tool
```

If LM Studio says no models loaded, load the configured model from LM Studio or use the dashboard **Load Model** button.

### Vision Audit 400 From LM Studio

Common causes:

- The configured visual model is not loaded.
- The model is not vision-capable.
- Endpoint is wrong: local LM Studio should usually be `http://localhost:1234/v1`.
- Payload format rejected by the server.

### Settings Do Not Stick

Inspect:

```bash
cat ~/Desktop/forge_nps_v01/data/config.json
```

The Settings page writes to `data/config.json`; runtime config overlays that on top of `.env`.

If the file does not exist yet, seed it from the tracked example:

```bash
cp data/config.example.json data/config.json
```

### ComfyUI Renders Exist But Are Missing In App

Check media root:

```bash
find ~/Desktop/FORGE_NPS_MEDIA -maxdepth 3 -type f | head
```

Restart the dashboard so startup reindex runs, then refresh the UI.

## Git Workflow for Agents

Before edits:

```bash
git status --short
```

Rules:

- Do not revert unrelated user changes.
- Leave untracked files alone unless the user asks.
- Keep fixes scoped.
- Commit and push completed fixes when requested or when preserving operational state matters.

Current expected untracked local file may include:

```text
CAMPAIGN_IDEAS_BIBLE.md
```

Do not touch it unless asked.

## Final Demo Readiness Checklist

Run before submission/demo:

1. `python3 -m py_compile dashboard/forge_dashboard.py core/hermes/pipeline/campaign_service.py core/hermes/pipeline/profile_cli.py`
2. `GET /api/stats` succeeds.
3. Kimi **Test Connection** succeeds.
4. LM Studio **Test & Detect Models** succeeds.
5. ComfyUI **Test ComfyUI + Spark** succeeds.
6. `/api/hermes/chat` returns real content.
7. `/api/hermes/run-campaign` reaches Kimi planning.
8. A short campaign reaches Spark dispatch.
9. Rendered media appears in dashboard.
10. `/api/hermes/idea-board` returns a board, or the Ideas UI falls back to `/api/shots`.
11. Audit/remediation reports pass/fail details, not generic placeholders.
