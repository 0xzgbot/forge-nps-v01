# Deep Sweep Report (2026-04-29)

## Scope
- Repo: `/Users/zgbot/Desktop/forge_nps_v01`
- Sweep targets: uncommitted churn, secrets, duplicate tests, dead code signals, doc/code drift

## 1) Uncommitted Churn
- Total pending entries: `479`
- Churn concentration by top-level path:
  - `hermes_home`: `414`
  - `core`: `21`
  - `workflows`: `12`
  - `dashboard`: `12`
  - `data`: `8`
  - `hermes_engine` (submodule pointer): `1`
- Practical conclusion:
  - Most risk is accidental churn in `hermes_home`.
  - App/runtime changes are concentrated in `core`, `dashboard`, `data`, and docs.

## 2) Secrets Sweep
- Hardcoded NVIDIA key in `data/config.json` has already been scrubbed (`set_in_env_only` placeholders).
- `nvapi-*` style key material was detected only in session artifacts under `hermes_home/profiles/trading/sessions/` (not in active app runtime config).
- Added ignore rules to reduce accidental commit of local runtime/session artifacts (see `.gitignore` updates).

## 3) Duplicate Tests
- No exact duplicate test file bodies were found in active repo paths when excluding:
  - `.claude/worktrees`
  - `.venv` / `venv`
  - `hermes_engine`
- Near-duplicate/experimental parser test files remain under `pipelines/generation/`:
  - `kimi_payload_parser_test.py`
  - `kimi_payload_parser_test_v2.py`
  - `kimi_payload_parser_test_v3.py`
  - `test_kimi_payload_parser.py`
- These are standalone and not imported by runtime code.

## 4) Dead Code Signals (Heuristic)
- Likely low-coupling modules detected by reference scan (candidate review, not auto-delete):
  - `core/assembly/timeline_assembler.py`
  - `core/dispatch/comfy_remediation_harness.py`
  - `core/genesis/*`
  - `core/routing/prompt_enhancer.py`
  - `pipelines/generation/*_test_v2.py`, `*_test_v3.py`
- These should be triaged by runtime entrypoint reachability before removal.

## 5) Doc/Code Drift
- Endpoint references in current docs match backend route definitions for the documented API set.
- No missing documented `/api/*` endpoint references were found against `dashboard/forge_dashboard.py` + `dashboard/memory_api.py`.

## 6) Build Health Checks
- `python3 -m py_compile` on changed non-`hermes_home`/non-`hermes_engine` files: **PASS**
- One hard breakage was found and repaired during sweep:
  - `core/bridge/cosmos_client.py` had an `IndentationError` at line 1 and was restored to repository version.

## 7) Cleanup Actions Applied
- `.gitignore` expanded for:
  - local venv folders
  - render output folders
  - volatile `hermes_home` runtime/session DB/log artifacts
  - local sweep artifacts under `private/artifacts/`
- No media files were altered.
- No workflow JSON content was edited.

## Recommended Next Cleanup Step
- Separate intentional product changes from `hermes_home` profile churn before final release tag:
  1. Keep app/runtime changes (`core`, `dashboard`, `data/contracts`, `data/prompt_profiles`, docs).
  2. Explicitly decide whether `hermes_home` profile/skills deltas are product assets or local churn.
  3. Commit in two units if needed:
     - runtime/product commit
     - profile bundle commit
