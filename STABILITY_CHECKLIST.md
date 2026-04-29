# Stability Checklist

Run before each demo pass.

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

## 4) Media Path
- Confirm media root exists and is writable:
  - `/Users/zgbot/Desktop/FORGE_NPS_MEDIA/images`
- Confirm new renders appear under this folder.

## 5) Canonical API Health
- `GET /api/shots` returns `shots`, `count`, `active_campaign_id`.
- `GET /api/memory/health` returns health counts JSON.

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

## 7) Audit and Retry Smoke
- Select at least one shot and run `POST /api/audit/reprocess`.
- Select a failed shot and run `POST /api/audit/remediate`.
- Confirm retry shot record has `retry_of`, `audit_status`, `audit_score`.

## 8) Legacy Route Guard
- Confirm these routes are not used by UI flow:
  - `/api/shots/dispatch-all`
  - `/api/shots/dispatch`
  - `/api/submit-recipe`
  - `/api/inject-prompt`
  - `/api/render`
  - `/api/render/audit`
