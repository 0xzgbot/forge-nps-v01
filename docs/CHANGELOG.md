# Changelog

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
- The previous `local_higgsfield_...` visible filename prefix is retained only on old files already rendered before this update.
- Added/updated validation for this batch:
  - `node --check dashboard/static/js/app.js`
  - `python3 -m py_compile dashboard/forge_dashboard.py core/affiliate/local_higgsfield.py`
  - `python3 -m pytest tests/test_local_higgsfield_adapter.py -q`

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

This entry summarizes the Forge NPS workspace changes made in the current dashboard refresh session.

Relevant commits:

- `3716bcc` - Refresh Forge dashboard UI
- `798e7e5` - Update prompt generation labels
- `4890e33` - Clean up dashboard controls
- `829b827` - Update dashboard UI and profile tooling

Current local workspace note:

- `dashboard/forge_dashboard.py` also contains an unpushed director fallback coverage change. It is documented below because it is present in the current workspace.

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

- Added [DESIGN.md](DESIGN.md) for Forge NPS product-launch video visual identity.
- Added this changelog and linked it from the documentation index and README.

### Validation Run

The following checks were run before the latest pushed commit:

```bash
node --check dashboard/static/js/app.js
python3 -m py_compile core/hermes/pipeline/profile_cli.py dashboard/api/prompt_builder.py dashboard/forge_dashboard.py
python3 -m pytest tests/test_profile_cli.py
```

Result: `tests/test_profile_cli.py` passed with `4 passed`.
