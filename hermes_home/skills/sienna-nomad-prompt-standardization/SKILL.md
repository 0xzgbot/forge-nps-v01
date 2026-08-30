---
name: sienna-nomad-prompt-standardization
description: Protocol for generating and maintaining cinematic prompt libraries for
  the Sienna Nomad AI Influencer project.
version: 1.0.0
author: Cinesmith
license: MIT
metadata:
  hermes:
    tags:
    - sienna-nomad-prompt-standardization
    category: cinesmith
---

# Sienna Nomad Project: Prompt Library Standardization & Generation

This skill provides the protocol for generating and maintaining the cinematic prompt libraries for the Sienna Nomad AI Influencer project. It ensures technical consistency across all episodes (EP01–EP20+) in terms of hardware profiles, metadata structure, naming conventions, and stylistic depth.

## Overview
The project uses a hierarchical directory structure where each episode contains:
- `CINEMATIC_BLUEPRINT.md`: The thematic/technical master file.
- `Prompt_##_Video_##.md`: High-fidelity video generation prompts.
- `Prompt_##_Photo_##.md`: High-fidelity still image prompts.

## Standards & Protocols

### 1. Naming Conventions (STRICT)
All prompt files MUST use the expanded naming convention to prevent ambiguity:
- **Correct:** `Prompt_01_Video_01.md`, `Prompt_01_Photo_05.md`
- **FORBIDDEN:** `Prompt_01_V01.md`, `Prompt_01_P05.md` (Abbreviations are strictly prohibited).
- *Note: `CINEMATIC_BLUEPRINT.md` is the only exception to this rule.*

### 2. File Structures & Content Integrity

#### A. CINEMATIC_BLUEPRINT.md
Must define:
- **Theme:** Narrative/visual core of the episode.
- **Temporal Window:** Specific time of day (e.g., Blue Hour, High Noon, Golden Hour).
- **Environmental Anchors:** Weather, atmosphere (haze, dust), and terrain characteristics.
- **Technical Profile (HARD LOCK):** Camera must be `Arri Alexa 65`. Lenses must be from the `Zeiss Master Prime` series. 
- **FORBIDDEN HARDWARE:** RED V-Raptor, Cooke Anamorphic, Panavision Anamorphic.

#### B. Photo Prompts (`Prompt_##_Photo_##.md`)
Must contain:
- `# Prompt_##_Photo_##` (Single header only).
- `Technical Metadata`: Camera (Arri Alexa 65), Lens (Zeiss Master Prime), Aperture (Discrete value, e.g., f/8), ISO, Film Grain.
- `Visual Description`: Highly descriptive, sensory language focusing on texture and light.
- `Environmental Anchors`: Contextual details (wind, dust, moisture).
- **FORBIDDEN CONTENT:** No duplicate headers; no copy-pasted sections from the CINEMATIC_BLUEPRINT.

#### C. Video Prompts (`Prompt_##_Video_##.md`)
Must contain:
- `# Prompt_##_Video_##` (Single header only).
- `CINEMATIC CONTEXT`: Narrative movement/intent.
- `VISUAL BLUEPRINT`: Detailed visual descriptions of motion and lighting.
- `FLUX_DIR_COMMAND`: Specialized block for AI engine execution consistency. 
  - **MUST NOT USE:** Generic values like `[camera_motion: cinematic]`.
  - **REQUIRED FORMAT:** Must include specific parameters:
    - `camera_motion`: [type, speed, altitude/level] (e.g., `[camera_motion: slow_tracking, speed: meditative, altitude: eye_level]`)
    - `lighting`: [quality, source, characteristics] (e.g., `[lighting: golden_hour, soft_ambient, high_dynamic_range]`)
    - `lens`: [focal length, depth of field, grain] (e.g., `[lens: 35mm, shallow_depth_of_field, organic_grain]`)

### 3. Generation & Cleanup Workflow (Agentic Loop)
1. **Analyze:** Read the existing `CINEMATIC_BLUEPRINT.md` from a completed episode to extract formatting and technical standards.
2. **Initialize:** Create the directory for the new episode.
3. **Draft Blueprint:** Generate the thematic foundation based on project requirements.
4. **Batch Generate:** Use `delegate_task` with the `tasks=[]` array to parallelize the creation of Video and Photo assets across multiple sub-agents.
5. **Audit & Sanitize (CRITICAL):** 
   - Verify naming compliance.
   - Scan for "hallucination artifacts": Replace/Remove "**polished vitrification**" and "**amberous luminosity**" (use "golden hour").
   - Ensure no nested `Prompts/` subdirectories exist; all files must be at the episode root.

## Pitfalls & Lessons Learned
- **Naming Error:** Early iterations used `V01/P01`. This caused confusion with directory structure and indexing. Always use the full words `Video` and `Photo`.
- **Hardware Drift:** Do not introduce alternate camera or lens brands. The profile is locked to Arri + Zeiss.
- **Command Weakness:** Generic commands like "cinematic" break high-fidelity workflows. Always provide structured parameter blocks.
- **Content Pollution:** Photo prompts often accidentally inherit large chunks of the Blueprint during manual copy-pasting; always audit for duplicate headers and redundant sections.
