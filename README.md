# Forge NPS

Forge NPS is a cinematic production pipeline for the Hermes Agent Creative Hackathon.

Runtime roles:

1. Hermes is the pipeline brain: campaign intake, prompt compilation, continuity, remediation.
2. Kimi is the director planner and critique model.
3. Spark/ComfyUI renders images and videos.
4. Vision audit gates quality and drives remediation.
5. Memory records provenance, failures, retries, and outcomes.

## Active Documentation

| File | Purpose |
|------|---------|
| [INSTALLATION_AGENT_GUIDE.md](/Users/zgbot/Desktop/forge_nps_v01/INSTALLATION_AGENT_GUIDE.md) | Full setup/runbook for another agent or engineer. |
| [ARCHITECTURE.md](/Users/zgbot/Desktop/forge_nps_v01/ARCHITECTURE.md) | Current runtime architecture, service boundaries, and data flow. |
| [PIPELINE_CONTRACT_SUMMARY.md](/Users/zgbot/Desktop/forge_nps_v01/PIPELINE_CONTRACT_SUMMARY.md) | Event, shot, memory, state, and fallback contract. |
| [STABILITY_CHECKLIST.md](/Users/zgbot/Desktop/forge_nps_v01/STABILITY_CHECKLIST.md) | Pre-demo health and smoke checklist. |
| [SUBMISSION_GUIDE.md](/Users/zgbot/Desktop/forge_nps_v01/SUBMISSION_GUIDE.md) | Judge-facing proof points and demo script. |
| [dashboard/COMMAND_CENTER_README.md](/Users/zgbot/Desktop/forge_nps_v01/dashboard/COMMAND_CENTER_README.md) | Dashboard-specific API/UI reference. |
| [data/contracts/pipeline_contract.json](/Users/zgbot/Desktop/forge_nps_v01/data/contracts/pipeline_contract.json) | Machine-readable pipeline contract. |

Archived planning/demo drafts live under [docs/archive](/Users/zgbot/Desktop/forge_nps_v01/docs/archive).

## Quick Start

```bash
cd /Users/zgbot/Desktop/forge_nps_v01
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python3 -m dashboard.forge_dashboard
```

Open:

```text
http://127.0.0.1:7000
```

For full setup, including LM Studio, Kimi/NVIDIA, ComfyUI, media paths, and smoke tests, use [INSTALLATION_AGENT_GUIDE.md](/Users/zgbot/Desktop/forge_nps_v01/INSTALLATION_AGENT_GUIDE.md).

## Required Services

| Service | Default |
|---------|---------|
| Dashboard | `http://127.0.0.1:7000` |
| Kimi/NVIDIA-compatible API | `https://integrate.api.nvidia.com/v1/chat/completions` |
| LM Studio | `http://100.74.164.1:1234` |
| ComfyUI/Spark | `http://100.112.87.8:8188` |
| Media root | `/Users/zgbot/Desktop/FORGE_NPS_MEDIA` |

Minimum environment/config values:

```bash
KIMI_API_KEY=nvapi-...
NIM_ENDPOINT=https://integrate.api.nvidia.com/v1/chat/completions
KIMI_INSTRUCT_MODEL=moonshotai/kimi-k2-instruct
KIMI_THINKING_MODEL=moonshotai/kimi-k2.6

LMSTUDIO_HOST=http://100.74.164.1
LMSTUDIO_PORT=1234
LMSTUDIO_CHAT_MODEL=qwen3.6-35b-a3b@q6_k
LMSTUDIO_VISION_MODEL=qwen3.6-35b-a3b@q6_k

COMFYUI_PRIMARY=http://100.112.87.8:8188
FORGE_MEDIA_ROOT=/Users/zgbot/Desktop/FORGE_NPS_MEDIA
```

`data/config.json` can override `.env` because the Settings page persists there.

## Canonical API Path

1. `POST /api/hermes/run-campaign`
2. `GET /api/shots`
3. `POST /api/audit/reprocess`
4. `POST /api/audit/remediate`
5. `GET /api/memory/health`

Legacy dispatch/render routes are intentionally disabled and return `410 legacy_disabled`; see [PIPELINE_CONTRACT_SUMMARY.md](/Users/zgbot/Desktop/forge_nps_v01/PIPELINE_CONTRACT_SUMMARY.md).

## Verification

```bash
python3 -m py_compile dashboard/forge_dashboard.py core/hermes/pipeline/campaign_service.py core/hermes/pipeline/profile_cli.py
curl -sS http://127.0.0.1:7000/api/stats
```

Run the full pre-demo checklist in [STABILITY_CHECKLIST.md](/Users/zgbot/Desktop/forge_nps_v01/STABILITY_CHECKLIST.md).

## Key Runtime Files

- [dashboard/forge_dashboard.py](/Users/zgbot/Desktop/forge_nps_v01/dashboard/forge_dashboard.py)
- [core/hermes/pipeline/campaign_service.py](/Users/zgbot/Desktop/forge_nps_v01/core/hermes/pipeline/campaign_service.py)
- [core/hermes/pipeline/director_service.py](/Users/zgbot/Desktop/forge_nps_v01/core/hermes/pipeline/director_service.py)
- [core/hermes/pipeline/profile_cli.py](/Users/zgbot/Desktop/forge_nps_v01/core/hermes/pipeline/profile_cli.py)
- [core/hermes/pipeline/audit_service.py](/Users/zgbot/Desktop/forge_nps_v01/core/hermes/pipeline/audit_service.py)
- [core/prompts/prompt_compiler.py](/Users/zgbot/Desktop/forge_nps_v01/core/prompts/prompt_compiler.py)

## Hermes Engine Submodule

`hermes_engine` is tracked as a submodule. To update it:

```bash
/Users/zgbot/Desktop/forge_nps_v01/scripts/update_hermes_engine.sh
git status
git commit -am "chore: update hermes_engine"
git push
```

Keep Forge-specific behavior in this repo (`dashboard/`, `core/`, `hermes_home/skills`, `hermes_home/profiles/forgehermes`) rather than editing upstream engine internals.
