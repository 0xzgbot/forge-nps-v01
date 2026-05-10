---
name: asset-prompt-generator
description: Transforms narrative script data into cinematic prompt batches for FLUX/LTX.
---

# Asset Prompt Generator Skill

## Overview
A specialized skill for transforming narrative script data (J10) into highly technical, cinematic prompt batches optimized for FLUX and LTX video generation models.

## Trigger Conditions
- When transitioning from Script Generation (D2) to Image/Video Generation (J8).
- When a project requires shot-by-shot visual breakdown based on a World Bible and Pilot Script.

## Workflow
1. **Input Ingestion:** Load the parsed `pilot_script.md` (from J10 parser) and the `world_bible.md`.
2. **Shot Decomposition:** Use an LLM (via KimiBridge) to decompose each script scene into a sequence of distinct visual shots.
3. **Cinematic Parameter Injection:** Apply standardized technical descriptors for:
    - **Camera Presets:** `wide`, `close_up`, `medium`, `tracking`, `drone`.
    - **Lighting Styles:** `cyberpunk neon`, `golden_hour`, `noir`, etc.
4. **Payload Construction:** Generate a structured JSON list of payloads containing the `base_prompt` (flattened string) and `metadata` (camera, subject, lighting).

## Technical Standards
- **Prompt Structure:** `[Subject/Action/Environment]. [Camera Detail]. [Named light source and direction]. [Material texture and physical imperfections]. [Composition/focal priority].`
- **Specificity Floor:** Each generated still prompt must include at least one concrete texture, one optical detail, one light-source detail, and one composition constraint.
- **Generic Token Ban:** Do not use `masterpiece`, `best quality`, `ultra-high fidelity`, or `8k` as quality substitutes. Replace them with visible material and capture details.
- **Output Format:** A JSON-compatible list of dictionaries for direct injection into the ComfyUI API layer.

## Pitfalls & Best Practices
- **Avoid Generic Terms:** Never use "cinematic" alone; always pair it with a specific descriptor (e.g., "cinematic scale," "cinematic lighting").
- **Consistency Anchors:** Always reference the World Bible's 'Consistency Anchors' to ensure character and environmental continuity across shots.
- **Fallback Logic:** If LLM decomposition fails, provide a default set of generic shots based on scene description to prevent pipeline stalls.

## Related Skills
- `genesis-engine-orchestration`: Orchestrates the initial idea-to-script phase.
- `comfyui-api-submission`: The subsequent layer for executing these prompts.
