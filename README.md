# Forge NPS — AI-Native Creative Pipeline

Forge NPS is a multi-model AI pipeline for generating cinematic image campaigns. A creative brief flows through Kimi K2 (director), Hermes/qwen (prompt writer), ComfyUI on Spark (renderer), and Kimi-VL (visual auditor). The system learns from every render — failures are diagnosed, prompts are rewritten, and rules accumulate in memory so the same mistake is never made twice.

---

## How to Run

### Dashboard (primary interface)
```bash
cd /Users/zgbot/dashboard
KIMI_API_KEY="nvapi-..." python3 forge_dashboard.py
# Opens at http://localhost:7000
```

### Demo (CLI pipeline)
```bash
cd /Users/zgbot/Desktop/forge_nps_v01
python demo.py --mock                          # Mock Kimi, real ComfyUI
python demo.py --memory-demo                   # Learning loop demonstration
python demo.py --idea "car commercial"         # Idea → world bible → renders
```

### Environment Variables
```
KIMI_API_KEY=nvapi-...                        # NVIDIA NIM API key (real key in .env only — config.json has masked placeholder)
LMSTUDIO_HOST=http://100.74.164.1:1234        # Hermes/qwen local inference
COMFYUI_PRIMARY=http://100.112.87.8:8188      # Spark GPU cluster
```

### Config File
`/Users/zgbot/data/config.json` — models, ComfyUI URLs, character paths.

---

## The Pipeline

```
Brief + Length
    │
    ▼
Kimi K2-Instruct (Director)
    Generates shot list: [{id, description, characters, intent}]
    │
    ▼
Hermes/qwen via LM Studio (Creative Writer)
    Writes cinematic SD prompt per shot
    Reads episodic memory before writing — applies learned rules
    │
    ▼
ComfyUI on Spark (Renderer)
    Injects prompt into workflow node 6 (CLIPTextEncode)
    Injects seed into node 9 (KSampler)
    Polls /history until complete, downloads PNG via /view
    │
    ▼
Kimi-VL (Visual Auditor)
    Compares render to character anchor images
    Returns: {is_consistent, confidence, issues, error_category}
    │
    ├── PASS → write to episodic memory, continue
    │
    └── FAIL → Remediation Loop
                Tier 1: Hermes reads audit + memory → rewrites prompt → re-renders
                Tier 2: Kimi K2-Instruct heavy rewrite → re-renders
                Tier 3: Human review flag
                │
                ▼
            Memory Write
            Episodic: {shot_id, concept, success, iterations, fix_applied, error_category}
            Semantic: consolidated rules after 2+ confirmations of same pattern
```

---

## Model Roles

| Model | Provider | Role |
|-------|----------|------|
| `moonshotai/kimi-k2-instruct` | NVIDIA NIM | Director — shot list from brief |
| `kimi-v2-vision` | NVIDIA NIM | Visual auditor — render vs anchor |
| `qwen3.6-35b-a3b` (auto-detected at startup) | LM Studio local | Creative writer — SD prompts, failure diagnosis |
| FLUX2 / Z-Image Turbo | ComfyUI Spark | Image renderer |

---

## Folder Structure

```
forge_nps_v01/
├── agents/
│   ├── auditor/continuity_auditor.py    # Kimi-VL visual audit + lore validation
│   └── visual/visual_agent.py           # ComfyUI workflow dispatch
├── core/
│   ├── bridge/
│   │   ├── kimi_bridge.py               # Kimi K2 + Kimi-VL API client
│   │   ├── nous_hermes_bridge.py        # LM Studio client for Hermes/qwen
│   │   └── lmstudio_client.py           # OpenAI-compatible local inference client
│   ├── consistency/
│   │   └── character_consistency_engine.py  # Character DNA + anchor injection
│   ├── dispatch/
│   │   └── comfy_client.py              # ComfyUI HTTP client + job polling
│   ├── feedback/
│   │   └── remediation_loop.py          # 3-tier failure remediation
│   ├── genesis/                         # Idea → world bible (partially implemented)
│   ├── hermes/
│   │   ├── hermes_agent.py              # Agent orchestrator
│   │   └── memory/                      # Episodic + semantic memory system
│   ├── orchestrator/
│   │   └── forge_orchestrator.py        # Campaign orchestrator
│   └── state/
│       └── session_manager.py           # Session persistence
├── data/
│   ├── character_banks/anchors/         # Character reference images
│   ├── config.json                      # Runtime config
│   ├── lore_bible/world_bible.md        # Character and world definitions
│   ├── renders/campaigns/               # Campaign render outputs
│   └── hermes_memory/                   # Episodic + semantic memory store
├── workflows/
│   └── hermes_z_image_turbo_api.json   # ComfyUI workflow template
├── dashboard/                           # FastAPI web dashboard (port 7000)
└── demo.py                              # CLI entry point
```

---

## Memory System

Every render outcome is recorded. The system gets smarter over campaigns.

**Episodic memory** — written after every audit:
```json
{
  "shot_id": "SHOT_001",
  "concept": "neon alleyway golden hour",
  "kernel_id": "zimage_turbo",
  "success": false,
  "iterations_required": 3,
  "error_category": "Photometric",
  "fix_applied": "reduce highlight intensity, add soft global illumination",
  "audit_score": 0.92
}
```

**Semantic memory** — consolidated from episodic after 2+ matching failures:
```json
{
  "rule": "For neon lighting shots, specify iris color explicitly",
  "confidence": 0.87,
  "confirmations": 2
}
```

Hermes reads semantic memory before writing every new prompt. Rules compound across campaigns.

---

## Character System

Characters are defined in `data/lore_bible/world_bible.md` under `## KEY CHARACTER:` sections. The `CharacterConsistencyEngine` parses these at startup and:
- Injects physical descriptors into every generated prompt
- Uses anchor images from `data/character_banks/anchors/` for Kimi-VL comparison
- Generates deterministic seeds per character for visual consistency

---

## Known Issues

| Issue | File | Impact |
|-------|------|--------|
| `NousHermesBridge.__init__` takes no params but called with `lmstudio_client` in forge_nps orchestrator | `core/bridge/nous_hermes_bridge.py:29` | Brain injection broken in old orchestrator path |
| `KimiBridge.direct()` missing return statement | `core/bridge/kimi_bridge.py:178` | Returns None on success |
| `ContinuityAuditor._perform_semantic_audit()` only detects "red eyes" / "three arms" | `agents/auditor/continuity_auditor.py:136` | Text fallback audit is hardcoded; Kimi-VL path works correctly |
| `GenesisEngine` missing from `/Users/zgbot/core/genesis/` | `core/genesis/` | `forge_run.py` ImportError when run from parent dir |
| `RemediationLoop` calls `KimiBridge()` with no args | `core/feedback/remediation_loop.py:48` | Auth failure on Kimi escalation tier |
