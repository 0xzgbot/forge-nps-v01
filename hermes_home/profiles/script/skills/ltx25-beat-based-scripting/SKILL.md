---
name: ltx25-beat-based-scripting
description: A specialized workflow for transforming narrative scripts into technical production blueprints optimized for LTX 2.5 video generation.
---

# LTX 2.5 Beat-Based Scripting Standard

## Overview
A specialized workflow for transforming narrative scripts into technical production blueprints optimized for high-fidelity video generation models like LTX 2.5. This standard ensures that AI video generators receive precise temporal and visual instructions rather than abstract prose.

## Trigger Conditions
- When converting a story/narrative into a prompt-ready script for video generation.
- When preparing "Production-Ready" assets for an AI film pipeline.

## The Workflow

### 1. Character Anchor Alignment
Before writing, verify the character's physical and psychological profile against their established **Character Dossier**.
- **Movement:** Is it predatory, fluid, heavy, or mechanical?
- **Micro-expressions:** Does the character mask emotion (Julian Thorne) or express it through environmental shifts (Sylvanius)?

### 2. The "Materiality & Optics" Standard
Every scene must define the visual DNA using professional cinematography terminology:
- **Lenses:** Specify focal lengths (e.g., 35mm anamorphic for cinematic width, 100mm macro for texture).
- **Lighting:** Use specific setups (e.g., Chiaroscuro, Rembrandt, Volumetric, Rim Lighting, High-Key).
- **Textures:** Explicitly describe materials (e.g., weathered bark, matte carbon fiber, oil-stained canvas).

### 3. Beat-Based Prompting Structure
Divide every scene into time-stamped "beats" to guide the temporal evolution of the video. Use the following format:

**[Time Range]: [Camera Movement/Angle] + [Subject Action] + [Environmental/Lighting Shift]**

*Example:*
`[0-4s]: Wide shot, slow dolly-in on Elara Vance traversing a crumbling bridge; heavy volumetric dust and heat haze.`
`[4-8s]: Medium close-up, focus on her weathered skin and sweat; harsh side-lighting from a low sun.`

### 4. Production Notes Section
Each script must begin with a metadata block:
- **Theme:** The core emotional/visual concept.
- **Visual Goal:** The specific technical achievement (e.g., "Capture the relationship between character and scale").
- **Technical Focus:** Specific LTX 2.5 strengths to leverage (e.g., "Fluid motion," "Texture rendering," "Light bloom").

## Pitfalls to Avoid
- **Abstract Prose:** Never use words like "beautifully" or "intensely" without describing the *technical reason* why (e.g., instead of "beautiful light," use "warm, diffused golden hour rim lighting").
- **Static Descriptions:** AI video models need motion cues. If a scene is static, describe the movement of the environment (dust motes, swaying trees, flickering lights).
- **Ignoring Temporal Shifts:** A single prompt for an entire 10-second clip often fails. Use the beat-based structure to force the model to evolve the shot.