# Forge NPS Architecture

## Runtime Boundary
Canonical runtime for this project is entirely inside:
`~/Desktop/forge_nps_v01`

Primary server:
- `~/Desktop/forge_nps_v01/dashboard/forge_dashboard.py`
- Port `7000`

## Core Pipeline Services
- `~/Desktop/forge_nps_v01/core/hermes/pipeline/director_service.py`
  - Kimi structured planning and self-check.
- `~/Desktop/forge_nps_v01/core/hermes/pipeline/campaign_service.py`
  - Campaign orchestration and stream events.
- `~/Desktop/forge_nps_v01/core/hermes/pipeline/audit_service.py`
  - Re-audit and remediation/retry behavior.
- `~/Desktop/forge_nps_v01/core/hermes/pipeline/state_machine.py`
  - Canonical shot states and transitions.

## Data Flow
1. `POST /api/hermes/run-campaign`
2. Kimi returns strict shot-plan JSON.
3. Hermes compiler generates workflow-specific prompt artifact.
4. ComfyUI/Spark renders.
5. Vision audit stamps pass/fail.
6. Optional remediation creates linked retry shot.

## Canonical Endpoints
- `POST /api/hermes/run-campaign`
- `GET /api/shots`
- `POST /api/audit/reprocess`
- `POST /api/audit/remediate`
- `GET /api/memory/health`

## Stream Contract
Expected event types:
- `kimi`, `kimi_raw`, `kimi_plan`, `kimi_review`
- `hermes`, `compiler`, `spark`, `memory`
- `warning`, `error`, `done`

## Media Storage
- Root: `FORGE_MEDIA_ROOT` (default `~/Desktop/FORGE_NPS_MEDIA`)
- Served at `/external-renders/*`
- Images stored in `FORGE_MEDIA_ROOT/images`

## Legacy Policy
The following routes are intentionally disabled and return `410 legacy_disabled`:
- `/api/shots/dispatch-all`
- `/api/shots/dispatch`
- `/api/submit-recipe`
- `/api/inject-prompt`
- `/api/render`
- `/api/render/audit`

Compatibility route:
- `/api/renders/audit-batch` only forwards re-audit requests with `shot_ids`.

## Memory Contract
Events are stored in `data/hermes_memory/episodic/events.jsonl` using canonical event types only.
Health diagnostics are exposed at `GET /api/memory/health`.
