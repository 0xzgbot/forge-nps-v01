# Forge NPS — X Thread for Hermes Agent Creative Hackathon

---

## Tweet 1/12 — The Hook

🎬 We didn't build another "AI image generator."

We built a film crew where 5 AI models have actual jobs:
• Kimi = Director
• Hermes = Engineer  
• Spark = Renderer
• Vision = Critic
• Memory = Historian

Every pixel has an origin. Every failure has a retry lineage.

This is Forge NPS. 🧵

[video embed]

---

## Tweet 2/12 — The Problem

Most AI creative tools are black boxes.

You type a prompt → magic happens → maybe you get something good.

But:
❌ No paper trail
❌ No quality gate
❌ No failure recovery
❌ No learning from mistakes

That's fine for toys. It's catastrophic for production.

---

## Tweet 3/12 — The Architecture

Forge NPS assigns explicit roles. No model does everything.

Kimi plans shots → Kimi self-checks → Hermes compiles prompts → Spark renders → Vision audits → Memory records

Each stage emits structured events. The entire pipeline is observable.

---

## Tweet 4/12 — Kimi the Director

Before a single pixel is rendered, Kimi:
• Writes a structured shot plan
• Runs a self-check critique
• Scores coverage and risks
• Stops the campaign if the plan is bad

This saves GPU hours and catches bad ideas before they get expensive.

---

## Tweet 5/12 — Hermes the Engineer

Hermes isn't just chat. It's the pipeline brain:
• Campaign intake + context building
• Workflow-aware prompt compilation
• Skills tracking per shot
• Remediation orchestration
• Canonical memory writes

It learns. It repairs. It keeps continuity.

---

## Tweet 5b/12 — The Skills Library

We didn't just *use* Hermes skills — we wrote a creative library on top.

127 skill directories. Including:
• 12 deep style specialists (Cyberpunk, Ghibli, Wes Anderson, Caravaggio, Ukiyo-e…)
• 14 Forge agent protocols (the closed loop)
• 13 ComfyUI/Spark operating skills
• 10 diagnostic skills (anatomical errors, eye-color drift, scale distortion…)
• 9 camera + 10 lighting skills

Each one is film-school deep. The Cyberpunk skill alone has a magenta-cyan color-science table with hex codes.

Every shot records `skills_used`. The pipeline knows what knowledge fired.

📚 Full index: [SKILLS_INDEX.md link]

---

## Tweet 6/12 — Provenance

Click any shot and you see the complete paper trail:

✓ Kimi's visual brief + rationale
✓ Hermes compiled prompt + negative prompt + skills used
✓ Spark render (prompt ID, seed, path)
✓ Vision audit (status, score, issues)
✓ Retry lineage if remediation happened

Nothing is hidden. Everything is accounted for.

---

## Tweet 7/12 — Failure Is a Feature

Most pipelines hide failures. We ritualize them:

• Re-audit any shot
• Remediate failed shots → creates linked retry
• `retry_of` connects original → remediation → retry
• Full family tree visible in the UI

A failed shot isn't dead. It's a branch in the lineage.

[screenshot of retry lineage]

---

## Tweet 8/12 — Memory as Telemetry

`GET /api/memory/health` returns:
• Total events
• Unknown event types
• Orphan remediation events
• Shots missing audit after render

The event store isn't just logs. It's a quality dashboard for the pipeline itself.

---

## Tweet 9/12 — The Promo

We didn't just build a pipeline. We used it.

Forge NPS generated its own marketing:
• 16 cinematic hero shots
• TouchDesigner 2025 showcase with POPs + 3D textures
• Character portraits, campaign stills, motion pieces

The pipeline promoted itself.

[image collage]

---

## Tweet 10/12 — Tech Stack

| Role | Tech |
|------|------|
| Director | Kimi K2 / K2.6 via NVIDIA |
| Pipeline Brain | Hermes Agent (submodule) |
| Local Inference | LM Studio Qwen 3.6 |
| Rendering | ComfyUI / Spark |
| Vision Audit | Local vision model |
| Memory | JSONL episodic store |
| VFX | TouchDesigner 2025 + p5js |

---

## Tweet 11/12 — Why Hermes Matters Here

Hermes Agent is the only agent with a closed learning loop:
• Skills created from experience
• Memory persists across sessions
• Session continuity
• Self-improvement during use

In Forge NPS, that means every campaign makes the pipeline smarter. Skills compound. Memory deepens. The system actually learns from its own output.

---

## Tweet 12/12 — The Close

Forge NPS turns a creative brief into a traceable production sequence.

Not magic. Engineering.

🔗 Repo: [link]
📹 Demo: [link]
🎨 Gallery: [link]

Built for the @NousResearch Hermes Agent Creative Hackathon.

Forge NPS. Every shot, accounted for.

---

## Copy-Paste Ready (Single Tweets)

**Tweet 1:**
```
🎬 We didn't build another "AI image generator."

We built a film crew where 5 AI models have actual jobs:
• Kimi = Director
• Hermes = Engineer  
• Spark = Renderer
• Vision = Critic
• Memory = Historian

Every pixel has an origin. Every failure has a retry lineage.

This is Forge NPS. 🧵

📹 [video link]
```

**Tweet 2:**
```
Most AI creative tools are black boxes.

You type a prompt → magic happens → maybe you get something good.

But:
❌ No paper trail
❌ No quality gate
❌ No failure recovery
❌ No learning from mistakes

That's fine for toys. It's catastrophic for production.
```

**Tweet 3:**
```
Forge NPS assigns explicit roles. No model does everything.

Kimi plans shots → Kimi self-checks → Hermes compiles prompts → Spark renders → Vision audits → Memory records

Each stage emits structured events. The entire pipeline is observable.
```

**Tweet 4:**
```
Before a single pixel is rendered, Kimi:
• Writes a structured shot plan
• Runs a self-check critique
• Scores coverage and risks
• Stops the campaign if the plan is bad

This saves GPU hours and catches bad ideas before they get expensive.
```

**Tweet 5:**
```
Hermes isn't just chat. It's the pipeline brain:
• Campaign intake + context building
• Workflow-aware prompt compilation
• Skills tracking per shot
• Remediation orchestration
• Canonical memory writes

It learns. It repairs. It keeps continuity.
```

**Tweet 5b (skills library):**
```
We didn't just use Hermes skills — we wrote a creative library on top.

127 skill directories:
• 12 deep style specialists (Cyberpunk, Ghibli, Wes Anderson, Caravaggio…)
• 14 Forge agent protocols
• 13 ComfyUI/Spark operating skills
• 10 diagnostic skills
• 9 camera + 10 lighting

Every shot records skills_used. The pipeline knows what knowledge fired.

📚 SKILLS_INDEX.md
```

**Tweet 6:**
```
Click any shot and you see the complete paper trail:

✓ Kimi's visual brief + rationale
✓ Hermes compiled prompt + negative prompt + skills used
✓ Spark render (prompt ID, seed, path)
✓ Vision audit (status, score, issues)
✓ Retry lineage if remediation happened

Nothing is hidden. Everything is accounted for.
```

**Tweet 7:**
```
Most pipelines hide failures. We ritualize them:

• Re-audit any shot
• Remediate failed shots → creates linked retry
• retry_of connects original → remediation → retry
• Full family tree visible in the UI

A failed shot isn't dead. It's a branch in the lineage.
```

**Tweet 8:**
```
GET /api/memory/health returns:
• Total events
• Unknown event types
• Orphan remediation events
• Shots missing audit after render

The event store isn't just logs. It's a quality dashboard for the pipeline itself.
```

**Tweet 9:**
```
We didn't just build a pipeline. We used it.

Forge NPS generated its own marketing:
• 16 cinematic hero shots
• TouchDesigner 2025 showcase with POPs + 3D textures
• Character portraits, campaign stills, motion pieces

The pipeline promoted itself.
```

**Tweet 10:**
```
Tech stack:
• Director: Kimi K2 / K2.6
• Pipeline Brain: Hermes Agent
• Local Inference: LM Studio Qwen 3.6
• Rendering: ComfyUI / Spark
• Vision Audit: Local vision model
• Memory: JSONL episodic store
• VFX: TouchDesigner 2025 + p5js
```

**Tweet 11:**
```
Hermes Agent is the only agent with a closed learning loop:
• Skills created from experience
• Memory persists across sessions
• Session continuity
• Self-improvement during use

In Forge NPS, every campaign makes the pipeline smarter. Skills compound. Memory deepens. The system actually learns from its own output.
```

**Tweet 12:**
```
Forge NPS turns a creative brief into a traceable production sequence.

Not magic. Engineering.

🔗 Repo: [link]
📹 Demo: [link]
🎨 Gallery: [link]

Built for the @NousResearch Hermes Agent Creative Hackathon.

Forge NPS. Every shot, accounted for.
```
