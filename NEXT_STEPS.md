# Forge NPS — Next Steps

Date: 2026-04-29
Deadline: 2026-05-03

## Today: Critical Order
1. Lock canonical pipeline behavior (Kimi -> Hermes -> Spark -> Audit -> Retry).
2. Lock frontend traceability to those backend fields.
3. Record deterministic demo path.

## P0 (Must Finish First)

### 1) Kimi/Hermes Contract Integrity
- Confirm run-campaign stream emits `kimi_raw`, `kimi_plan`, `kimi_review`, `compiler`, `spark`, `done`.
- Confirm no Spark dispatch occurs on Kimi auth/parse failure unless `FORGE_DEV_FALLBACK=true`.
- Confirm each shot keeps:
  - `kimi_plan`
  - `compiled_prompt`
  - `negative_prompt`
  - `skills_used`
  - audit fields

### 2) Audit + Retry Reliability
- Confirm `POST /api/audit/reprocess` returns updates for selected shot IDs.
- Confirm `POST /api/audit/remediate` creates retry shot with `retry_of`.
- Confirm retry shot gets final pass/fail audit status.

### 3) UI Clarity
- Ensure pass/fail/retry indicators render from shot data.
- Ensure details panel shows Kimi plan + Hermes prompt + audit data.
- Ensure campaign placeholders do not hide real media shots.

## P1 (Same Day, After P0)

### 4) Prompt Quality Improvements
- Improve prompt profile separation:
  - `spark_image_z_image*` profiles for photoreal/commercial look.
  - `spark_image_flux2_text_to_image*` profiles for stylized/art direction look.
- Validate model standards are applied and visible per shot.

### 5) Memory Health Signal
- Use `GET /api/memory/health` before demo run.
- Clean up unknown event-type inflation and fallback noise.

## P2 (After Demo Build Is Stable)
- Video pipeline production behavior.
- Script tab legacy cleanup.
- Memory graph UX polish.

## Quick Verification
```bash
cd ~/Desktop/forge_nps_v01
python3 -m py_compile dashboard/forge_dashboard.py core/hermes/pipeline/*.py
node --check dashboard/static/js/app.js
curl -s http://localhost:7000/api/memory/health
curl -s http://localhost:7000/api/shots
```
