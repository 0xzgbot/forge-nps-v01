# Forge NPS Dashboard Reference

The dashboard is the FastAPI UI/API surface for Forge NPS.

- App file: [dashboard/forge_dashboard.py](~/Desktop/forge_nps_v01/dashboard/forge_dashboard.py)
- Default port: `7000`
- UI: `http://localhost:7000`

For full installation and service setup, use [INSTALLATION_AGENT_GUIDE.md](~/Desktop/forge_nps_v01/INSTALLATION_AGENT_GUIDE.md).

## Startup Behavior

On startup the dashboard:

1. Loads `.env`.
2. Overlays `data/config.json`.
3. Ensures media directories exist.
4. Reindexes media from `FORGE_MEDIA_ROOT`.
5. Queries LM Studio `/v1/models`.
6. Emits LM Studio status events.

Expected log signs:

```text
[FORGE] Media shots reindexed at startup: ...
[FORGE] LM Studio auto-detected model: ...
Uvicorn running on http://0.0.0.0:7000
```

## Canonical API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/` | Serve dashboard UI. |
| `POST` | `/api/hermes/chat` | Stream Hermes live chat response. |
| `POST` | `/api/hermes/run-campaign` | Run full campaign pipeline as NDJSON stream. |
| `POST` | `/api/hermes/cancel` | Cancel active campaign stream. |
| `GET` | `/api/shots` | Return current shot store. |
| `GET` | `/api/campaigns` | Return campaign index. |
| `POST` | `/api/audit/reprocess` | Re-audit selected shot IDs. |
| `POST` | `/api/audit/remediate` | Remediate failed selected shot IDs. |
| `GET` | `/api/memory/health` | Return memory integrity health. |
| `GET` | `/api/config` | Return effective settings. |
| `POST` | `/api/config/save` | Persist settings to `data/config.json`. |
| `GET` | `/api/lmstudio/status` | Check loaded and available LM Studio models. |
| `POST` | `/api/lmstudio/load` | Ask LM Studio to load selected model using LM Studio defaults. |
| `POST` | `/api/test/comfyui` | Test ComfyUI host health. |

Legacy dispatch/render endpoints are intentionally disabled. See [PIPELINE_CONTRACT_SUMMARY.md](~/Desktop/forge_nps_v01/PIPELINE_CONTRACT_SUMMARY.md).

## Campaign Stream

`POST /api/hermes/run-campaign` returns newline-delimited JSON.

Expected early sequence:

```json
{"type":"pipeline_timing","stage":"backend_stream_open"}
{"type":"profile","text":"Hermes / Campaign Intake starting."}
{"type":"pipeline_timing","stage":"hermes_campaign_intake"}
{"type":"profile","text":"Hermes / Campaign Intake complete."}
{"type":"kimi","text":"Generating shot list..."}
{"type":"pipeline_timing","stage":"kimi_director_plan"}
{"type":"kimi_raw","text":"..."}
```

Common event types:

- `profile`
- `pipeline_timing`
- `kimi`
- `kimi_raw`
- `kimi_plan`
- `kimi_review`
- `compiler`
- `spark`
- `render_complete`
- `kimi_vl_audit`
- `memory`
- `warning`
- `error`
- `done`

## Settings Behavior

The Settings page writes to `data/config.json`. Effective config is `.env` plus the JSON override.

LM Studio behavior:

- **Test & Detect Models** calls status/model-list endpoints.
- **Load Model** and **Reload Hermes/Vision** call `POST /api/lmstudio/load` with the selected model only.
- Forge does not send context length, eval batch size, flash attention, or KV-cache overrides.

## Local Checks

```bash
curl -sS http://localhost:7000/api/stats
curl -sS http://localhost:7000/api/config
curl -sS http://localhost:7000/api/shots
```

Hermes chat:

```bash
curl -sS -N -X POST http://localhost:7000/api/hermes/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"Say hello in one sentence.","profile":"live"}'
```

ComfyUI:

```bash
curl -sS -X POST http://localhost:7000/api/test/comfyui \
  -H 'Content-Type: application/json' \
  -d '{"host":"http://localhost:8188"}'
```
