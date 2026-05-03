# Forge NPS — Final Discord Submission Post

Channel: `#creative-hackathon-submissions`  
Event: Hermes Agent Creative Hackathon  
Tags: `@NousResearch` `@Kimi_Moonshot`

---

## Copy-Paste Post

**Forge NPS — a creative production pipeline with a memory**

I’m entering **Forge NPS** in the Hermes Agent Creative Hackathon.

Forge is not another “prompt in, image out” tool. It is a traceable creative production system where each model has a real job:

- **Kimi** plans and critiques the campaign before render.
- **Hermes** is the pipeline brain: intake, memory, skill selection, prompt compilation, remediation, and canonical event writes.
- **Spark / ComfyUI** renders image and video workflows.
- **Vision audit** gates quality with scores and issues.
- **Memory** records provenance, failures, fixes, retries, and outcomes.

The core idea: creative AI should behave like production engineering. Every shot should have a plan, a paper trail, a quality gate, and a memory of what happened.

## What makes it different

**1. Kimi does real director work**

Kimi is not used for one short prompt. Forge uses Kimi for structured planning and critique:

- brief decomposition
- shot planning
- visual rationale
- coverage critique
- risk scoring
- revision when critique fails

Bad plans get caught before GPU time gets burned.

**2. Hermes is the pipeline brain**

FastAPI routes are thin adapters. Hermes owns the production logic:

- campaign intake
- context and memory retrieval
- workflow-aware prompt compilation
- skill tracking per shot
- remediation orchestration
- canonical writes to episodic memory

This is the part that makes the system feel agentic instead of scripted.

**3. The skills library turns Forge into a virtual agency**

Forge now ships a **155-skill Hermes library**, including:

- 14 Forge closed-loop agent protocols
- 13 Spark / ComfyUI operating skills
- 15 style specialists
- 16 camera and movement skills
- 13 lighting and color skills
- 10 diagnostic failure-mode skills
- FLUX.2 Dev specialists
- LTX 2.3 video/audio/motion specialists
- VFX, motion graphics, sound, industry verticals, schemas, and prompt-engineering libraries

Every shot records `skills_used`, so the app can show which expertise fired on which render. It is not just “style tags”; it is an inspectable agency brain.

**4. Memory is prominent and inspectable**

Forge records:

- every campaign event
- every render attempt
- every audit result
- every failure
- every remediation
- every retry relationship

The memory health endpoint checks the memory system itself for missing audits, orphan remediation events, unknown event types, and other integrity issues.

**5. Failure is a first-class workflow**

A failed shot is not hidden. It can be re-audited, remediated, re-rendered, and linked back with `retry_of`.

The app can show:

`original shot -> failed audit -> remediation -> retry render -> final audit`

## What judges can inspect

Click any shot and you can inspect:

- Kimi visual brief and rationale
- Kimi critique result
- Hermes compiled prompt
- negative prompt
- workflow profile
- skills used
- Spark prompt id / seed / output path
- audit status, score, and issues
- retry lineage

The evidence is built into the app.

## Built with itself

Forge also generated and packaged its own launch material:

- cinematic marketing website
- matching app UI concept
- generated hero graphics
- campaign stills
- promo-video attempts
- TouchDesigner showcase kit

The pipeline was used to package the pipeline.

## Links

- **Repo:** [link]
- **Demo video:** [link]
- **Marketing site:** [link]
- **X thread:** [link]
- **Skills index:** `SKILLS_INDEX.md`

## Closing

Forge NPS turns a creative brief into a traceable production sequence:

**Kimi directs. Hermes operates. Spark renders. Vision audits. Memory compounds.**

Built for the Hermes Agent Creative Hackathon with **Hermes Agent** and **Kimi / Moonshot AI**.

---

## Short Backup Version

**Forge NPS — the creative studio with a memory**

I’m entering Forge NPS in the Hermes Agent Creative Hackathon.

Forge is a traceable AI production pipeline:

- Kimi plans and critiques campaigns.
- Hermes is the pipeline brain.
- Spark / ComfyUI renders.
- Vision audits quality.
- Memory records every event, failure, remediation, and retry.

The biggest proof point is the skill system: Forge now ships a **155-skill Hermes library** covering closed-loop agent protocols, Spark operations, style specialists, camera, lighting, diagnostics, FLUX.2 Dev, LTX 2.3, VFX, sound, schemas, and industry verticals.

Every shot records `skills_used`, plus Kimi plan data, Hermes compiled prompts, Spark render metadata, audit scores, and retry lineage.

It is not a black box. It is a production system with receipts.

**Kimi directs. Hermes operates. Spark renders. Vision audits. Memory compounds.**

Repo: [link]  
Demo: [link]  
Site: [link]  
X thread: [link]
