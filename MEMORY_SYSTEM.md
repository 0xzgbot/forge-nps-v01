# Forge NPS — Memory System

Forge doesn't just run pipelines. It learns. Every render outcome is recorded, patterns are extracted, and rules are written into semantic memory. The next campaign starts smarter than the last.

---

## Three Layers

### 1. Episodic Memory
Raw event log. One entry per render outcome.

**File**: `data/hermes_memory/{session_id}/episodic/events.jsonl`  
**Format**: Append-only JSONL, one JSON object per line.

```json
{
  "shot_id": "SHOT_001",
  "concept": "neon alleyway golden hour",
  "kernel_id": "zimage_turbo",
  "success": false,
  "iterations_required": 3,
  "error_category": "Photometric",
  "fix_applied": "reduce highlight intensity, add soft global illumination",
  "audit_score": 0.61,
  "timestamp": "2026-04-26T20:00:00",
  "embedding": [...]
}
```

Queried by semantic similarity (embedding cosine) before each new prompt write. Hermes finds past failures in the same concept space and avoids repeating them.

---

### 2. Semantic Memory
Consolidated rules. Extracted from episodic after 2+ matching events.

**File**: `data/hermes_memory/{session_id}/semantic/insights.json`

```json
{
  "rule": "For neon lighting shots, always specify iris color explicitly to prevent mismatch",
  "confidence": 0.87,
  "confirmations": 2,
  "error_category": "Photometric",
  "examples": ["SHOT_001", "SHOT_004"],
  "pattern": "lighting_neon+character_eyes"
}
```

Hermes injects matching semantic rules as `memory_context` before writing each prompt. Rules with higher `confirmations` are weighted more heavily.

---

### 3. Session State
Per-campaign metadata and shot outcomes.

**File**: `data/sessions/{session_id}.json`

```json
{
  "session_id": "demo_20260426",
  "created_at": "2026-04-26T20:00:00",
  "script_path": "...",
  "shots": {"SHOT_001": {...}, "SHOT_002": {...}},
  "autonomy_score": 0.83,
  "total_fixes_by_hermes": 2,
  "total_kimi_escalations": 1
}
```

---

## How Rules Are Forged

```
Two failures with same error_category
    │
    ▼
MemoryConsolidator.consolidate()
    Groups episodes by (error_category, kernel_id)
    Finds consensus fix across matching events
    Checks: confirmations >= 2
    │
    ▼
SemanticMemory.store()
    New rule written with confidence = avg(audit_scores)
    confirmations counter starts at 2
    │
    ▼
Next campaign: Hermes reads rule before writing prompt
    Injects as memory_context: "Known fix: [rule]"
    Same failure avoided on first attempt
    confirmations++ after successful render
```

---

## Embedder Backends

The memory system uses vector similarity to find relevant past episodes. Three backends, auto-detected in order:

| Backend | When Used | Quality |
|---------|-----------|---------|
| **KimiEmbedder** | KIMI_API_KEY available | Best — semantic understanding |
| **LMStudioEmbedder** | LM Studio online | Good — local model embeddings |
| **NumpyTFIDFEmbedder** | Always available (zero dependencies) | Adequate — keyword overlap |

`HybridEmbedder` tries each in order and falls back automatically. Memory always works, quality degrades gracefully.

---

## Querying Memory

Before Hermes writes a prompt:

```python
# Query episodic memory for similar past shots
similar = await episodic_memory.query_similar(
    concept=shot_description,
    top_k=3
)

# Query semantic memory for relevant rules
rules = semantic_memory.query(
    error_category="Photometric",
    kernel_id="zimage_turbo"
)

# Build memory_context string injected into Hermes prompt
memory_context = format_rules(rules) + format_examples(similar)
```

---

## The Learning Curve

A campaign running for the first time will use 3 iterations on hard failures. The same campaign type run again will pass audit on the first attempt for any failure pattern already in semantic memory.

Over 10 campaigns in the same domain: the system self-optimizes toward zero remediation iterations. This is the core value proposition — not just automation, but compounding improvement.

---

## Dashboard — Memory Panel

The Memory panel in the Command Center shows rules accumulating in real time.

- Updates live on `memory_written` WebSocket event
- Displays: rule text, confidence score, confirmation count
- Newest rules appear at top
- Cleared only when session resets

---

## Files Written During a Campaign

```
data/
├── hermes_memory/
│   └── {session_id}/
│       ├── episodic/
│       │   └── events.jsonl          ← One line per render outcome
│       └── semantic/
│           └── insights.json         ← Consolidated rules
├── sessions/
│   └── {session_id}.json             ← Session metadata + shot outcomes
└── campaigns/
    └── {campaign_id}/
        ├── shot001.png               ← Rendered image
        └── shot001.json              ← Sidecar audit result
```
