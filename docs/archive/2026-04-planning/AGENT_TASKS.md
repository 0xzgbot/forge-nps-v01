# Forge NPS Agent Tasks

Updated: 2026-04-29
Deadline: 2026-05-03

## Hard Scope For Hackathon Demo
Required:
1. Kimi planning is strict JSON and visible.
2. Hermes prompt compiler uses skills + model standards.
3. Spark render path is deterministic.
4. Vision audit + remediation lineage is real.
5. UI shows provenance per shot.

Not in scope:
- video pipeline productionization
- memory graph redesign
- legacy endpoint support

## Assignment Model
Agent A owns backend service and contract behavior.
Agent B owns frontend traceability behavior.
Agent E owns demo and submission docs.
Avoid overlapping edits to the same file in parallel.

## Priority Queue (P0 first)

### P0 Backend Reliability
- [ ] Validate `POST /api/hermes/run-campaign` against contract and stream events.
- [ ] Confirm Kimi failure blocks Spark unless `FORGE_DEV_FALLBACK=true`.
- [ ] Confirm canonical states are used on all shot records.
- [ ] Confirm `POST /api/audit/reprocess` updates audit fields on selected shots.
- [ ] Confirm `POST /api/audit/remediate` creates linked retry (`retry_of`) records.

### P0 Frontend Traceability
- [ ] Dashboard and Video views show the same live shot set.
- [ ] Per-shot pass/fail/retry badges render from backend fields.
- [ ] Clicking a shot reveals Kimi plan, compiler prompt, audit payload, retry lineage.
- [ ] Re-audit selected uses only `/api/audit/reprocess`.
- [ ] Re-render failed uses only `/api/audit/remediate`.

### P0 Demo Stability
- [ ] Save and verify Kimi endpoint + API key in Settings.
- [ ] Validate Spark host and workflow presence.
- [ ] Confirm media path is writable: `~/Desktop/FORGE_NPS_MEDIA/images`.
- [ ] Run one successful end-to-end campaign before recording.

## P1 Product Quality
- [ ] Tune Kimi planner prompt for better narrative coverage.
- [ ] Tune prompt profiles for Z-Image vs Flux differentiation.
- [ ] Add stricter audit issue labeling for anatomy and geometry failures.
- [ ] Add memory health gating in demo checklist.

## P1 Documentation
- [ ] Keep `/data/contracts/pipeline_contract.json` in sync with runtime.
- [ ] Refresh examples in `/data/contracts/examples/` after backend field changes.
- [ ] Keep demo script aligned to current UI labels.

## P2 Post-Submission
- [ ] Video tab workflow presets and generation queue.
- [ ] Script tab modernization.
- [ ] Memory graph UX polish.

## Verification Commands
```bash
cd ~/Desktop/forge_nps_v01
python3 -m py_compile dashboard/forge_dashboard.py core/hermes/pipeline/*.py
node --check dashboard/static/js/app.js
```

## Delivery Format For Any Agent
Each agent response must include:
1. files changed
2. behavior changed
3. verification performed
4. unresolved blockers
