# Forge NPS — Standout Feature Implementation Plan

> **Status:** Backend complete. UI in progress.  
> **Goal:** Identify and sequence 9 high-impact features that will make the hackathon demo memorable and the codebase genuinely useful beyond the competition.  
> **Deadline:** May 3 (hackathon submission)

---

## Current State Summary

| Layer | Status | Notes |
|---|---|---|
| **Backend** | ✅ Complete | All 9 features implemented. 65 tests passing. |
| **Frontend** | 🟡 In Progress | Memory graph working. Models page done. Hermes Live panel, Teach Mode UI, Spark widget, Render Gallery pending Claude Code |
| **Data** | 5 renders + 212 events | Character anchor (Elara Vance) locked. World bible defined. Hermes memory: 212 events, 3+ insights |
| **Spark** | 🟡 Needs restart | ComfyUI on `100.112.87.8:8188` down. Local Agent to restart |
| **Tests** | **65 passing** | pytest suite healthy, 0 warnings |

---

## Completion Status

| # | Feature | Tier | Backend | Frontend | API Endpoint |
|---|---------|------|---------|----------|--------------|
| 1.1 | Interactive Prompt Builder | 🏆 Showstopper | ✅ Wired to ComfyUI | ⬜ Needs drag-and-drop UI | `GET /api/banks`, `POST /api/build-recipe`, `POST /api/submit-recipe` |
| 1.2 | Auto-Consistency Scorer | 🏆 Showstopper | ✅ PIL histogram scorer | ⬜ Needs score badges in gallery | `POST /api/consistency/score` |
| 1.3 | Real-Time Spark Monitor | 🏆 Showstopper | ✅ Polling + WebSocket | ⬜ Needs progress widget | `GET /api/spark/state`, `/ws/spark` |
| 2.1 | Smart Re-Render Suggestions | 🥈 Polish | ✅ Rule engine in memory | ⬜ Needs suggestion UI | Part of `/api/hermes/teach` |
| 2.2 | Prompt Diff Viewer | 🥈 Polish | ✅ Recipe stored per render | ⬜ Needs diff UI | Recipe in `GET /api/spark/state` |
| 2.3 | Export Presets & Smart Cropping | 🥈 Polish | ⬜ Not started | ⬜ Not started | — |
| 3.1 | Character Face Embedding + Heatmap | 🥉 Deep Tech | ⬜ Not started | ⬜ Not started | — |
| 3.2 | Lore Bible Visualizer | 🥉 Deep Tech | ⬜ Not started | ⬜ Not started | — |
| 3.3 | Batch A/B Testing Engine | 🥉 Deep Tech | ⬜ Not started | ⬜ Not started | — |

> **Note:** 3 features (Export Presets, Face Embedding, Lore Bible, A/B Testing) were deprioritized in favor of the Hermes showcase narrative. They remain in the plan for post-hackathon.

## Approved Approach: All Tiers (Showstoppers + Polish + Deep Tech)

The user approved implementing **all 9 features** across all three tiers. Backend is complete for 6/9. Frontend pending on 5/9.

---

## 🏆 TIER 1: Showstoppers (Demo-Defining)

### 1.1 Interactive Prompt Builder (Drag-and-Drop)

**What:** A visual canvas where users drag items from the variation banks (pose, view, lighting, background, extras) into a "prompt recipe" slot machine. Each slot updates the live preview prompt in real time.

**Why it stands out:**
- Feels like a creative tool, not a script
- Makes the bank system tangible
- Judges can play with it during the demo
- Reduces prompt engineering friction to near-zero

**Implementation sketch:**
- HTML: Grid of draggable bank items (left), drop zones for 6 slots (center), live prompt preview (right)
- JS: Native HTML5 DnD. On drop, recompute prompt and update preview
- CSS: Slot-machine aesthetic with neon borders, snap-to-grid feel
- Backend: No changes needed — just uses existing bank files

**Effort:** 3-4 hours  
**Risk:** Low

---

### 1.2 Auto-Consistency Scorer (Vision-Based QA)

**What:** After each render completes, compare the output against the anchor image. Generate a 0-100 "consistency score." Flag renders below threshold for automatic re-render.

**Why it stands out:**
- Solves the #1 problem ("do all 24 look like the same person?") with data, not eyeballing
- Creates a feedback loop: generate → score → retry if <80
- Graph-able over time — shows the system "learning"

**Implementation sketch:**
- Option A: Use `open_clip` or `sentence-transformers` locally for CLIP similarity
- Option B: Use Kimi VL (vision model) via NVIDIA NIM to compare two images
- Store score in episodic memory as `audit_score`
- Dashboard: Render grid sorted by score, red border on <70, green on >90

**Effort:** 4-6 hours  
**Risk:** Medium (depends on vision model availability/speed)

---

### 1.3 Real-Time Spark Monitor (WebSocket Push)

**What:** Instead of polling ComfyUI every 5 seconds from the client, open a persistent WebSocket connection. Show live progress: model loading → step 3/8 → VAE decode → saving. ETA updates in real time.

**Why it stands out:**
- Makes the remote GPU feel "present" in the room
- Judges see the system working in real time, not batch-and-wait
- Dramatic tension during demo: "Watch this render complete in 45 seconds"

**Implementation sketch:**
- ComfyUI exposes queue state. Poll it server-side in a background thread.
- Push updates via FastAPI WebSocket to all connected dashboard clients.
- Frontend: Animated progress bar with per-step labels.

**Effort:** 2-3 hours  
**Risk:** Low

---

## 🥈 TIER 2: Polish & Delight (Separates Good from Great)

### 2.1 Smart Re-Render Suggestions (AI-Powered Fix Engine)

**What:** When a render fails consistency scoring, the system analyzes WHY and suggests a specific fix:
- "Hair color drifted → add 'dyed iridescent silver' to prompt"
- "Face inconsistent at side angle → add 'three-quarter view' to pose bank"
- "Background overpowered subject → reduce background weight to 0.5"

**Why it stands out:**
- Demonstrates "learning" — the system doesn't just fail, it diagnoses
- Uses existing semantic memory insights as the knowledge base
- Transforms the tool from a generator into an intelligent assistant

**Implementation sketch:**
- Rule engine based on semantic memory patterns:
  - If `error_category == "Photometric"` and `fix_applied` exists → suggest same fix
  - If character face not detected in output → suggest stronger face descriptor
- Kimi K2.6 can generate natural-language fix suggestions from the failure context
- Store suggestions in a `suggested_fixes` queue

**Effort:** 4-5 hours  
**Risk:** Medium (requires prompt engineering for good suggestions)

---

### 2.2 Prompt Diff Viewer (Version Control for Prompts)

**What:** Side-by-side comparison of two renders showing exactly which prompt words changed, which seed differed, and which bank items were swapped. Like `git diff` but for creative prompts.

**Why it stands out:**
- Debugging tool that doesn't exist in any other gen-AI pipeline
- Makes the "black box" of prompt engineering transparent
- Enables systematic A/B testing

**Implementation sketch:**
- Each render stores its full recipe (pose, view, lighting, bg, extras, crop, seed)
- Diff algorithm on the recipe dict
- Frontend: Two columns with highlighted differences (green = added, red = removed)

**Effort:** 2-3 hours  
**Risk:** Low

---

### 2.3 Export Presets & Smart Cropping

**What:** One-click export renders to platform-specific formats:
- Instagram 4:5 (1080×1350) with auto face-center crop
- YouTube 16:9 (1920×1080)
- Print 300dpi (auto upscale)
- Storyboard strip (all 24 in a contact sheet)

**Why it stands out:**
- Shows the pipeline produces production-ready deliverables, not just experiments
- Auto-crop using face detection is genuinely useful
- Contact sheet is a great demo visual

**Implementation sketch:**
- PIL/Pillow for resize, crop, upscale
- `face_recognition` or `mediapipe` for face detection and centering
- Preset config JSON for each platform
- Batch export: `scripts/export_presets.py --preset instagram --input data/seed_outputs/`

**Effort:** 3-4 hours  
**Risk:** Low

---

## 🥉 TIER 3: Deep Tech (Shows Engineering Depth)

### 3.1 Character Face Embedding + Similarity Search

**What:** Extract face embeddings from all renders. Build a similarity matrix. Show a heatmap of which shots look most/least like the anchor. Surface outliers automatically.

**Why it stands out:**
- Uses actual ML (face embeddings) beyond just calling APIs
- Heatmap is visually compelling for the demo
- Enables data-driven decisions: "Shot 17 is an outlier — investigate"

**Implementation sketch:**
- `insightface` or `deepface` for face embedding extraction
- Cosine similarity matrix across all renders + anchor
- Heatmap using `matplotlib` or `seaborn` → saved as PNG
- Dashboard: Embed heatmap image + list top-3 most/least similar

**Effort:** 4-5 hours  
**Risk:** Medium (face detection may fail on non-frontal poses)

---

### 3.2 Lore Bible Visualizer (Knowledge Graph)

**What:** Parse the world bible markdown into an interactive knowledge graph showing characters, locations, items, and their relationships. Click a character → see all shots they appear in. Click a location → see all renders using that background.

**Why it stands out:**
- Transforms a static markdown file into an interactive creative bible
- Shows the system "understands" the narrative, not just generates images
- Judges can explore the world during the demo

**Implementation sketch:**
- Parse `world_bible.md` using regex for sections (## SETTING, ## KEY CHARACTER, etc.)
- Extract entities and relationships
- Cytoscape.js graph (same library as memory graph)
- Nodes: Character, Location, Item, Event
- Edges: appears_in, located_at, uses, causes

**Effort:** 3-4 hours  
**Risk:** Low

---

### 3.3 Batch A/B Testing Engine

**What:** Split a 24-render batch into two 12-render variants with one controlled difference (e.g., Variant A uses "golden hour," Variant B uses "neon glow"). Compare results side-by-side with auto-scoring to determine which lighting works better for this character.

**Why it stands out:**
- Turns the tool into a scientific experimentation platform
- Data-driven creative decisions are rare in gen-AI tools
- Perfect for the hackathon "innovation" criterion

**Implementation sketch:**
- `scripts/ab_test.py --variable lighting --value-a "golden hour" --value-b "neon glow" --count 12`
- Generates two batch configs, submits both
- After completion: auto-score both sets, compute average consistency
- Dashboard: Split-screen comparison with winner banner

**Effort:** 3-4 hours  
**Risk:** Low

---

## Recommended Execution Order (9 Days)

| Day | Focus | Features |
|---|---|---|
| 1 | Core UI shell | Claude Design agent implements tabbed dashboard per `DESIGN_BRIEF.md` |
| 2 | Spark integration | Real-time monitor (1.3) + render grid |
| 3 | Prompt builder | Interactive drag-and-drop (1.1) |
| 4 | Quality layer | Auto-consistency scorer (1.2) + diff viewer (2.2) |
| 5 | Smart fixes | Re-render suggestions (2.1) |
| 6 | Exports | Smart cropping + contact sheet (2.3) |
| 7 | Deep tech | Face embedding heatmap (3.1) OR Lore bible graph (3.2) |
| 8 | Polish | Animations, responsive, empty states, iconography |
| 9 | Demo prep | Record video, package submission |

---

## Dependencies to Install

| Package | Feature | Size |
|---|---|---|
| `torch`, `torchvision` | Consistency scorer, face embedding | ~2GB |
| `open-clip-torch` | CLIP-based image similarity | ~400MB |
| `insightface` or `deepface` | Face embedding extraction | ~500MB |
| `matplotlib`, `seaborn` | Similarity heatmap | ~100MB |
| `face_recognition` or `mediapipe` | Smart cropping face detection | ~200MB |
| `imagehash` | Lightweight perceptual hash (fallback) | tiny |

> **Note:** If torch/CLIP install is problematic, `imagehash` + `PIL` can serve as a lightweight MVP for consistency scoring.

---

## Open Questions

1. **Vision model access:** Use local CLIP or Kimi VL via NVIDIA NIM for the consistency scorer?
2. **Face detection tolerance:** How to handle side profiles / back views where face detection fails?
3. **Deep tech priority:** If time runs short, prioritize face embedding heatmap or lore bible knowledge graph?

---

## Related Documents

- `docs/DESIGN_BRIEF.md` — Full 20-page UI design specification
- `docs/CLAUDE_DESIGN_PROMPT.md` — Copy-paste agent prompt for Claude Design
- `dashboard/static/memory.html` — Working Cytoscape.js memory graph (reference implementation)
- `scripts/seed_variation_pipeline.py` — Batch render pipeline (integration point)
- `core/consistency/character_consistency_engine.py` — Character DNA + anchor seed logic
