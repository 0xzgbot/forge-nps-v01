# Forge NPS Submission and Demo Guide

Event: Hermes Agent Creative Hackathon  
Deadline: May 3, 2026

## Judge-Facing Positioning

Forge NPS is a creative production pipeline with explicit model roles:

1. Kimi is the director planner: structured shot plans and critique.
2. Hermes is the pipeline brain: campaign intake, prompt compilation, continuity, remediation.
3. Spark/ComfyUI renders.
4. Vision audit gates quality.
5. Memory captures provenance, failures, retries, and outcomes.

## What To Show

Show one coherent path, in this order:

1. Run a campaign from a single creative brief.
2. Show Kimi raw and structured planning events.
3. Show Hermes compiler profile, skills, and final prompt.
4. Show Spark render output with prompt id.
5. Show audit pass/fail.
6. Show remediation retry lineage on a failed shot.

If this sequence is clear, the system reads as a working pipeline rather than a collection of disconnected features.

## Mandatory Proof Points

- Kimi endpoint configured and connection tested.
- Live `run-campaign` stream includes `kimi_raw`, `kimi_plan`, and `kimi_review` or a visible warning.
- Shot detail view includes:
  - Kimi plan fields
  - Hermes compiled prompt
  - skills used
  - audit status/score/issues
  - retry lineage when present
- Memory health endpoint returns structured counts.

## Three-Minute Demo Script

### 0:00-0:30 Preflight

1. Launch the app:

   ```bash
   cd ~/Desktop/forge_nps_v01
   python3 -m dashboard.forge_dashboard
   ```

2. Open `http://localhost:7000`.
3. In Settings confirm:
   - Kimi/NVIDIA endpoint and key
   - LM Studio host/model
   - ComfyUI/Spark host
   - successful connection tests

### 0:30-2:00 Live Campaign

1. Enter a concise cinematic brief.
2. Click **Run Campaign**.
3. Narrate stream events:
   - `profile` / Hermes campaign intake
   - `kimi_raw`
   - `kimi_plan`
   - `kimi_review` or warning
   - `compiler`
   - `spark`
   - `memory`
4. Open a rendered shot and show:
   - Kimi visual brief/rationale/constraints
   - Hermes compiled prompt and negative prompt
   - workflow profile and skills used
   - audit status, score, and issues

### 2:00-2:40 Failure and Recovery

1. Filter to failed shots or select one shot for re-audit.
2. Run **Re-Audit Selected**.
3. Run remediation on a failed shot if available.
4. Show retry linkage:
   - original shot id
   - `retry_of`
   - remediated prompt
   - final audit outcome

### 2:40-3:00 Close

Use this close:

> Forge NPS turns a creative brief into a traceable production sequence: Kimi directs, Hermes compiles and repairs prompts, Spark renders, vision audits quality, and memory keeps the evidence.

## 60-90 Second Cut

1. Hook: best visual outputs.
2. Pipeline run: live stream with callouts.
3. Failure handling: re-audit or remediation retry.
4. Close: one-line model-role summary.

## Tweet / Writeup Checklist

- Mention Kimi and Hermes roles explicitly.
- Mention Spark rendering and vision audit gate.
- Mention memory as provenance and health telemetry.
- Avoid generic “AI platform” language.

## Stability Gate

Before recording, run [STABILITY_CHECKLIST.md](~/Desktop/forge_nps_v01/STABILITY_CHECKLIST.md) top to bottom.

## Skills Library Proof Point

Forge ships a 155-skill curated Hermes library: 14 Forge agent protocols (the closed loop), 13 ComfyUI/Spark operating skills, 15 deep style specialists (Cyberpunk, Ghibli, Wes Anderson, Caravaggio, Film Noir, Impressionism…), 10 diagnostic failure-mode skills, plus cinematography, lighting, FLUX.2 Dev, LTX 2.3, sound, VFX, schema, and industry skills. Profile-mounted libraries are active for `live`, `character`, `product`, `script`, `forgehermes`, and `trading`. Every shot record carries `skills_used`, so judges can trace which knowledge fired on which render.

Walk judges through the index in 30 seconds: open [SKILLS_INDEX.md](~/Desktop/forge_nps_v01/SKILLS_INDEX.md) → point to the **Forge Agent Protocols** section (the closed loop) → point to the **Style Specialists** section → open one (e.g., [hermes_home/skills/cyberpunk_neon_noir_specialist/SKILL.md](~/Desktop/forge_nps_v01/hermes_home/skills/cyberpunk_neon_noir_specialist/SKILL.md)) to show the depth.

## Canonical References

- [README.md](~/Desktop/forge_nps_v01/README.md)
- [INSTALLATION_AGENT_GUIDE.md](~/Desktop/forge_nps_v01/INSTALLATION_AGENT_GUIDE.md)
- [PIPELINE_CONTRACT_SUMMARY.md](~/Desktop/forge_nps_v01/PIPELINE_CONTRACT_SUMMARY.md)
- [SKILLS_INDEX.md](~/Desktop/forge_nps_v01/SKILLS_INDEX.md)
- [data/contracts/pipeline_contract.json](~/Desktop/forge_nps_v01/data/contracts/pipeline_contract.json)
