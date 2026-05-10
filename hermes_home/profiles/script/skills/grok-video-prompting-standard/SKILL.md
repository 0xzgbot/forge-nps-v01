---
name: grok-video-prompting-standard
description: Expert-tier prompting protocol for Grok Imagine Video Generation (xAI). Focuses on 'Hollywood sequence' narrative prose, SCENE LOCK consistency, and handheld realism.
version: 1.0
---

# Grok Video Prompting Standard

Grok rewards authoritative "Movie Director" prose over weighted tags or syntax-heavy prompts. It excels at multi-scene sequences and sharp transitions when using a cohesive narrative approach.

## Core Principles
- **Director Prose**: Use commanding, descriptive language (e.g., "A sweeping orbital pan reveals...") rather than comma-separated tags or weights like `(word:1.2)`. Weighting is ineffective in Grok.
- **Physics & Materiality**: Explicitly name physical properties to trigger high-fidelity renders (e.g., "viscous liquid," "granulated concrete texture," "heat shimmer").
- **Handheld Realism (UGC Style)**: For realistic/casual footage, use the specific string: `handheld — natural slight shake, micro-movements, subtle instability, as if filmed by a real operator`.
- **Image-to-Video (I2V) Rule**: Describe *only* motion and camera changes. Never re-describe the static reference image. Lead with Subject + Primary Action in the first 30 words.
- **Compiler Requirement:** Use full-sentence director prose, not tag soup. Include subject action, camera behavior, lighting source, physical atmosphere, and a drift-prevention phrase for every generated video prompt.

## Consistency & Extension Protocol
To maintain visual, lighting, and character consistency across extended clips:

### 1. SCENE LOCK (Mandatory for Extensions)
When using Grok's extension features to build longer videos from a base clip, always prepend the prompt with:
`SCENE LOCK: [Maintain exact camera setup / fixed tripod / same subject wardrobe / identical lighting]`

### 2. Extension Chaining Strategy
*   **Base Clip**: Generate a high-quality 10s narrative foundation.
*   **Extensions**: Chain 2-5s increments using the `SCENE LOCK` prefix to prevent "teleporting," morphing, or sudden shifts in environment/character.

## Prompting Formats

### 1. Cinematic Sequence (Standard)
Best for high-production, narrative clips.
**Structure:**
`[Style/Film Stock]. [Subject + Primary Action]. [Specific Camera Movement]. [Lighting Source & Quality]. [Physics/Atmospheric Details]. [Finish/Mood].`

*Example:* `35mm film stock. A rugged explorer pushes through dense tropical ferns, sweat glistening on his brow. A slow dolly-in follows his determined gaze. Dappled sunlight pierces the canopy, creating sharp volumetric rays. Tropical humidity creates a thick haze in the air. Intense and adventurous.`

### 2. Multi-Shot/Scene-Block
Best for rapid sequences or "cuts."
**Structure:**
`[Initial Shot Description]. [Action]. [Cut to: Shot 2 Description]. [Action]. [Negative Prompting for stability].`

*Example:* `Extreme macro of a mechanical eye dilating. Cut to: Wide shot of the android standing in a neon-lit hangar. The android turns its head sharply toward the camera. NEGATIVE: no morphing, no limbs disappearing, no sudden color shifts.`

## Failure Modes to Avoid
- **Tagging/Weighting**: Using `(word:1.5)` or `--no` style syntax (Grok prefers natural language).
- **Vague Lighting**: "Cinematic lighting" $\rightarrow$ Use "Single focused spotlight casting sharp shadows."
- **Static/Neutral Defaults**: "A man walking" $\rightarrow$ "A weary traveler trudging through thick mud, shoulders slumped with heavy exertion."
- **Morphing/Drift**: Failing to use `SCENE LOCK` during extensions or missing the `NEGATIVE:` block for complex action.
- **Smooth AI Look:** Missing material/skin/environment physics. Add pores, sweat, cloth movement, pavement texture, humidity, dust, rain, or lens noise as appropriate.

## Vocabulary Cheat Sheet
- **Camera**: `sweeping orbital pan`, `slow dolly-in`, `low-angle ground view`, `handheld micro-shake`, `fixed tripod`.
- **Physics**: `viscous`, `granular`, `shimmering`, `splashing`, `collapsing`, `friction`.
- **Lighting**: `volumetric rays`, `dappled sunlight`, `harsh neon flicker`, `warm tungsten glow`.
