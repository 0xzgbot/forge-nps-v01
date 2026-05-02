# Forge NPS

Forge NPS is the hackathon pipeline where:
1. Kimi is the director (structured shot planning + director self-check).
2. Hermes is the prompt engineer (skills + model-standard prompt compilation).
3. Spark/ComfyUI renders.
4. Vision audit gates quality.
5. Memory captures what happened.

## Canonical Docs
- `/Users/zgbot/Desktop/forge_nps_v01/DEMO_SCRIPT.md`
- `/Users/zgbot/Desktop/forge_nps_v01/STABILITY_CHECKLIST.md`
- `/Users/zgbot/Desktop/forge_nps_v01/PIPELINE_CONTRACT_SUMMARY.md`
- `/Users/zgbot/Desktop/forge_nps_v01/data/contracts/pipeline_contract.json`

## Demo Scope
In scope:
- Kimi structured director plan
- Hermes workflow-aware prompt compiler
- Spark render dispatch
- Vision re-audit and remediation retry
- Full per-shot provenance in API/UI

Out of scope for judging:
- video generation productionization
- memory graph visual polish
- legacy dispatch flows
- imported-media browsing polish

## Run
```bash
cd /Users/zgbot/Desktop/forge_nps_v01
KIMI_API_KEY="nvapi-..." uvicorn dashboard.forge_dashboard:app --host 0.0.0.0 --port 7000
```
Open: `http://localhost:7000`

## Updating Hermes Engine (Submodule)
`hermes_engine` is intentionally tracked as a submodule so Forge keeps a normal updatable Hermes install.

Use the repo helper:
```bash
/Users/zgbot/Desktop/forge_nps_v01/scripts/update_hermes_engine.sh
```

Then persist the new engine pointer in Forge:
```bash
cd /Users/zgbot/Desktop/forge_nps_v01
git status
git commit -am "chore: update hermes_engine"
git push
```

Notes:
- This updates `hermes_engine` from `origin/main` (NousResearch hermes-agent).
- Keep Forge-specific behavior in this repo (`dashboard/`, `core/`, `hermes_home/skills`, `hermes_home/profiles/forgehermes`), not by ad-hoc edits to upstream engine internals.

## Required Runtime Env
```bash
KIMI_API_KEY=nvapi-...
NIM_ENDPOINT=https://integrate.api.nvidia.com/v1/chat/completions
COMFYUI_PRIMARY=http://100.112.87.8:8188
LMSTUDIO_HOST=http://100.74.164.1:1234
FORGE_MEDIA_ROOT=/Users/zgbot/Desktop/FORGE_NPS_MEDIA
```

## LM Studio Load Controls
The Settings page LM Studio controls are real model-load controls. They are sent to LM Studio only when **Load Model** or **Reload Hermes/Vision** calls `POST /api/lmstudio/load`.

- `Context`: LM Studio `context_length`; larger values allow longer prompts/history and use more VRAM.
- `Batch`: LM Studio `eval_batch_size`; larger values can improve prompt prefill throughput and use more VRAM.
- `Flash Attention`: LM Studio `flash_attention`; enables the server-side optimized attention path when the loaded model/runtime supports it.
- `KV Cache GPU`: LM Studio `offload_kv_cache_to_gpu`; keeps KV cache on GPU for faster generation at higher VRAM cost.

Changing these fields and saving config does not modify an already-loaded model. Reload the model for changes to take effect. These settings do not change ComfyUI image/video quality and do not affect NVIDIA/Kimi cloud requests.

Optional hard gates:
```bash
FORGE_DEV_FALLBACK=false
FORGE_KIMI_REQUIRE_SELF_CHECK=false
FORGE_KIMI_MIN_DIRECTOR_SCORE=45
FORGE_LEARN_FROM_FALLBACK=false
```

## Canonical API Path
1. `POST /api/hermes/run-campaign`
2. `GET /api/shots`
3. `POST /api/audit/reprocess`
4. `POST /api/audit/remediate`
5. `GET /api/memory/health`

## Legacy Endpoints
These are intentionally disabled and return `410 legacy_disabled`:
- `/api/shots/dispatch-all`
- `/api/shots/dispatch`
- `/api/submit-recipe`
- `/api/inject-prompt`
- `/api/render`
- `/api/render/audit`

Compatibility shim:
- `POST /api/renders/audit-batch` only proxies to canonical re-audit if `shot_ids` is provided.

## Pipeline Behavior (Current)
1. Kimi planner generates strict JSON shot plan.
2. Kimi self-check returns score/status/risks.
3. Hermes compiler produces workflow-specific artifact:
   - `compiled_prompt`
   - `negative_prompt`
   - `skills_used`
   - model standard metadata
4. Spark renders each shot/workflow pair.
5. Vision audit writes pass/fail + issues + score.
6. Failed shots can be remediated into linked retries (`retry_of` lineage).

Campaign stops before Spark if Kimi fails and `FORGE_DEV_FALLBACK` is not enabled.

## Stream Event Types
- `kimi`
- `kimi_raw`
- `kimi_plan`
- `kimi_review`
- `hermes`
- `compiler`
- `spark`
- `memory`
- `warning`
- `error`
- `done`

## Key Files
- `/Users/zgbot/Desktop/forge_nps_v01/dashboard/forge_dashboard.py`
- `/Users/zgbot/Desktop/forge_nps_v01/core/hermes/pipeline/campaign_service.py`
- `/Users/zgbot/Desktop/forge_nps_v01/core/hermes/pipeline/director_service.py`
- `/Users/zgbot/Desktop/forge_nps_v01/core/hermes/pipeline/audit_service.py`
- `/Users/zgbot/Desktop/forge_nps_v01/core/prompts/prompt_compiler.py`

## Notes
- Workspace-local Hermes runtime is required for the app stack in this repo.
- Media rendered by Spark is served from `/external-renders/*` and stored under `FORGE_MEDIA_ROOT/images`.
