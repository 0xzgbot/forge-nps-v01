# Forge NPS — Architecture

## System Overview

Two codebases, one running dashboard:

- **`/Users/zgbot/Desktop/forge_nps_v01/`** — original forge project with full orchestrator, agents, memory system, and demo.py
- **`/Users/zgbot/dashboard/`** + **`/Users/zgbot/core/`** — active Command Center dashboard (port 7000), imports from `/Users/zgbot/core/`

The dashboard on port 7000 does NOT use the forge_nps orchestrator. It calls `NousHermesBridge` and `KimiBridge` directly.

---

## Data Flow — Campaign Run

```
User: "car commercial golden hour" + 30s (6 shots)
        │
        ▼
POST /api/hermes/run-campaign
        │
        ├─ Load world_bible.md (lore context)
        │
        ▼
[KIMI K2-INSTRUCT] moonshotai/kimi-k2-instruct via NVIDIA NIM
    Input:  brief + lore context
    Output: [{id, description, characters, intent}] × N shots
    Stream: {type: "kimi", text: "Shot list ready: 6 shots"}
        │
        ▼ (per shot, sequential)
[HERMES/QWEN] qwen3.6-35b-a3b via LM Studio (100.74.164.1:1234)
    Input:  shot description + memory_context (learned rules)
    Output: cinematic Stable Diffusion prompt (2-4 sentences)
    Stream: {type: "hermes", text: "SHOT_001: wide angle..."}
    Fallback: if LM Studio offline → use Kimi description + style suffix
        │
        ▼
[COMFYUI SPARK] 100.112.87.8:8188
    Loads:  /Users/zgbot/workflows/hermes_z_image_turbo_api.json
    Injects: node["6"]["inputs"]["text"] = prompt
             node["9"]["inputs"]["seed"] = random_seed
    Polls:  GET /history/{prompt_id} every 5s (600s timeout)
    Downloads: GET /view?filename=X&subfolder=Y&type=output
    Saves:  data/campaigns/{campaign_id}/{filename}.png
    Stream: {type: "render_complete", src: "/campaigns/..."}
        │
        ▼
[KIMI-VL] kimi-v2-vision via NVIDIA NIM
    Input:  rendered PNG (base64) + character anchor image (base64) + original prompt
    Output: {is_consistent, confidence, issues, error_category}
    Stream: {type: "kimi_vl_audit", score: 0.91, passed: true}
        │
        ├── PASS ──────────────────────────────────────────┐
        │                                                  │
        └── FAIL → Remediation Loop                        │
                    Tier 1: Hermes diagnoses → rewrites    │
                    Tier 2: Kimi K2 heavy rewrite           │
                    (max 2 retries)                        │
                    Stream: {type: "retry", rewrite_reason} │
                        │                                  │
                        ▼                                  │
                   ← re-render → re-audit →               │
                                                          ▼
                                            Memory Write
                                            data/hermes_memory/episodic/events.jsonl
                                            Stream: {type: "memory_written"}
```

---

## Component Map

```
/Users/zgbot/
├── dashboard/
│   ├── forge_dashboard.py          ← ACTIVE SERVER (port 7000)
│   ├── static/js/app.js            ← All UI logic
│   └── templates/index.html        ← Single-page shell
│
└── core/
    ├── bridge/
    │   ├── nous_hermes_bridge.py   ← Wraps LMStudioClient
    │   ├── kimi_bridge.py          ← Kimi K2 + Kimi-VL HTTP client
    │   └── lmstudio_client.py      ← OpenAI-compat local client
    ├── dispatch/
    │   └── comfy_client.py         ← ComfyUI job submit + poll + download
    └── feedback/
        └── remediation_loop.py     ← 3-tier retry logic

/Users/zgbot/Desktop/forge_nps_v01/
├── core/
│   ├── hermes/
│   │   ├── hermes_agent.py         ← Full orchestrating agent
│   │   └── memory/
│   │       ├── episodic_memory.py  ← JSONL append-only event store
│   │       ├── semantic_memory.py  ← Consolidated rules store
│   │       ├── consolidator.py     ← Pattern extraction + rule forging
│   │       └── embedder.py         ← Kimi / LMStudio / NumPy TF-IDF (auto-fallback)
│   ├── consistency/
│   │   └── character_consistency_engine.py  ← Parses world_bible, enriches prompts
│   ├── orchestrator/
│   │   └── forge_orchestrator.py   ← Kimi→Hermes→Auditor→Remediation pipeline
│   └── feedback/
│       └── remediation_loop.py     ← 3-tier remediation (forge_nps version)
├── agents/
│   ├── auditor/
│   │   └── continuity_auditor.py   ← Kimi-VL audit + hardcoded text fallback
│   └── visual/
│       └── visual_agent.py         ← ComfyUI dispatch with character enrichment
└── demo.py                         ← CLI entry: full pipeline + memory demo
```

---

## Memory Architecture

```
Render outcome
    │
    ▼
EpisodicMemory.record()
    → data/hermes_memory/{session}/episodic/events.jsonl (append-only)
    → Indexed by embedding vector (Kimi → LMStudio → NumPy TF-IDF fallback)
    │
    ▼ (after session or on demand)
MemoryConsolidator.consolidate()
    → Groups episodes by (error_category, kernel_id)
    → Finds consensus fix across 2+ matching events
    │
    ▼
SemanticMemory.store()
    → data/hermes_memory/{session}/semantic/insights.json
    → {rule, confidence, confirmations, examples, pattern}
    │
    ▼ (next campaign)
HermesAgent reads SemanticMemory before writing prompts
    → Injects learned rules as memory_context
    → Same error category → same fix, first try
```

---

## Infrastructure

| Service | Address | Purpose |
|---------|---------|---------|
| Dashboard | `localhost:7000` | Command Center UI + API |
| LM Studio | `100.74.164.1:1234` | Hermes/qwen local inference |
| ComfyUI Spark | `100.112.87.8:8188` | GPU render cluster |
| NVIDIA NIM | `integrate.api.nvidia.com/v1` | Kimi K2 + Kimi-VL |

---

## Remediation Loop — 3 Tiers

```
Kimi-VL audit FAIL
    │
    ▼
Tier 1 — Hermes autonomous
    Reads: audit finding + episodic memory (similar past failures)
    Writes: corrected prompt (targeted fix)
    Re-renders → re-audits
    Success rate: ~60%
    │
    ▼ (if still failing)
Tier 2 — Kimi K2-Instruct escalation
    Full prompt rewrite from scratch
    Heavy reasoning token budget
    Re-renders → re-audits
    Success rate: ~85%
    │
    ▼ (if still failing after max_retries=2)
Tier 3 — Human review flag
    Stream: {type: "error", text: "needs_human_review"}
    Shot marked unresolved in session
```
