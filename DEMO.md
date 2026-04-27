# Forge NPS — Demo Script

60-second judge walkthrough. Everything visible on screen, no terminal.

---

## Setup (before judges arrive)

1. Dashboard running: `http://localhost:7000`
2. LM Studio loaded with qwen model on 100.74.164.1:1234
3. ComfyUI Spark online at 100.112.87.8:8188
4. One existing character in system (Elara Vance with anchor image)

---

## The 60-Second Demo

**0:00 — Open dashboard**
> "This is Forge. You give it a brief. It produces a campaign."

Point to the Hermes Command Center. Show the event log panel — labeled by model. Show the Characters tab — Elara's anchor image visible.

---

**0:08 — Set brief and length**
> "Car commercial. Golden hour. 30 seconds — six shots."

Type brief in the input. Click `[30s]` length chip. Click **Run Campaign**.

---

**0:12 — Kimi directs**
> "Kimi K2 acts as the director. It reads the brief and the world bible, then generates a shot list."

Event log shows: `[KIMI K2 ✍] Generating shot list... Shot list ready: 6 shots`

---

**0:20 — Hermes writes**
> "Hermes is the creative writer. It reads Kimi's shot descriptions and writes the actual Stable Diffusion prompts — but before it writes, it checks memory for anything it's learned."

Event log shows: `[HERMES 🧠] Writing prompt for SHOT_001... SHOT_001: wide angle hero shot, golden hour rim light, anamorphic lens flare...`

---

**0:30 — Spark renders**
> "The prompt goes to Spark — our ComfyUI GPU cluster. Node 6 gets the prompt. Node 9 gets the seed."

Event log shows: `[SPARK ⚡] Dispatching SHOT_001... queued`

Image appears in filmstrip as it downloads.

---

**0:40 — Kimi-VL audits**
> "Kimi-VL looks at the rendered image against Elara's reference. It's checking: right eye color? Right build? Right clothing signature?"

Event log shows: `[KIMI-VL 👁] Score: 0.61 FAIL — Eye color mismatch. Found: brown. Expected: emerald.`

FAIL badge appears on the filmstrip thumbnail.

---

**0:48 — Hermes remediates**
> "Hermes reads that finding, cross-references memory, and rewrites."

Event log shows: `[HERMES 🧠] RETRY — Remembered: specify iris color explicitly. Rewriting SHOT_001...`

New render dispatched. New audit fires.

Event log shows: `[KIMI-VL 👁] Score: 0.94 PASS`

PASS badge replaces FAIL on filmstrip.

---

**0:55 — Memory updates**
> "And that rule gets written to memory. Next campaign, Hermes won't make that mistake."

Memory panel shows new entry: *"Always specify iris color explicitly for Elara Vance shots. Confirmed: 1"*

Event log shows: `[MEM 💾] Rule learned: specify iris color for Elara Vance`

---

**1:00 — Close**
> "Three models. One pipeline. Gets better every time it runs."

---

## Hermes Chat Demo (bonus 30 seconds)

Click into the Hermes Live panel. Type:

> *"Write me an opening shot for a dawn sequence with Elara"*

Hermes streams a response in real time — in character as creative director.

> "This is the creative director you can talk to. Ask it anything about the campaign."

---

## Key Talking Points

- **Multi-model by design** — each model does what it's best at: Kimi reasons, Hermes creates, Kimi-VL sees, qwen writes
- **Memory is the differentiator** — not just a pipeline, a system that compounds learning
- **Remediation is automatic** — no human in the loop for common failures
- **Runs local + cloud** — Hermes/qwen on local LM Studio, Kimi on NIM, renders on Spark

---

## If Something Breaks

| Problem | Fix |
|---------|-----|
| LM Studio offline | Hermes uses fallback prompt (Kimi description + style suffix) — pipeline still runs |
| Kimi-VL times out | Audit skipped, render still saved, memory write skipped |
| ComfyUI queue full | Stream shows "queued" — image appears when slot opens |
| Run Campaign returns error | Check KIMI_API_KEY is set in environment, not read from config.json |
