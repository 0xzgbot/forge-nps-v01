# Forge NPS — Hermes Agent Creative Hackathon Submission

---

## 🎬 The Pitch

**Forge NPS** is a cinematic production pipeline where five AI models work as a film crew — not a monolithic black box. Every pixel has an origin, every shot has a paper trail, and failures are first-class citizens with their own retry lineage.

We didn't build another "AI image generator." We built a **production system** that treats creativity as engineering: plan → compile → render → audit → learn.

📹 **Video Demo:** [link when ready]
🧵 **X Thread:** [link when ready]

---

## 🏗️ Architecture — Five Minds, One Pipeline

Forge NPS assigns explicit roles to five distinct models. No model does everything. Each has a job, an interface, and accountability.

| Role | Model | Job |
|------|-------|-----|
| **Director** | Kimi (K2 / K2.6) | Structured shot planning, coverage critique, self-check scoring |
| **Engineer** | Hermes (local + Nous) | Campaign intake, prompt compilation, skills orchestration, remediation |
| **Renderer** | Spark / ComfyUI | Image + video generation via workflow-specific dispatch |
| **Critic** | Vision (local Qwen) | Pass/fail quality audit with scored issues |
| **Historian** | Memory (episodic store) | Provenance, retry lineage, outcome telemetry |

**The flow:**

```
Brief → Kimi plans shots → Kimi self-checks → Hermes compiles prompts
  → Spark renders → Vision audits → Pass or Remediate → Memory records
```

---

## 🔥 What Makes This Different

### 1. Provenance-First Design
Every shot carries complete lineage:
- **Kimi plan** (visual brief, rationale, constraints)
- **Hermes compilation** (compiled prompt, negative prompt, skills used, model standard metadata)
- **Spark output** (prompt ID, seed, image path)
- **Audit stamp** (status, score, issues, raw response)
- **Retry linkage** (`retry_of`, remediated prompt, final outcome)

Click any shot and you see exactly who decided what, when, and why.

### 2. Failure Is a Feature, Not a Bug
Most pipelines hide failures. Forge NPS **ritualizes** them:
- Failed shots get re-audited with `POST /api/audit/reprocess`
- Failed shots get remediated with `POST /api/audit/remediate`
- Remediation creates a **linked retry** with full lineage
- The original and retry are connected via `retry_of` — you can trace the family tree

### 3. Hermes Is the Pipeline Brain — Not Just Chat
Hermes doesn't just answer questions. It:
- Intakes campaign briefs and produces director context
- Compiles workflow-specific prompt artifacts (not generic prompts)
- Tracks skills used per shot
- Orchestrates remediation with continuity
- Writes canonical memory events to `data/hermes_memory/episodic/events.jsonl`

### 4. Kimi Self-Checks Before Rendering
Before a single pixel is spent, Kimi runs a planning critique:
- Coverage analysis
- Risk scoring
- Constraint validation
- If the self-check fails, the campaign **stops** (unless dev fallback is enabled)

This saves GPU hours and catches bad ideas before they become expensive mistakes.

### 5. Memory as Telemetry, Not Just Logs
`GET /api/memory/health` returns structured integrity metrics:
- Total events
- Unknown event types
- Orphan remediation events
- Shots missing audit after render

This turns the event store into a **quality dashboard** for the pipeline itself.

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|------------|
| Dashboard | FastAPI + custom NDJSON streaming |
| Director | Kimi via NVIDIA API (K2 / K2.6) |
| Pipeline Brain | Hermes Agent (submodule, updatable) |
| Local Inference | LM Studio (Qwen 3.6 35B A3B) |
| Rendering | ComfyUI / Spark (Flux2, LTX 2.3, AceStep) |
| Vision Audit | Local vision model via LM Studio |
| Memory | JSONL episodic store with health diagnostics |
| Promo VFX | TouchDesigner 2025 + POPs + p5js + AudioCraft |

---

## 📊 Demo Proof Points

### Live Campaign Run
1. Enter brief → click **Run Campaign**
2. Stream shows: `profile` → `kimi_raw` → `kimi_plan` → `kimi_review` → `compiler` → `spark` → `memory`
3. Open shot → see complete provenance

### Failure & Recovery
1. Filter failed shots
2. **Re-Audit Selected** → new audit score
3. **Remediate** → linked retry shot created
4. View `retry_of` lineage: original → remediation → retry → final pass/fail

### Memory Health
- `GET /api/memory/health` returns integrity counts
- Events stored in `data/hermes_memory/episodic/events.jsonl`

---

## 🎨 Creative Output

Forge NPS doesn't just manage pipelines — it **produces** them. We used our own pipeline to generate:
- 16 cinematic hero shots for the TouchDesigner 2025 showcase kit
- A 90-second promo visual experience using POPs, 3D textures, and volumetric rendering
- Character portraits, campaign stills, and motion pieces

The pipeline promoted itself.

---

## 🔗 Links

- **Repo:** `forge_nps_v01` (private, shared with judges)
- **Docs:** README.md, ARCHITECTURE.md, PIPELINE_CONTRACT_SUMMARY.md
- **Contract:** `data/contracts/pipeline_contract.json`
- **Video:** [link]
- **X Thread:** [link]

---

## 🙏 Credits

Built with:
- **Hermes Agent** by Nous Research — the only agent with a closed learning loop (skills, memory, session continuity)
- **Kimi** by Moonshot AI — director-level planning and critique
- **TouchDesigner 2025** by Derivative — POPs, 3D textures, and real-time VFX
- **ComfyUI / Spark** — render execution

---

*Forge NPS. Every shot, accounted for.*
