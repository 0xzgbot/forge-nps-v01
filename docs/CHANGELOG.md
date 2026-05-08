# Changelog

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
- Kept Home, Ideas, Characters, Script, Products, Renders, Memory, and Settings as the active sidebar navigation.
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
