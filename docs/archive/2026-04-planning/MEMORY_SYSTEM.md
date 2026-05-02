# Forge NPS Memory System

## Purpose
Memory is the trace layer for the pipeline, not a placeholder feature.
It records what happened during planning, rendering, auditing, and remediation.

## Primary Event Store
- File: `/Users/zgbot/Desktop/forge_nps_v01/data/hermes_memory/episodic/events.jsonl`
- Format: append-only JSONL

## Canonical Event Types
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

## Required Metadata Per Event
- `timestamp`
- `event_type`
- `shot_id`
- `campaign_id`
- `workflow_id`
- `pipeline_mode`
- `source`
- optional `success` and additional payload fields

## Health Endpoint
`GET /api/memory/health` returns:
- `total_events`
- `unknown_event_types`
- `orphan_remediation_events`
- `fallback_events`
- `shots_missing_audit_after_render`

Use this endpoint as the memory integrity gate before demo runs.

## Learning Guardrails
- Fallback-source events are not included in learning by default.
- Enable only when needed: `FORGE_LEARN_FROM_FALLBACK=true`.

## What Counts As Valid Learning
A campaign contributes valid learning only when:
1. render attempt/result is recorded,
2. audit result is recorded,
3. final outcome is recorded,
4. if retried, `retry_linked` is present.

## Canonical References
- `/Users/zgbot/Desktop/forge_nps_v01/PIPELINE_CONTRACT_SUMMARY.md`
- `/Users/zgbot/Desktop/forge_nps_v01/data/contracts/pipeline_contract.json`
