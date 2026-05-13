# Stability Checklist

Run before each demo pass.

## 0) Hermes Engine Pointer
- If you updated Hermes, run:
  - `/Users/zgbot/Desktop/forge_nps_v01/scripts/update_hermes_engine.sh`
- In Forge repo, confirm submodule pointer is committed/pushed:
  - `git status` should not show unintended `hermes_engine` drift.

## 1) Kimi Auth and Endpoint
- Confirm API key is present in Settings.
- Confirm endpoint ends with `/v1/chat/completions`.
- Run **Test Connection**.
- Expected: success. If `401`, stop and fix credentials first.

## 2) Spark Health
- Confirm `COMFYUI_PRIMARY` is correct and reachable.
- Optional: `GET /api/spark/stats`.
- Do not run demo if Spark queue/host is unstable.

## 3) LM Studio Health
- Confirm host/model in Settings.
- Confirm vision model exists if using local vision audit.
- Use **Test & Detect Models** to verify the LM Studio server is reachable.
- Use **Load Model** or **Reload Hermes/Vision** only to load the selected model. Forge does not override LM Studio load tuning; LM Studio uses its model defaults.

## 4) Media Path
- Confirm media root exists and is writable:
  - `/Users/zgbot/Desktop/FORGE_NPS_MEDIA/images`
- Confirm new renders appear under this folder.

## 5) Canonical API Health
- `GET /api/shots` returns `shots`, `count`, `active_campaign_id`.
- `GET /api/memory/health` returns health counts JSON.
- Run the repeatable smoke suite while the dashboard is active:
  - `python3 scripts/smoke_forge.py --base-url http://127.0.0.1:7000`
- For live render validation, opt in explicitly:
  - `python3 scripts/smoke_forge.py --base-url http://127.0.0.1:7000 --live-script`
  - `python3 scripts/smoke_forge.py --base-url http://127.0.0.1:7000 --live-campaign`
- `scripts/pre_push_hygiene.sh` runs the smoke suite automatically when Forge is already listening on `127.0.0.1:7000`.

## 6) Campaign Stream Smoke
- Run one short campaign.
- Confirm stream contains, in order:
  - `kimi`
  - `kimi_raw`
  - `kimi_plan`
  - `kimi_review` or `warning`
  - `compiler`
  - `spark`
  - `done`

## 7) Script Studio Smoke
- Open Script Studio.
- Paste a short brief.
- Click **Generate Videos**.
- Confirm the Jobs log progresses through:
  - `script`
  - `coverage`
  - `storyboard`
  - `frames`
  - `videos`
- Confirm the Script Studio Videos step shows generated start frames or completed clips.
- Confirm local storyboard file prefixes use the selected model name, not a generic backend label.
- Confirm `/api/script/pipeline/jobs/<job_id>` returns `project.video_shots`.
- If one storyboard frame times out, the job must keep completed frames and mark only the missing frame for retry. A completed job must not leave Script Studio with an empty Storyboard or Videos panel.

## 8) Audit and Retry Smoke
- Select at least one shot and run `POST /api/audit/reprocess`.
- Select a failed shot and run `POST /api/audit/remediate`.
- Confirm retry shot record has `retry_of`, `audit_status`, `audit_score`.

## 9) Legacy Route Guard
- Confirm these routes are not used by UI flow:
  - `/api/shots/dispatch-all`
  - `/api/shots/dispatch`
  - `/api/submit-recipe`
  - `/api/inject-prompt`
  - `/api/render`
  - `/api/render/audit`
- The smoke suite verifies each route returns `410 legacy_disabled`.

## 10) Full Demo Rehearsal
- Run a 5-image campaign.
- Run a 12-image carousel campaign.
- Run a 20-image larger campaign.
- Run a TikTok/vertical campaign.
- Run one Script Studio prompt through script, coverage, storyboard frames, and individual video clips.
- Create or reuse one Asset Vault package, attach it to Script Studio, and confirm the prompt text includes the package locks.
- Use `ffprobe` on completed Script Studio clips to verify video duration, codec, and whether an audio stream is present.
- Save artifact paths, campaign IDs, script IDs, job IDs, and limitations in the demo report before pushing.
