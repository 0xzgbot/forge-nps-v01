---
name: ltx23-prompting-workflow
description: High-precision prompting protocol for LTX 2.3 (Lightricks) video generation, optimized for ComfyUI VFX pipelines and local control. Incorporates cinematic prose, camera motion selectors, and the community-standard 3-stage sampling hack.
model: LTX 2.3 (Lightricks)
---

# ltx23-prompting-workflow

## Overview
This skill provides a standardized framework for generating cinematic, high-fidelity prompts specifically designed for the LTX 2.3 model architecture. It leverages director-level specificity to maximize motion dynamics and temporal coherence, optimized for ComfyUI VFX production on local hardware (e.g., RTX 3090).

## Core Principles
- **Cinematic Prose:** Avoid generic descriptors; use professional filmmaking terminology (lens types, lighting sources, film stocks).
- **Motion Priority:** The model rewards explicit camera movement and physical interaction descriptors.
- **3-Stage Sampling Requirement:** All LTX 2.3 workflows should implement the community-standard "3-stage sampling" to ensure micro-expressions and dynamic depth.
- **I2V/V2V Constraint:** When using reference images/videos, describe *only* motion, camera, emotion, and changes. Do not re-describe the static subject.
- **Specificity Floor:** Every prompt must name the camera behavior, subject motion, environmental motion, light continuity, and one explicit artifact risk in the negative field.
- **Anti-Living-Photo Rule:** A prompt that only says "preserve identity," "gentle parallax," or "cinematic motion" is invalid. It must describe what visibly changes frame-to-frame.

## Prompt Architecture (The 6-Element Structure)
Every prompt should be structured as a single cinematic paragraph following this sequence:

1. **[Genre / Film Stock / Era]:** e.g., "Vintage 1985 dark fantasy film", "Kodak Portra 400 aesthetic".
2. **[Subject Description]:** Detailed physical characteristics and clothing.
3. **[Precise Action + Emotion]:** What is happening and the underlying feeling (e.g., "releasing a paper lantern with a mournful expression").
4. **[Camera Motion]:** Explicit movement (e.g., "slow lens push from medium close-up to close-up", "snap zoom", "Dolly In").
5. **[Lighting Source + Atmosphere]:** Physical light descriptions (e.g., "soft side light from the morning sun through fog", "rim lighting").
6. **[Stylized Tone / Framing]:** Final aesthetic polish (e.g., "central framing with telephoto compression, melancholic tone").

## Implementation Standards

### T2V (Text-to-Video) Example
> A silver-haired elderly woman in a loose linen dress stands at the edge of a misty forest lake at dawn, her weathered hands releasing a paper lantern onto the still water; the camera uses a slow lens push from medium close-up to close-up, capturing her peaceful yet mournful expression; soft side light from the early morning sun filters through the fog, casting a warm glow and rim light around her silhouette; the scene is composed with central framing and uses a telephoto lens to compress the depth of the misty forest; stylized with a poetic, melancholic tone and naturalistic visual style.

### I2V/V2V (Image/Video-to-Video) Protocol
*Focus on the first 20-40 words for maximum impact.*
- **Rule:** Do not re-describe the image.
- **Goal:** Describe how the pixels move.
- **Example:** "The subject's eyes widen in sudden terror as the camera performs a rapid snap zoom; heavy rain begins to lash against their skin, creating realistic water ripples and splashing."

### Negative Prompting (Critical)
Always include a negative prompt field to mitigate known failure modes:
`negative: no drum sticks, no stiff motion, no flat lighting, no artifacts, no morphing, no flickering`

Keep the negative prompt in the dedicated negative field. Do not bury it inside the positive prompt paragraph.

## Advanced Techniques & Troubleshooting

| Issue | Solution |
| :--- | :--- |
| **Stiff/Flat Motion** | Use 3-Stage Sampling and more explicit Camera Motion descriptors. |
| **Loss of Precision** | Integrate ControlNets (Canny, Depth, or Pose) into the ComfyUI workflow. |
| **Character Drift in V2V** | Use Start/End frame images + IC-LoRA "SCENE LOCK" technique. |
| **Unwanted Audio Artifacts** | Ensure a robust negative prompt is present if audio generation is active. |

### 3-Stage Sampling (Community Standard)
Run the KSampler in three sequential passes with progressively decreasing denoise values rather than a single full-denoise pass. This prevents flat motion and builds micro-detail in layers:

1. **Pass 1 — Structure** (`denoise: 1.0`, ~10 steps): Establishes composition, subject, rough motion
2. **Pass 2 — Motion Refinement** (`denoise: 0.65`, ~10 steps): Refines movement and temporal coherence
3. **Pass 3 — Detail Polish** (`denoise: 0.35`, ~5 steps): Adds micro-expressions, texture, and fine motion

In ComfyUI: chain three KSampler nodes in series, each taking the latent output of the previous. Use the same seed across all three passes for coherence.

### IC-LoRA SCENE LOCK (Video Extension)
IC-LoRA (Image Conditioning LoRA) is a technique for extending clips beyond their native length without scene drift. SCENE LOCK refers to anchoring the extension by conditioning on both the last frame of the prior clip and a target end frame.

**Implementation in ComfyUI:**
- Load the final frame of your generated clip as a start-frame reference
- Optionally provide a target end-frame image to direct where the extension lands
- Apply IC-LoRA weights to the base LTX 2.3 model before sampling
- Prompt describes only the continuation motion — do not re-describe the locked scene

This preserves lighting, wardrobe, environment, and character appearance across clips that would otherwise drift.

## Workflow Integration
For professional VFX, chain this protocol as follows:
1. **Reference Generation:** Use Flux/SDXL for high-quality reference stills.
2. **Motion Injection:** LTX 2.3 I2V/V2V using the structured prompt above.
3. **Temporal Extension:** Use IC-LoRA SCENE LOCK to extend clips while preserving scene continuity.
4. **Upscaling:** Final pass with RTX Video Super Resolution (x2/ULTRA) post-VAE decode in ComfyUI.

## Skill Version
v1.5 (Updated: 2026-04-17)
Author: Hermes Agent Team
Compatibility: LTX 2.3 models only (LTX0203022b0dev0fp8, ltx-2.3-22b distilled)
