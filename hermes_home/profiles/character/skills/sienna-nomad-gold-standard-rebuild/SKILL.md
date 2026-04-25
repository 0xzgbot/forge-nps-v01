---
name: sienna-nomad-gold-standard-rebuild
description: A specialized workflow for rebuilding and standardizing AI prompt libraries to meet high-fidelity brand requirements. It ensures character consistency, spatial grounding (Van Spatial Inventory), temporal lighting continuity, and technical metadata compliance.
---

# Sienna Nomad Gold Standard Rebuild Protocol

## Purpose
To transform raw or inconsistent AI prompts into a "Gold Standard" library that maintains absolute narrative and visual continuity across an entire production episode.

## Prerequisites
- **Brand Bible:** Must be up-to-date with Character Anchors, Environment/Van Spatial Inventory, and Lighting Protocols.
- **Target Directory:** A directory containing the `.md` files to be rebuilt.
- **Template Reference:** The `CINEMATIC_BLUEPRINT.md` for the current episode.

## Rebuild Requirements (The "Gold Standard" Checklist)

### 1. Character Anchors
Every prompt MUST explicitly name and describe:
- **Sienna:** [Age/Build] + [Sun-kissed skin, freckles] + [Golden-Rust hair with blonde highlights].
- **Aura:** [Breed: Vizsla] + [Sleek, muscular build] + [Golden-Rust coat with sun-bleached highlights].

### 2. Spatial Anchoring (The Van Protocol)
If the scene occurs within or near the van, you MUST name a specific location from the `[THE VAN: SPATIAL INVENTORY]` in the Brand Bible.
- **Valid Locations:** *Rear Living Area*, *Kitchenette*, *Driver/Passenger Area*, *Side Door*, *Rear Barn Doors*.
- **Forbidden:** Using generic terms like "the van" or "inside the vehicle".

### 3. Temporal Lighting Continuity
Prompts must follow a logical time-of-day progression to prevent visual jumps:
- **Pre-Dawn:** Deep Blue Hour, cool tones, low visibility.
- **Transition:** Soft lavender, pink hues, diffused light.
- **Golden Hour:** Warm, high-contrast sunlight, long shadows, golden highlights.
- **Daylight (if applicable):** Natural sun, high clarity.

### 4. Technical Metadata Compliance
- **Photo Prompts:** Must maintain professional photography descriptors (e.g., `85mm, f/1.8`).
- **Video Prompts:** MUST include a structured `FLUX_DIR_COMMAND` block containing:
    - `camera_motion`: [Speed/Altitude/Direction]
    - `lighting`: [Quality/Temperature]
    - `lens`: [Focal length and depth of field]

### 5. Content Scrubbing
- **Banned Phrases:** Ensure zero presence of "stygian shadows", "polished vitrification", "amberous luminosity", "saffron-tinted radiance", or "eroded morphology".

## Execution Workflow
1. **Analyze:** Read the episode's `CINEMATIC_BLUEPRINT.md` to understand the narrative arc and lighting progression.
2. **Extract:** Parse existing `.md` files for core creative intent/action.
3. **Augment:** Inject Character, Spatial, and Temporal anchors into the extracted text.
4. **Verify:** Run a final check against the Banned Phrases list and Technical Metadata requirements.
5. **Overwrite:** Save the improved content back to the original `.md` files.
