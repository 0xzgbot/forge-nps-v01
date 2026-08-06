# Changelog

## 2026-08-06 - Rebrand: Forge NPS → Cinesmith

- **Full rename** across app, docs, skills, and marketing: `Forge NPS` → `Cinesmith` (formerly "Neural Production Studio").
- Code/module renames: `forge_dashboard.py` → `cinesmith_dashboard.py`, `forge_env.py` → `cinesmith_env.py`, `forge_run.py` → `cinesmith_run.py`, `launch_forge.sh` → `launch_cinesmith.sh`, `smoke_forge.py` → `smoke_cinesmith.py`, `forge_nexus` → `cinesmith_nexus`, profile `forgehermes` → `cinesmith`, all `forge-*.js/css` → `cinesmith-*`, marketing assets → `cinesmith-*`.
- Env vars: `FORGE_*` → `CINESMITH_*` (legacy `FORGE_*` values and `FORGE_NPS_MEDIA` sibling dir still honored for backward compatibility).
- Skill renames: `forge-nps-evolution-plan` → `cinesmith-evolution-plan`, `forge-*-protocol` skill dirs → `cinesmith-*-protocol`.
- MCP tool names: `forge_query/context/impact/trace` → `cinesmith_query/context/impact/trace`; `ForgeAPIError` → `CinesmithAPIError`; JS globals `ForgeCore` → `CinesmithCore` etc.
- Repo folder `forge_nps_v01` intentionally unchanged (rename at your discretion); sibling media dir `FORGE_NPS_MEDIA` still auto-detected, new name `CINESMITH_MEDIA`.

## 2026-07-16 - World-class ease: coach, samples, hang fixes, series

- **Getting-started coach** on Agency (`cinesmith-coach.js` + `cinesmith-polish.css`): adaptive next steps from readiness + milestones, hide/restore, pulse targets
- **Sample EP briefs** chips (neon courier, travel, product, short film) + ⌘K actions for sample brief / sheet from photo / First→Last / new episode / restore coach
- **Onboarding** 3-step path card; Enter Agency lands on Agency home; richer keyboard help
- **Create hub** 15-minute path + sample_briefs + tips from `/api/product/create-hub`
- **F3 auto character sheet:** fix missing-character 404; sheet workflow `04_*` + alias for legacy `02_*`
- **D3 first/last frame** E2E; **E5 multi-episode** series APIs + Stories UI
- **Spark recovery docs** full guide at `/static/docs/DESKTOP_SPARK_PACKAGE.md`; preflight character-sheet check
- Still **uncommitted** (no git commit per request)

## 2026-07-09 - Multi-agent polish pass (isolation, upload, theme, compile, cost, A/B)

- **A9 Hermes isolation:** vendored CLI launcher + `HERMES_HOME` isolation for profile CLI and dashboard profile chat; bare PATH `hermes`/`cinesmith` rewritten away
- **F2 Multi-upload:** drag-drop multi-file refs on Characters + Asset Vault (`cinesmith-characters.js`, `cinesmith-assets.js`)
- **F4 Package → campaign:** one-click attach package identity pack to active campaign
- **H4/H5:** responsive mobile shell + dark/light theme toggle (`cinesmith-theme.*`, `cinesmith-responsive.css`)
- **C7 Parallel compile:** bounded concurrent shot compile with structured per-shot errors + Failed shots UI panel
- **J4 Failure memory:** auto-consolidate after N pipeline failures into durable Hermes memory summaries
- **G5 Cost meter:** cloud image spend counter (OpenAI/Gemini) with readiness chips + Settings panel
- **H9 A/B compare:** side-by-side frame compare, winner preference, review-log integration
- Stories **Assemble / Export package** CTA polish; roadmap checkboxes synced
- Tests: **161 passed** (full suite)

## 2026-07-08 - Client review: approve / reject / Hermes remediate

- Frame.io-style **client review** on lightbox: Approve · Needs changes · Reject + remediate
- Keyboard: **A** approve · **R** reject+remediate · **C** needs changes · **←/→** frames
- API: `POST /api/product/review`, `GET /api/product/review/queue`
- Review state on shots (`review_status`, badges on filmstrip), log at `data/reviews/review_log.jsonl`
- Reject can call existing Hermes audit remediation service

## 2026-07-08 - Adobe-tier Agency: EP console, ⌘K, production timeline

- **Executive Producer Console** on Agency home: production brief, Hermes chat (improve brief / shot list / story beats), live production timeline
- **Command palette** (⌘/Ctrl+K): navigate desks, run campaign, produce story, export, scorecard, stack health
- Production timeline stages: Brief → Plan → Critique → Compile → Render → Audit → Memory → Done
- Pro handoff strip: export package + continuity score from Agency
- Brand chrome: Cinesmith Agency sidebar mark; premium primary CTAs
- API: `GET /api/product/agency-desk` desk summary
- Scripts: `cinesmith-agency.js`

## 2026-07-08 - Hermes-first product reframe (not a script app)

- Product vision: [PRODUCT_VISION.md](PRODUCT_VISION.md) — agency runtime, not script runner
- UI renames: **Script Studio → Stories**, Create → **Agency**, primary CTAs **Run with Hermes** / **Produce with Hermes**
- Agency home: live brief box → one-click live image campaign or multi-beat story
- Create hub / suggestions / wizard / help copy reframed around Hermes real-time work
- Internal APIs may still use `/api/script/*` and `data/scripts/` for compatibility; users never see “script app” language

## 2026-07-08 - Domain router split for dashboard API

- Mounted domain APIRouters under `dashboard/routes/`:
  `system`, `campaigns`, `script`, `hermes`, `characters`, `assets`, `memory`, `video`, `ideas`, `legacy` (+ existing `product`)
- Handlers remain in `cinesmith_dashboard.py` (behavior-identical); routers only register paths/tags
- `GET /` and WebSockets stay on the main app; static mounts unchanged
- Docs: [DASHBOARD_ROUTERS.md](DASHBOARD_ROUTERS.md)

## 2026-07-08 - Product surface: Create hub, export, scorecard, modular routes

- Added modular package layout:
  - `dashboard/routes/product.py` — Create hub, story export, media probe, scorecard, wizard, queue summary, suggestions
  - `dashboard/errors.py` — structured `CinesmithAPIError` responses (`code`, `hint`, `recovery`)
  - `core/script_projects.py`, `core/story_export.py`, `core/media_probe.py`, `core/consistency_scorecard.py`, `core/memory_suggestions.py`
- Frontend modules: `cinesmith-core.js` (API + errors + toasts), `cinesmith-product.js` (hub, wizard, export, audio badges)
- **Create** workspace: unified entry for Images / Full Story / Image→Video / Characters with queue strip + memory suggestions
- **Export Story Package** ZIP (manifest, captions, frames, clips, audio honesty)
- **Consistency Scorecard** for Script Studio projects
- **Audio honesty** badges on video cells via `ffprobe`
- Multi-step **setup wizard** (server-persisted in `data/first_run_wizard.json`)
- Contract tests (`tests/test_api_contracts.py`) + product tests (`tests/test_product_surface.py`)
- Smoke suite covers new product routes and export

## 2026-07-08 - Polish pass: isolation, readiness, presets, onboarding

- Added `core/cinesmith_env.py` for portable media roots and **Hermes isolation** (repo `hermes_home/` only; never silent `~/.hermes`).
- Dashboard applies isolation at import; Hermes profile chat and profile CLI subprocesses use isolated env.
- Added `GET /api/system/readiness` for first-run health (isolation, media, Spark, LM Studio).
- Added `scripts/launch_cinesmith.sh` one-command launcher with isolation + media defaults.
- Clarified env validation: `scripts/validate_env.py` (setup.py remains a compatibility wrapper).
- UI: system readiness chips, first-run onboarding, image + story presets, keyboard shortcuts (⌘/Ctrl+Enter, `?`, 1–7), global toasts.
- Portable media default: sibling `CINESMITH_MEDIA` or `<repo>/media`.
- Tests: relative repo paths (no hard-coded `~/...`); new `tests/test_cinesmith_env.py`.
- Smoke suite checks readiness + isolation.
- Master backlog: [docs/POLISH_ROADMAP.md](POLISH_ROADMAP.md).

## 2026-05-13 - Goal validation pass, batch queueing, and demo-readiness report

- Added [DEMO_READINESS_REPORT.md](DEMO_READINESS_REPORT.md) with live validation results for the full polish/testing goal.
- Verified the current runtime stack with LM Studio Director, Spark/Comfy health, media reindexing, and Script Studio persistence.
- Confirmed `flux2_dev` and `flux2_klein` as available local storyboard models.
- Confirmed `z_image` and `z_image_turbo` are unavailable after their model files were removed; local storyboard provider preflight now reports exact missing files instead of failing later in the render.
- Changed campaign image rendering so compiled jobs are prepared first, then submitted to ComfyUI as one grouped queue before polling results.
- Added cancellation-aware render failure wording so cancelled pending jobs are not reported as timeouts.
- Fixed retry audit state transitions so remediation renders can move from retry audit into final pass/fail without `invalid_transition` errors.
- Verified a one-click Script Studio run from short prompt to script package, coverage, Flux2.Dev storyboard start frames, and two LTX image-to-video clips.
- Verified generated Script Studio clips contain H.264 video and AAC audio streams with `ffprobe`.
- Verified Asset Vault package data is injected into Script Studio storyboard prompts.
- Added `scripts/smoke_cinesmith.py` for repeatable dashboard/API smoke checks.
- Updated `scripts/pre_push_hygiene.sh` to run the smoke suite when the local dashboard is already active.
- Expanded the stability checklist with full demo rehearsal steps, smoke-suite commands, storyboard/video visibility checks, and ffprobe verification.
- Validation completed:
  - `python3 -m pytest tests -q` -> `83 passed`
  - `python3 -m pytest tests/test_full_pipeline.py tests/test_script_studio_persistence.py tests/test_resilience.py -q` -> `9 passed`
  - `python3 scripts/smoke_cinesmith.py --base-url http://127.0.0.1:7000` -> passed
  - `node --check dashboard/static/js/app.js` -> passed
  - Python compile checks for changed backend files -> passed

## 2026-05-12 - One-click Script Studio video, Asset Vault handoff, and storyboard provider cleanup

- Added a job-based Script Studio pipeline for **Generate Videos** from a short brief.
- The default Script Studio flow now runs: brief -> locked script package -> coverage -> storyboard plan -> individual 1080p start frames -> LTX image-to-video jobs.
- Rewired the Brief primary action away from the partial package/storyboard path and into `POST /api/script/pipeline/start`.
- Hid advanced pipeline controls from the primary UI so the main Script Studio workflow is one click.
- Script Studio now shows generated start frames and completed clips in its own **Videos** step instead of requiring users to open the global Videos page to finish the workflow.
- The backend now filters video generation to `storyboard_start_frame` records only, preventing coverage-only records from being queued without rendered images.
- Added persistent script project state for pipeline jobs, storyboard panel jobs, video shot records, and active job logs.
- Simplified package exposure: package data remains saved for continuity and debugging, but it is no longer treated as a primary user step.
- Added readiness cards for coverage and storyboard so users can see what source package/plan is loaded.
- Added Asset Vault packaging for product, brand, logo, character reference, font, and style continuity assets used by storyboard generation.
- Added storyboard image provider selection and Settings support for local Spark models, OpenAI image generation, and Gemini/Nano Banana.
- Local storyboard providers now include Spark / Flux2.Dev, Spark / Flux2 Klein, Spark / Z-Image, and Spark / Z-Image Turbo.
- Storyboard renders now default to individual production keyframes instead of multi-panel storyboard pages.
- Raised default storyboard frame generation to `1920x1080` / `1080p`.
- Changed storyboard prompts to explicitly request image-to-video start frames with no text, captions, labels, grids, contact sheets, or page layouts.
- Page render / assemble actions remain available only as advanced proof actions.
- Local Spark storyboard output filenames now use the selected model prefix, for example `flux2_dev_...`, `flux2_klein_...`, `z_image_...`, or `z_image_turbo_...`.
- The previous `local_spark_media_...` visible filename prefix is retained only on old files already rendered before this update.
- Added/updated validation for this batch:
  - `node --check dashboard/static/js/app.js`
  - `python3 -m py_compile dashboard/cinesmith_dashboard.py core/affiliate/local_spark_media.py`
  - `python3 -m pytest tests/test_local_spark_media_adapter.py -q`

## 2026-05-09 - Video controls, image-count clarity, and push hygiene

- Renamed the left navigation entry from **Home** to **Images** and placed **Videos** directly beneath it.
- Restored **Characters** as a left-navigation tab while keeping the persistent lower character thumbnail rail removed.
- Renamed **Renders** to **Videos** for the video workspace.
- Removed Hermes Chat from the Videos tab so the page focuses on video generation controls.
- Added a compact video-generation control surface with model, duration, quality/resolution, aspect-ratio, and FPS inputs.
- Added a **25 Sec** duration option for video generation.
- Removed visible Retake and IC-LoRA mode choices from the main Videos tab until those workflows have complete, explicit controls.
- Wired video duration, FPS, resolution, and aspect-ratio values into the ComfyUI workflow payload mutator where matching node inputs exist.
- Added an Images target-count pill and now send `target_shots` explicitly with `/api/hermes/run-campaign`.
- Expanded Kimi shot-count inference so explicit requests like `20 images`, `Images: 12`, `Need eight stills`, or `30 shots` are respected.
- Added `tests/test_director_shot_count.py` to guard the image-count inference behavior.
- Replaced hard-coded private semantic-audit endpoints with `KIMI_SEMANTIC_AUDIT_URL` / `KIMI_SEMANTIC_AUDIT_MODEL` environment-driven defaults.
- Added `scripts/pre_push_hygiene.sh` to check tracked files for local runtime config, generated render artifacts, obvious secret tokens, and private/local IP addresses before a public push.

## 2026-05-07 - TikTok platform skill, hooks, and carousel export

- Added prompt-driven TikTok platform detection through `core/hermes/platform_skills.py`.
- TikTok/vertical-short briefs now activate 1080x1920, 9:16, 8-15s, hook-first, bottom-third caption-safe constraints.
- Added visible dashboard platform state with Auto Detect, Force TikTok 9:16, and Disable Platform Skill modes.
- Added optional Series Continuity control; TikTok briefs mentioning a series, recurring character, or girl-next-door character automatically receive continuity-lock guidance.
- Added TikTok hook generation in the Ideas tab, backed by `data/platform_skills/wholesome_audio_ideas.json`.
- Added new skill pack entries: `tiktok_vertical_platform`, `girl_next_door_realism`, `sunlit_travel_cinematography`, `heartwarming_storytelling`, and `soft_pastel_animation_lighting`.
- Added low-watch-time review detection that can revise the first shot with stronger first-3-second hook guidance.
- Added one-click carousel export for selected stills/clips with `captions.txt` and `manifest.json`.

## 2026-05-05 / 2026-05-06 - Dashboard UI, profile tooling, and script fallback coverage

This entry summarizes the Cinesmith workspace changes made in the current dashboard refresh session.

Relevant commits:

- `3716bcc` - Refresh Cinesmith dashboard UI
- `798e7e5` - Update prompt generation labels
- `4890e33` - Clean up dashboard controls
- `829b827` - Update dashboard UI and profile tooling

Current local workspace note:

- `dashboard/cinesmith_dashboard.py` also contains an unpushed director fallback coverage change. It is documented below because it is present in the current workspace.

### Dashboard Navigation and Layout

- Refreshed the dashboard command center with a denser dark production-console layout.
- Added an **Ideas** tab with a Hermes idea board / kanban view grouped by production stage.
- Removed the standalone **Models** tab. Model and provider configuration remain in Settings.
- Kept Home, Ideas, Characters, Script, Asset Vault, Renders, Memory, and Settings as the active sidebar navigation.
- Added responsive/mobile handling for the idea board and dashboard panes.

### Prompt Generation Controls

- Renamed the main input label from **Creative Brief** to **Prompt**.
- Renamed the primary action from **Run Campaign** to **Generate Images**.
- Made the prompt textarea taller and changed its interior to a lighter dark blue.
- Made the **Prompt** label larger and bold.
- Removed the main-dashboard **Re-Audit Selected** control.
- Removed the optional world-bible path input from the prompt toolbar; campaign requests now send an empty `bible_path` unless another caller provides one.
- Changed the empty prompt validation message to `Please enter a prompt`.

### Model Toggle Behavior

- Moved **Turbo** into the same pill/bubble as **Flux2.Dev**.
- Kept **Turbo** on the same line as **Flux2.Dev** with a visual divider.
- Enforced the dependency in JavaScript: Turbo is unchecked, disabled, and ignored unless Flux2.Dev is checked.
- Preserved **Flux2 Klein** as an independent model toggle.

### Character / Identity Language

- Changed visible **Anchor/Anchors** terminology to **Character/Characters** across the dashboard.
- Updated identity asset role labels so the `anchor` backend value displays as **Character** in the UI.
- Updated logs and preview text from anchor assets to character assets.
- Kept internal API field names such as `anchor_image_ids` and `value="anchor"` unchanged for compatibility.
- Added character management UI surfaces for character creation, character image upload, DNA preview/editing, and render history.
- Added `/api/characters/spark-render` for Spark-backed character renders and improved character render submission error handling.

### Idea Board

- Added `GET /api/hermes/idea-board` on the dashboard backend.
- The endpoint returns Hermes-provided board data when Hermes exposes a compatible board method.
- If Hermes has no board method, the backend builds a fallback board from `_SHOTS_STORE`.
- The frontend also falls back to `/api/shots` if `/api/hermes/idea-board` returns a 404, so older running backends do not break the Ideas tab.

### Script and Director Workflow

- Added `/api/script/develop` to create a locked script package with acts, scenes, beats, continuity, edit intent, and transition strategy.
- Added deterministic script-package fallback generation when the Director API is unavailable.
- Added local director fallback coverage from a locked script package for shot-list generation after Director API failure.
- The fallback coverage preserves scene IDs, beat IDs, wardrobe, props, screen direction, locations, time of day, and edit role.

### Profile Endpoint Tooling

- Updated `core/hermes/pipeline/profile_cli.py` so OpenAI-compatible base URL normalization preserves explicit custom endpoint ports.
- Added `tests/test_profile_cli.py` for profile base URL normalization and explicit custom endpoint preference.

### Prompt Builder and Product Banks

- Fixed product-bank loading in `dashboard/api/prompt_builder.py` so product mode reads from `data/product_banks` instead of a nested character-bank path.

### Documentation and Design Assets

- Added [DESIGN.md](DESIGN.md) for Cinesmith product-launch video visual identity.
- Added this changelog and linked it from the documentation index and README.

### Validation Run

The following checks were run before the latest pushed commit:

```bash
node --check dashboard/static/js/app.js
python3 -m py_compile core/hermes/pipeline/profile_cli.py dashboard/api/prompt_builder.py dashboard/cinesmith_dashboard.py
python3 -m pytest tests/test_profile_cli.py
```

Result: `tests/test_profile_cli.py` passed with `4 passed`.
