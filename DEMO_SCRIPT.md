# Forge NPS Demo Script (3 Minutes)

## Goal
Show one coherent path with hard provenance:
Kimi director plan -> Hermes prompt compile -> Spark render -> vision audit -> retry lineage.

## 0:00 - 0:30 Preflight
1. Launch app:
   `uvicorn dashboard.forge_dashboard:app --host 0.0.0.0 --port 7000`
2. Open `http://localhost:7000`.
3. In Settings confirm:
   - Kimi API key + `NIM_ENDPOINT`
   - Spark host (`COMFYUI_PRIMARY`)
   - LM Studio host/model
   - Save settings
   - Test Kimi connection

## 0:30 - 2:00 Live Campaign
1. Enter creative brief and choose workflows.
2. Click **Run Campaign**.
3. Narrate event stream in order:
   - `kimi` (planning start)
   - `kimi_raw` (raw director output excerpt)
   - `kimi_plan` (structured shot count)
   - `kimi_review` (self-check score/status)
   - `compiler` (Hermes profile + skills + model standard)
   - `spark` (dispatch + prompt_id)
   - `memory` (audit result)
4. Open a rendered shot and show:
   - Kimi plan + rationale
   - Hermes compiled prompt + negative prompt
   - profile + skills used
   - audit status/score/issues

## 2:00 - 2:40 Failure and Recovery
1. Filter to failed shots.
2. Select one failed shot.
3. Run **Re-Audit Selected**.
4. Run **Re-Render Failed**.
5. Show retry linkage:
   - original shot id
   - `retry_of`
   - remediated prompt
   - final audit outcome

## 2:40 - 3:00 Close
- Kimi is the director and planner.
- Hermes is the skill-driven prompt engineer and remediator.
- Spark is renderer.
- Vision model is quality gate.
- Memory is reusable provenance + health checks.

## Mentioned Endpoints
- `POST /api/hermes/run-campaign`
- `GET /api/shots`
- `POST /api/audit/reprocess`
- `POST /api/audit/remediate`
- `GET /api/memory/health`
