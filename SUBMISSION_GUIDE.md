# Forge NPS Submission Guide

Event: Hermes Agent Creative Hackathon  
Deadline: 2026-05-03

## Product Positioning (Judge-Facing)
Forge NPS is a creative pipeline with explicit model roles:
1. Kimi = director planner (structured shot plans + quality self-check).
2. Hermes = skill-driven prompt compiler/remediator.
3. Spark = renderer.
4. Vision model = audit gate.
5. Memory = reusable event trace and health telemetry.

## What To Show (and In This Order)
1. Run campaign from a single brief.
2. Show Kimi raw + structured planning events.
3. Show Hermes compiler profile + skills + final prompt.
4. Show Spark render output with prompt id.
5. Show audit pass/fail.
6. Show remediation retry lineage on a failed shot.

If this order is clear, both technical credibility and novelty are obvious.

## Mandatory Proof Points In Demo Video
- Kimi endpoint configured and connection tested.
- Live `run-campaign` stream includes `kimi_raw`, `kimi_plan`, and `kimi_review`.
- Shot detail view includes:
  - Kimi plan fields
  - Hermes compiled prompt
  - skills used
  - audit status
  - retry lineage when present
- Memory health endpoint returns structured counts.

## Recommended Video Structure (60-90s)
1. Hook (5-8s): best visual outputs.
2. Pipeline run (35-45s): live campaign with stream callouts.
3. Failure handling (15-20s): re-audit + remediate + retry_of.
4. Close (10s): one-line model-role summary.

## Tweet/Writeup Checklist
- Mention Kimi and Hermes roles explicitly.
- Mention Spark rendering and vision audit gate.
- Link how memory is used (health + event trace).
- Keep copy concrete; avoid generic "AI platform" language.

## Stability Gate Before Recording
Run `/Users/zgbot/Desktop/forge_nps_v01/STABILITY_CHECKLIST.md` top-to-bottom.

## Canonical References
- `/Users/zgbot/Desktop/forge_nps_v01/README.md`
- `/Users/zgbot/Desktop/forge_nps_v01/DEMO_SCRIPT.md`
- `/Users/zgbot/Desktop/forge_nps_v01/PIPELINE_CONTRACT_SUMMARY.md`
- `/Users/zgbot/Desktop/forge_nps_v01/data/contracts/pipeline_contract.json`
