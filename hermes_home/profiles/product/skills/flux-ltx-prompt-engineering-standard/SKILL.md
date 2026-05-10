---
name: flux-ltx-prompt-engineering-standard
description: A specialized framework for generating high-fidelity prompts optimized for Flux.2 (image) and LTX 2.5 (video). Focuses on materiality, optical physics, temporal dynamics, and cinematic technicality to move beyond "vibe-coded" descriptions.
model: gemma-4-26b
category: mlops
---

# Flux & LTX Prompt Engineering Standard

This skill provides the technical syntax required to maximize the output quality of Flux.2 and LTX 2.5 models, ensuring professional-grade cinematic results for character and environment generation.

## 1. Flux.2 (Image) Standard: "Materiality & Optics"
Flux performs best when prompts describe physical properties rather than abstract concepts. Avoid generic terms like "hyper-realistic," "masterpiece," "best quality," or naked "cinematic" polish tags.

### Compiler Integration Contract
Every FLUX2 image prompt must include concrete positive details in these fields, even when the user's brief is short:
- **Materiality:** skin pores, flyaway hairs, fabric weave, scuffed surfaces, dust, fingerprints, brushed metal, worn paint, stitching, or other physically visible texture.
- **Optics:** camera body or capture style, focal length, aperture/depth behavior, lens falloff, sensor noise or film grain.
- **Lighting Source:** named real source, direction, color temperature, catchlights, practical reflections, shadow behavior.
- **Composition:** subject scale, framing, foreground/midground/background relationship, focal priority.

For FLUX2, do not embed `negative prompt:` blocks in the positive prompt. Convert common negatives into positive targets: "sharp eyelashes and hair strands" instead of "no blur"; "clean blank background" instead of "no text"; "natural skin texture with slight asymmetry" instead of "not plastic."

### Core Components:
- **Subject Materiality:** Describe textures in detail (e.g., "weathered skin pores," "matte black carbon fiber weave," "brushed titanium," "micro-scars").
- **Optical Physics:** Specify lens and camera hardware to dictate depth of field and distortion (e.g., "Shot on Arri Alexa, 85mm anamorphic lens, f/1.4," "macro photography," "shallow depth of field with creamy bokeh").
- **Lighting Physics:** Use technical lighting terms (e.g., "high-contrast chiaroscuro," "volumetric god rays," "rim lighting," "subsurface scattering," "specular highlights").
- **Film Aesthetic:** Define the medium (e.g., "35mm film grain," "Kodak Portra aesthetic," "digital sensor noise," "cinematic color grading").

**Bad Prompt:** `A realistic portrait of a survivalist woman in a forest.`
**Standard Prompt:** `Extreme close-up, macro photography of a weathered female survivor's face. Visible skin pores and fine dirt particles under dappled sunlight filtering through leaves. Shot on Arri Alexa, 85mm lens, f/1.8. Shallow depth of field, cinematic film grain, hyper-detailed textures.`

## 2. LTX 2.5 (Video) Standard: "Temporal Dynamics"
LTX requires descriptions of *movement* and *time* to prevent "living photo" syndrome.

### Core Components:
- **Camera Motion:** Define the movement of the lens (e.g., "slow dolly zoom," "cinematic tracking shot," "handheld camera shake," "low-angle pan," "tilt up").
- **Subject Dynamics:** Describe how the subject moves (e.g., "subtle micro-expressions," "hair fluttering in wind," "rhythmic breathing," "fluid, economical movement").
- **Environmental Motion:** Describe atmospheric changes (e.g., "swirling volumetric mist," "flickering light shadows," "falling rain streaks," "drifting dust motes").
- **Temporal Consistency:** Use terms like "high-fidelity temporal consistency" and "smooth motion transitions."

**Bad Prompt:** `A video of a robot walking in a neon city.`
**Standard Prompt:** `Cinematic low-angle tracking shot following a cybernetic operative walking through a rain-slicked Neo-Kyoto alley. The camera moves with a subtle handheld shake. Neon lights reflect off wet pavement and matte black plating. High-fidelity temporal consistency, fluid motion, volumetric fog.`

## 3. Workflow: The Casting Matrix Expansion
When creating new characters or looks:
1.  **Define Archetype:** (e.g., "The Relentless Survivor").
2.  **Apply Brand DNA:** Select the color palette and lighting style from the project's master brand guide.
3.  **Generate Look Variations:** Create 3-9 distinct aesthetic directions using the technical syntax above.
4.  **Stress Test:** Run prompts through Flux (for stills) and LTX (for motion) to validate stability.

## Pitfalls to Avoid
- **Vibe-Coding:** Using abstract adjectives ("beautiful," "epic," "amazing") instead of physical descriptors.
- **Static Video Prompts:** Forgetting to describe *how* the camera or subject moves in LTX prompts.
- **Lens Neglect:** Failing to specify focal lengths, which leads to inconsistent depth of field across a series.
- **Plastic AI Smoothness:** Missing pores, flyaway hair, fabric structure, surface wear, lens grain, and real light-source behavior.
