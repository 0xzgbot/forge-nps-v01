# Commit Scope Plan (2026-04-29)

## Safe-to-Ship First
- `core/`
- `dashboard/`
- `data/contracts/`
- `data/prompt_profiles/`
- `workflows/spark_image_*.json`
- top-level docs (`README.md`, `DEMO*.md`, `ARCHITECTURE.md`, `NEXT_STEPS.md`, `AGENT_TASKS.md`)

## Hold / Review Before Shipping
- `hermes_home/` (currently dominant churn source)
- `hermes_engine` submodule pointer (currently `-dirty`)

## Why Split
- Prevent accidental inclusion of local profile/session churn.
- Keep hackathon runtime deterministic and reviewable.
- Preserve ability to package hermes profile deltas intentionally in a second commit.
