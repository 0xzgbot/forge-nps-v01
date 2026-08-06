# Cinesmith — Master Polish Roadmap

**Goal:** Make Cinesmith the most polished, reliable workflow for generating images, videos, and full stories — without conflicting with a user's global Hermes install.

**Rule:** Cinesmith always uses **repo-local** `hermes_home/` + vendored `hermes_engine/`. Never write to `~/.hermes` unless the user explicitly opts in.

---

## Status legend

- `[x]` done in this pass
- `[~]` partial / improved
- `[ ]` remaining (safe next work)

---

## A. Foundation & isolation

- [x] A1. Central path/env module (`core/cinesmith_env.py`)
- [x] A2. Portable `CINESMITH_MEDIA_ROOT` default (sibling folder or `media/`)
- [x] A3. Hermes isolation helpers (HERMES_HOME + launcher, never bare `hermes` without env)
- [x] A4. Wire dashboard Hermes chat to isolation helpers
- [x] A5. Wire profile CLI subprocess path to set `HERMES_HOME`
- [x] A6. One-command launcher (`scripts/launch_cinesmith.sh`) that exports isolation env
- [x] A7. System readiness API (`GET /api/system/readiness`)
- [x] A8. Unit tests for isolation + portable paths
- [x] A9. Audit every subprocess that could call Hermes without HERMES_HOME
- [x] A10. Promo kit README defaults to repo hermes_home (not ~/.hermes)

## B. Cleanup & portability

- [x] B1. Remove root remediation dump JSON clutter
- [x] B2. Rename/clarify env validation (`scripts/validate_env.py`; keep `setup.py` as wrapper)
- [x] B3. Make pytest paths relative to repo root (no hard-coded `~/...`)
- [x] B4. `.env.template` documents portable media root + Hermes isolation
- [~] B5. Docs still mention machine-local paths in historical reports (ok; install guide media defaults made portable)
- [x] B6. Slim publish bundle notes: `docs/SHIP_BUNDLE.md`, `scripts/cinesmith_ship_excludes.txt`, Desktop+Spark package guide + preflight + package launch mode (`docs/DESKTOP_SPARK_PACKAGE.md`, `scripts/preflight_desktop_spark.py`, `CINESMITH_PACKAGE_MODE` / `--package`)

## C. Image workflow (stills)

- [x] C1. Prompt presets / quick-start cards (cinematic, product, character, TikTok, story stills)
- [x] C2. Keyboard shortcut: Ctrl/Cmd+Enter runs Generate Images from prompt box
- [x] C3. Live system readiness strip (Spark / Director / Hermes / Media)
- [x] C4. Clearer campaign progress stages with approximate percent + toast on done
- [x] C5. Empty gallery state copy (filmstrip: brief Hermes → Run with Hermes; Spark fills stills)
- [x] C6. Domain APIRouters for system/campaigns/script/hermes/characters/assets/memory/video (handlers still in cinesmith_dashboard; next: move bodies to services)
- [x] C7. Parallel compile with structured per-shot errors in UI

## D. Video workflow

- [x] D1. Video quick presets (9:16 / 16:9 / 1:1, duration chips already exist — wire presets)
- [x] D2. Videos empty state when no start frames (select Images/Stories stills or text-to-video prompt)
- [x] D3. First/last frame mode end-to-end controls (Retake/IC-LoRA remain advanced)
- [x] D4. Timeline assemble + export story package ZIP (Script Studio export)
- [x] D5. Audio honesty: surface whether clip has audio stream (probe + badges)

## E. Full story workflow (Script Studio)

- [x] E1. Story starter presets (short film beat, product spot, travel series, TikTok story)
- [x] E2. One-click Generate Videos remains primary path; presets fill brief
- [x] E3. Progress job status panel polish (readiness poll + toast on complete)
- [x] E4. Unified project export (script + frames + clips + captions + manifest ZIP)
- [x] E5. Multi-episode series continuity UI
- [x] E6. Consistency scorecard across storyboard frames / shots

## F. Characters & Asset Vault

- [x] F1. Onboarding points users at Characters + Assets
- [x] F2. Drag-drop multi-upload for references
- [x] F3. Auto character sheet from 1 photo
- [x] F4. Package → campaign identity one-click attach

## G. Settings, health, first-run

- [x] G1. First-run onboarding overlay (dismissible, localStorage)
- [x] G2. Readiness strip with Test connections CTA
- [x] G3. Guided tooltips remain available
- [x] G4. Multi-step first-run wizard (server-persisted + Settings guidance)
- [x] G5. Spend / cost meter for cloud image APIs

## H. UX polish

- [x] H1. Global toast helper used for readiness + pipeline milestones
- [x] H2. Keyboard help overlay (`?`)
- [x] H3. Focus rings / status strip styling
- [x] H3b. Unified **Create** hub workspace (Agency home)
- [x] H4. Mobile layout pass
- [x] H5. Dark/light theme toggle
- [x] H6. Command palette (⌘/Ctrl+K) — desks, run campaign, produce story, export, scorecard
- [x] H7. Client review (approve / needs changes / reject+remediate) on lightbox + review queue API
- [x] H8. Executive Producer console (agency brief, Hermes chat actions, production timeline)
- [x] H9. A/B frame compare (side-by-side, pick winner → preference on shot + review log)
- [x] H10. Stories Assemble / Export package CTA (highlighted when frames/clips exist; disabled + Produce with Hermes reason when empty)

## I. Reliability & testing

- [x] I1. Isolation unit tests
- [x] I2. Expand smoke suite with readiness + product endpoints
- [x] I3. Full pytest suite after changes
- [ ] I4. Live render smoke (`--live-script`, `--live-campaign`) when Spark online
- [x] I5. Contract tests for canonical APIs (`tests/test_api_contracts.py`)
- [x] I6. Structured API errors (`dashboard/errors.py`)

## J. Memory & agency intelligence

- [x] J1. Memory tab Agency learning explainer + failure auto-consolidate status pointer
- [x] J2. Memory suggestions on Create hub (episodic + brief-aware)
- [x] J3. Consistency scorecard for stories
- [x] J4. Auto-consolidate after N failures

---

## Execution order for this pass

1. Foundation (A, B)
2. Readiness + onboarding + presets + shortcuts (C, D, E, G, H)
3. Tests (I)
4. Document remaining backlog for next sessions

---

## Definition of done (this pass)

- App launches with `scripts/launch_cinesmith.sh` and never points Hermes at `~/.hermes` by default
- Media root works without hard-coded user path
- Onboarding + readiness strip visible on first load
- Image + Script Studio presets accelerate story creation
- Unit tests pass; smoke suite checks readiness when server is up
- Agency coach + sample briefs make first production obvious without docs
- Characters sheet-from-photo, Videos First→Last, Stories series episodes usable end-to-end
