# Pipeline Contract Summary

## Canonical Runtime Flow
1. `POST /api/hermes/run-campaign`
2. Hermes campaign intake returns structured context.
3. Kimi returns strict structured shot plan.
4. Kimi returns planning/self-check critique.
5. Hermes compiles workflow-specific prompt artifact.
6. Spark renders and returns prompt id + image path.
7. Vision audit stamps pass/fail.
8. Failed shots can be re-audited or remediated into linked retries.

## Script Studio Runtime Flow

Script Studio is also canonical. It is job-based and persists progress into saved script projects.

1. `POST /api/script/pipeline/start`
2. Script package is created or loaded.
3. Coverage is generated from the locked package.
4. Storyboard plan is generated.
5. Individual storyboard start frames are rendered at 1080p.
6. Frames are exported as `storyboard_start_frame` shot records.
7. Only `storyboard_start_frame` records are queued for image-to-video.
8. `GET /api/script/pipeline/jobs/{job_id}` returns logs and the current saved project.
9. Script Studio Videos displays `project.video_shots` start frames and clips directly.

Manual page proofs are not part of the default contract. They are advanced storyboard artifacts only.

## Canonical Event Stream Types
- `profile`
- `pipeline_timing`
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

## Expected Early Campaign Stream

The run button is considered wired when the stream reaches at least:

1. `backend_stream_open`
2. `Hermes / Campaign Intake starting.`
3. `Hermes / Campaign Intake complete.`
4. `Kimi: Generating shot list...`
5. `kimi_director_plan`
6. `kimi_raw`

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
- Script/video provenance:
  - `source` = `storyboard_start_frame`
  - `start_frame_url`
  - `video_prompt`
  - `video_status`
  - `video_prompt_id`
  - `video_url` when complete
  - `storyboard_board_id`
  - `storyboard_panel_index`
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

## Memory Health

Primary event store:

```text
~/Desktop/cinesmith_v01/data/hermes_memory/episodic/events.jsonl
```

`GET /api/memory/health` is the memory integrity gate and should report:

- `total_events`
- `unknown_event_types`
- `orphan_remediation_events`
- `fallback_events`
- `shots_missing_audit_after_render`

Fallback-source events are excluded from learning unless `CINESMITH_LEARN_FROM_FALLBACK=true`.

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
- Dev fallback is opt-in only: `CINESMITH_DEV_FALLBACK=true`.
- Fallback events are excluded from learning unless `CINESMITH_LEARN_FROM_FALLBACK=true`.
