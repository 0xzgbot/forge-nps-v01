# Cinesmith Architecture

## Runtime Boundary

Canonical runtime lives in:

```text
~/Desktop/cinesmith_v01
```

Primary app:

- Server: [dashboard/cinesmith_dashboard.py](~/Desktop/cinesmith_v01/dashboard/cinesmith_dashboard.py)
- Port: `7000`
- UI: `http://127.0.0.1:7000`

Cinesmith is a multi-service app. The dashboard coordinates an LLM (local or frontier), dual-3090 Comfy for stills, and Spark MiniMax H3 for video.

## Produce (primary surface)

`GET /` serves Produce. Job files live under `data/produce/<id>/`. Hermes (`@producer` and crew bots) writes story/script/shots; a worker drains `queue.json` onto the right Comfy host. See [PRODUCE.md](PRODUCE.md).

| File | Responsibility |
|------|----------------|
| [core/dispatch/capability_router.py](../core/dispatch/capability_router.py) | Spark = video/H3; 3090 A/B = stills. |
| [core/hermes/produce/service.py](../core/hermes/produce/service.py) | Starts Hermes on a job directory. Not a stage machine. |
| [core/hermes/produce/queue.py](../core/hermes/produce/queue.py) | Honest GPU queue. GET snapshot never drains. |
| [core/hermes/produce/render.py](../core/hermes/produce/render.py) | `render_board`, `render_take`, range retake, assemble. |
| [core/assembly/timeline_assembler.py](../core/assembly/timeline_assembler.py) | ffmpeg concat, mute, stitch, color pass. |
| [dashboard/routes/produce.py](../dashboard/routes/produce.py) | Produce HTTP API. |

## Service Roles

| Service | Runtime Role |
|---------|--------------|
| FastAPI dashboard | Thin API/UI adapter, config, media serving, stream orchestration. |
| Hermes pipeline services | Campaign intake, prompt compilation, continuity, remediation, memory writes. |
| Kimi/NVIDIA | Director planning, coverage critique, visual audit when configured. |
| LM Studio | Hermes local profile/chat calls and optional local vision model. |
| ComfyUI/Spark | Render execution and output files. |
| Media root | Durable rendered image/video storage outside the repo. |

## Pipeline Services

| File | Responsibility |
|------|----------------|
| [core/hermes/pipeline/campaign_service.py](~/Desktop/cinesmith_v01/core/hermes/pipeline/campaign_service.py) | Main campaign orchestration and NDJSON stream events. |
| [core/hermes/pipeline/director_service.py](~/Desktop/cinesmith_v01/core/hermes/pipeline/director_service.py) | Kimi shot planning, requested shot count, self-check. |
| [core/hermes/pipeline/profile_cli.py](~/Desktop/cinesmith_v01/core/hermes/pipeline/profile_cli.py) | Hermes profile calls through LM Studio/OpenAI-compatible API. |
| [core/hermes/pipeline/audit_service.py](~/Desktop/cinesmith_v01/core/hermes/pipeline/audit_service.py) | Re-audit and remediation orchestration. |
| [core/hermes/pipeline/video_service.py](~/Desktop/cinesmith_v01/core/hermes/pipeline/video_service.py) | Image-to-video prompt/render support. |
| [core/hermes/pipeline/state_machine.py](~/Desktop/cinesmith_v01/core/hermes/pipeline/state_machine.py) | Canonical shot state transitions. |
| [core/prompts/prompt_compiler.py](~/Desktop/cinesmith_v01/core/prompts/prompt_compiler.py) | Workflow-aware prompt artifact compilation. |
| [core/storyboard/image_providers.py](~/Desktop/cinesmith_v01/core/storyboard/image_providers.py) | Optional OpenAI and Gemini/Nano Banana storyboard image providers. |
| [core/affiliate/local_spark_media.py](~/Desktop/cinesmith_v01/core/affiliate/local_spark_media.py) | Legacy-compatible local creative adapter backed by Spark/ComfyUI. New visible output names use the selected model prefix. |

## Data Flow

1. UI or client calls `POST /api/hermes/run-campaign`.
2. Hermes campaign intake produces director context.
3. Kimi creates a structured shot plan.
4. Kimi performs planning/self-check critique.
5. Hermes compiles each shot into workflow-specific prompt artifacts.
6. ComfyUI/Spark renders each prompt.
7. Vision audit stamps pass/fail details.
8. Failed shots can be re-audited or remediated into linked retries.
9. Memory records canonical pipeline events and outcomes.

## Script Studio Data Flow

Script Studio uses a persisted job runner instead of a manual chain of UI clicks.

1. User enters a short brief and clicks **Generate Videos**.
2. `POST /api/script/pipeline/start` creates or updates a saved script project and starts a background job.
3. The job builds a locked script package.
4. Coverage is generated from the package.
5. A storyboard plan is built from coverage and continuity locks.
6. Individual storyboard start frames are rendered at 1080p by the selected storyboard image provider.
7. Rendered frames are exported into `storyboard_start_frame` shot records.
8. Only those `storyboard_start_frame` records are queued for LTX image-to-video generation.
9. `GET /api/script/pipeline/jobs/{job_id}` returns logs plus the saved project, including `storyboard_panel_jobs` and `video_shots`.
10. The Script Studio **Videos** panel displays generated start frames and completed clips directly.

Storyboard provider options:

- `spark:flux2_dev`
- `spark:flux2_klein`
- `spark:z_image`
- `spark:z_image_turbo`
- `openai` when `OPENAI_API_KEY` is configured
- `gemini` / Nano Banana when `GEMINI_API_KEY` is configured

## Dashboard Workspaces

Produce (`/`) is the default app. `/studio` is the previous multi-tab campaign UI (Images, Videos, Stories, Characters, Memory, Settings).

| Workspace | Runtime Role |
|-----------|--------------|
| Produce | Prompt, Hermes crew, 3090 boards, H3 takes, queue, timeline, cut. |
| Images (legacy studio) | Prompt intake, generation controls, campaign selection, log and media review. |
| Ideas | Hermes/shot-store kanban board grouped by intake, planning, prompt compile, render, audit, revise, and approved stages. |
| Characters | Identity asset management, character image upload, DNA editing, character render prompts, and character render history. |
| Script | One-click brief-to-video pipeline, saved script projects, package generation, coverage, storyboard start frames, and individual video clips. |
| Asset Vault | Product, brand, reference, style, and linked-character packages used by storyboard continuity. |
| Videos | Image/video processing, failed render remediation, media refresh, and video workflow dispatch. |
| Memory | Provenance graph, insights, playback, and campaign/event filtering. |
| Settings | Provider, endpoint, ComfyUI/Spark, LM Studio, Kimi/NIM, and profile configuration. |

## Canonical Endpoints

Produce (home):

- `POST /api/produce/start`
- `GET /api/produce/{job_id}`
- `POST /api/produce/{job_id}/render-board`
- `POST /api/produce/{job_id}/render-take`
- `POST /api/produce/{job_id}/range-retake`
- `POST /api/produce/{job_id}/queue` / `queue/plan` / `queue/run`
- `POST /api/produce/{job_id}/assemble`
- `GET /api/connect/status`

Campaign / studio (legacy path):

- `POST /api/hermes/run-campaign`
- `POST /api/hermes/cancel`
- `GET /api/hermes/idea-board`
- `GET /api/shots`
- `GET /api/campaigns`
- `POST /api/script/develop`
- `POST /api/script/pipeline/start`
- `GET /api/script/pipeline/jobs/{job_id}`
- `GET /api/script/storyboard/image-models`
- `POST /api/script/storyboard/render-image`
- `POST /api/script/storyboard/export-video-shots`
- `POST /api/director/generate`
- `GET /api/characters`
- `POST /api/characters`
- `POST /api/characters/spark-render`
- `POST /api/audit/reprocess`
- `POST /api/audit/remediate`
- `GET /api/memory/health`
- `GET /api/config`
- `POST /api/config/save`
- `GET /api/lmstudio/status`
- `POST /api/lmstudio/load`
- `POST /api/test/comfyui`

## Media Storage

Media root:

```text
~/Desktop/CINESMITH_MEDIA
```

Important folders:

- `images/`
- `videos/`
- `imports/`
- `legacy/`

Dashboard routes serve media through `/media-assets/*` and `/external-renders/*`.

## Configuration Resolution

Runtime config loads from `.env`, then overlays `data/config.json`. The Settings page writes to `data/config.json`.

Important note: LM Studio load tuning is not controlled by Cinesmith. `POST /api/lmstudio/load` sends the selected model and lets LM Studio use its own model defaults.

## Legacy Policy

Legacy routes are intentionally disabled and return `410 legacy_disabled`:

- `/api/shots/dispatch-all`
- `/api/shots/dispatch`
- `/api/submit-recipe`
- `/api/inject-prompt`
- `/api/render`
- `/api/render/audit`

Compatibility shim:

- `/api/renders/audit-batch` forwards to canonical re-audit only when `shot_ids` is provided.

## Fallback Behavior

Fallbacks are explicit and surfaced to the caller.

- The Ideas workspace calls `GET /api/hermes/idea-board` when available. If the running backend does not expose that route, the frontend builds a compatible board from `GET /api/shots`.
- The backend idea-board route asks Hermes for a board if Hermes exposes a compatible method, otherwise it builds the board from `_SHOTS_STORE`.
- Script development can return a deterministic fallback package if the Director API is unavailable.
- Director shot-list generation can derive fallback coverage from a locked script package after Director API failure, preserving scene IDs, beat IDs, continuity locks, screen direction, and edit role.
- Script Studio video generation is explicitly job-based. It persists phase logs, frame outputs, video shot records, and queued video jobs to the saved script project.
- Storyboard page proofs are advanced artifacts only; the default video path uses individual production keyframes.
- Profile calls normalize OpenAI-compatible base URLs without rewriting explicit custom endpoint ports.

## Contract Reference

Event stream types, shot fields, memory events, allowed states, and fallback policy are defined in [PIPELINE_CONTRACT_SUMMARY.md](PIPELINE_CONTRACT_SUMMARY.md) and [data/contracts/pipeline_contract.json](../data/contracts/pipeline_contract.json).
