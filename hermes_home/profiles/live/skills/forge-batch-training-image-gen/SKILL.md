---
name: forge-batch-training-image-gen
description: Specialized skill for generating large batches of diverse training images for character consistency in Forge.
---

# Forge Batch Training Image Generation

A specialized skill for generating large batches (100+) of high-quality, diverse training images to ensure character consistency in LoRA or Flux Redux workflows.

## Trigger Conditions
- When tasked with "training image generation" within the Forge MediaEngine framework.
- When a project requires establishing visual consistency for a specific subject/character.

## Operational Protocol

### 1. Prerequisites
- A valid `PROJECT.md` file exists in `/Users/zgbot/Desktop/forge/projects/[slug]/`.
- All required character bank files exist in `/Users/zgbot/Desktop/forge/projects/[slug]/banks/` (`pose_bank.txt`, `view_bank.txt`, etc.).
- `z_image_turbo_api.json` is available in `/Users/zgbot/Desktop/forge/workflows/`.

### 2. Execution Steps (Implementation Logic)
1. **Data Ingestion:** Parse `PROJECT.md` for character description and trigger word. Load bank files into memory.
2. **Prompt Engineering:** Generate a list of prompts based on the defined distribution:
   - **30% Isolation Shots:** White/black BG, varied angles + crop, close detail.
   - **40% Environmental:** Natural/urban/interior BG, mid-range crop, varied lighting.
   - **20% Close-up Face:** Extreme close-up/close-up crops, varied lighting.
   - **10% Full Body Dynamic:** Full body crop, varied pose + lighting.
3. **Assembly Formula:** `[Quality Constants] + [Subject] + [Random Pose] + [Random View] + [Random Crop] + [Random Lighting] + [Random Background]`.
4. **Batch Submission:** 
   - Use `comfy_client` to submit the entire batch to the GPU queue (Port 8188/8189) *before* beginning the polling loop to maximize throughput.
5. **Asynchronous Polling:** Implement a single loop that polls all prompt IDs, reporting progress every 10 completions.
6. **Asset Retrieval:** Download and save PNGs to `projects/[slug]/assets/training_images/` using the naming convention `{slug}_char1_train_{i:03d}.png`.

### 3. Pitfalls & Error Handling
- **Parsing Failures:** If `PROJECT.md` is malformed, fallback to a generic "a character" subject rather than crashing.
- **ComfyUI Connectivity:** Handle `TimeoutError` during polling gracefully; do not terminate the batch if one job hangs.
- **File Path Integrity:** Use absolute paths for all file operations to ensure stability across different execution contexts.

## Verification Checklist
- [ ] Verify `IMAGE_COUNT` (use 5 for testing, 100+ for production).
- [ ] Confirm prompt diversity (filenames should reflect increasing index).
- [ ] Confirm files are stored in the correct `/assets/training_images/` subfolder.
