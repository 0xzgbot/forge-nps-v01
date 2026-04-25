---
name: forge-onboarding-pipeline
title: Forge Onboarding Pipeline
description: Validated workflow for metadata-driven training dataset generation and auto-captioning (Chunks 6 & 7).
---

# Forge Onboarding Pipeline: Metadata-Driven Captioning

This skill outlines the validated workflow for generating and captioning training datasets within the Forge MediaEngine project. It ensures that image generation (Chunk 6) and automated captioning (Chunk 7) are architecturally coupled via filename metadata.

## Overview
To enable high-precision LoRA training without expensive vision-model inference for every tag, this workflow encodes visual attributes (pose, view, crop, lighting, background) directly into the image filenames during the generation phase. The captioning agent then parses these filenames to create structured `.txt` sidecar files.

## Workflow Steps

### 1. Image Generation (Chunk 6)
**Script:** `pipelines/onboarding/generate_training_images.py`
- **Logic:** Uses a distribution of shot types (Isolation, Environmental, Close-up, Full Body).
- **Prompt Construction:** `[QUALITY] + [SUBJECT] + [POSE] + [VIEW] + [CROP] + [LIGHTING] + [BACKGROUND]`
- **Mandatory Filename Format:** 
  `{slug}_char1_train_{idx}_{pose}_{view}_{crop}_{lighting}_{bg}.png`
- **Requirement:** All metadata components (pose, view, etc.) must be sanitized of spaces/special characters (replace with `_`) before being appended to the filename.

### 2. Automated Captioning (Chunk 7)
**Script:** `pipelines/onboarding/caption_images.py`
- **Logic:** Reads all `.png` files in the project's training directory.
- **Metadata Extraction:** Uses regex/string splitting to parse the structured filename segments.
- **Caption Format:**
  `{trigger_word}, {pose}, {view}, {crop}, {lighting}, {bg}, {natural_caption}`
- **Note:** `{natural_caption}` can be a simulated placeholder or an actual BLIP2/WD-Tagger output, but the structured tags MUST come from the filename for training reliability.

## Pitfalls & Troubleshooting
- **Filename Mismatch:** If `generate_training_images.py` is updated to change the number of segments in the filename, `caption_images.py` **must** be updated simultaneously to prevent index errors or incorrect tag assignment.
- **Missing Banks:** Ensure all required `.txt` banks (pose, view, etc.) exist in `projects/[slug]/banks/` before running Chunk 6.
- **Sanitization:** Always ensure that bank entries used in filenames do not contain spaces; use underscores to prevent breaking the split logic in the captioner.

## Verification Protocol
1. Run `generate_training_images.py` with a small `--count` (e.g., 5).
2. Verify files exist: `ls projects/[slug]/assets/training_images/*.png`.
3. Run `caption_images.py [slug]`.
4. Confirm `.txt` counts match `.png` counts.
5. Inspect a sample `.txt` file to ensure the first 6 comma-separated values match the filename segments.
