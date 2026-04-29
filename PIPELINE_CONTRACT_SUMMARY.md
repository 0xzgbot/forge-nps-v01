# Pipeline Contract Summary

## Canonical Runtime Flow
1. `POST /api/hermes/run-campaign`
2. Kimi returns strict structured shot plan.
3. Hermes compiles workflow-specific prompt artifact.
4. Spark renders and returns prompt id + image path.
5. Vision audit stamps pass/fail.
6. Failed shots can be re-audited or remediated into linked retries.

## Canonical Event Stream Types
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

## Required Shot Fields
- Base:
  - `id`, `campaign_id`, `shot_id`, `sequence`, `workflow_id`, `state`, `status`
- Kimi provenance:
  - `kimi_plan`
  - `raw_kimi_prompt` (or visual brief)
  - `kimi_rationale`
  - `kimi_constraints`
  - `kimi_raw_response`
- Hermes provenance:
  - `compiled_prompt`
  - `negative_prompt`
  - `workflow_profile`
  - `skills_used`
  - `compiler_version`
  - `model_standard_name`
  - `model_standard_version`
- Spark provenance:
  - `prompt_id`
  - `seed`
  - `image_path` and/or `image_url`
- Audit provenance:
  - `audit_model`
  - `audit_status`
  - `audit_score`
  - `audit_issues`
  - `audit_raw_response`
  - `audit_timestamp`
- Remediation lineage:
  - `retry_of`
  - `original_compiled_prompt`
  - `remediation_reason`
  - `remediated_prompt`
  - `remediation_model`

## Allowed Shot States
- `planned`
- `queued`
- `rendered`
- `audit_started`
- `audited_pass`
- `audited_fail`
- `remediation_started`
- `retry_queued`
- `retry_rendered`
- `final_pass`
- `final_fail`

## Canonical Memory Event Types
- `shot_planned`
- `render_attempt`
- `render_result`
- `audit_started`
- `audit_result`
- `remediation_started`
- `remediation_result`
- `retry_linked`
- `final_outcome`
- `import_completed`

## Legacy Policy
Hard-disabled (`410 legacy_disabled`):
- `/api/shots/dispatch-all`
- `/api/shots/dispatch`
- `/api/submit-recipe`
- `/api/inject-prompt`
- `/api/render`
- `/api/render/audit`

Compatibility shim:
- `/api/renders/audit-batch` is accepted only for `shot_ids` re-audit forwarding.

## Fallback Policy
- Production runs stop before Spark on Kimi failure.
- Dev fallback is opt-in only: `FORGE_DEV_FALLBACK=true`.
- Fallback events are excluded from learning unless `FORGE_LEARN_FROM_FALLBACK=true`.
