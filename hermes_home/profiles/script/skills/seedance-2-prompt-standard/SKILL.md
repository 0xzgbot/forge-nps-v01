---
name: seedance-2-prompt-standard
description: Expert-tier prompting protocol for Seedance 2 (ByteDance) video generation. Focuses on director-style temporal segmentation, physical descriptors, and cinematic metadata to prevent 'robotic' defaults.
version: 1.0
---

# Seedance 2 Prompting Standard

Seedance 2 rewards precise, structured, film-director language over loose descriptions. It excels at physics and multi-shot coherence when provided with temporal segmentation and physical/lighting/camera specs.

## Core Principles
- **Physics > Vibes**: Use specific physical descriptors (e.g., "hydraulic hiss", "metal scrape", "steam bursts") rather than vague adjectives.
- **Camera Language**: Use specific cinematography terms (e.g., "ultra-slow push-in", "side tracking shot", "low-angle from ground level"). 
- **Lighting**: Use physical, source-based descriptors only (e.g., "soft morning light through a window on the left") instead of "cinematic lighting".
- **Skin/Texture**: Avoid waxy defaults by specifying "realistic skin texture, visible pores, natural slight unevenness".
- **Motion vs. Camera**: To avoid artifacts, prefer either a static camera with a moving subject, or a controlled camera move. Simultaneous high-speed movement in both can cause confusion.
- **Image-to-Video Rule**: Describe only motion and camera; never re-describe the reference image. Lead with Subject + Primary Action in the first 20-30 words.
- **Compiler Requirement:** Every prompt must include temporal segmentation or explicit shot progression, one camera behavior, one source-based lighting phrase, one physical texture phrase, and one dedicated negative line.

## Prompting Formats

### 1. Timed Paragraph (Standard Narrative)
Best for: General cinematic clips, character acting, and narrative sequences.

**Structure:**
[CINEMATIC SETUP]
[Film stock / lens / aperture / camera behavior]. [Color grade]. [Lighting source]. [Atmosphere]. [Audio: sound FX only / no music]. Face stable, no deformation.

[@ image1] is [role/description]. [@ image2] is [reference for X].

0-2s: [Shot type]. [@ image1] [precise action]. [Camera move]. [Sound.]
2-3s: [Shot type]. [Action sequence with physics]. [Camera behavior]. [Sound FX.]
...
[Final timestamp]s: [Closing shot]. [Final action / movement]. [Sound fade or impact.]

**Negative Line (Append to each sequence):**
`negative: no face morph, no costume disappearing, no armor floating, no floating limbs` (Adjust based on specific risk).

### 2. JSON Format (Complex VFX/Physics)
Best for: High-precision control over complex effects like POV time-freezes or intricate mechanical movements.

```json
{
  "shot": { "composition": "...", "lens": "...", "camera_movement": "..." },
  "subject": { "description": "...", "wardrobe": "...", "props": "..." },
  "scene": { "location": "...", "environment": "..." },
  "visual_details": { "action": "...", "special_effects": "..." },
  "cinematography": { "lighting": "...", "color_palette": "...", "tone": "..." },
  "audio": { "music": "...", "sound_effects": "..." }
}
```

## Failure Modes to Avoid (The "Kill List")
- **Vague Descriptions**: "A woman holding a product" $\rightarrow$ Robotic. Use full scene + lighting + camera + emotion.
- **Waxy Skin**: Missing texture descriptors.
- **Polished Fake Look**: Using "professional", "high quality", or "studio". Counter with "handheld iPhone", "casual slightly unsteady framing".
- **Smooth AI Look:** Missing pores, cloth weave, flyaway hair, sensor noise, sweat, dust, scratches, or material wear.
- **Neutral Default**: Unspecified emotion. Always define the emotional state (e.g., "genuine surprise building to pleased recognition").
- **Vague Lighting**: "Cinematic" or "black" without specific source/intensity.
- **Moving Camera + Moving Subject Simultaneously**: Causes artifacts and motion confusion. Use one or the other; static camera while subject moves is usually the safer choice.

## Debated Techniques (Community Split)
**"Cinematic" / "4K" / "IMAX quality" suffix tags:** Widely used as a polish line at the end of prompts (e.g., `cinematic, 4K, film quality`). Some power users report a visible quality boost; others argue the gain is marginal and that strong physical descriptors earlier in the prompt matter more. Both camps continue using them. Safe to include as a final line — unlikely to hurt, may help.

## Vocabulary Cheat Sheet
- **Push-in**: "ultra-slow push-in", "almost imperceptible push-in".
- **Tracking**: "side tracking shot moving with [subject]", "ground-level tracking".
- **Angles**: "extreme macro", "low angle from floor", "POV time-freeze", "forced-foreground low-angle".
- **Feel**: "handheld phone camera feel with slight natural movement", "locked-off feel. No handheld".
- **Slow-mo**: Use "240fps feel" or "half-speed" instead of just "slow motion".
