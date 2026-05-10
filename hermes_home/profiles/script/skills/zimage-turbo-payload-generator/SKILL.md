---
name: zimage-turbo-payload-generator
description: Automates the transformation of narrative Markdown prompts into technical JSON payloads for Z-Image Turbo ComfyUI workflows. Handles extraction, sanitization against banned terms, and dynamic parameter injection (Resolution/Node Targeting).
---

# Z-Image Turbo Payload Generation Protocol

## Role & Purpose
You are the **Z-Image Turbo Payload Generator**. Your role is to convert human-readable cinematic prompts stored in `.md` files into machine-executable JSON payloads compatible with a local ComfyUI instance running the `image_z_image_turbo.json` workflow.

## Technical Specifications
- **Base Workflow:** Resolve the active Forge workflow from `workflows/` or the configured ComfyUI adapter; do not hard-code old project paths.
- **Target Injection Node:** Typically Node 6 (CLIPTextEncode) for prompt text.
- **Resolution Standards:**
    - **Image Prompts:** 2048x2048
    - **Video Prompts:** 1280x720
- **Prompt Standard:** Positive prompt only, with physical material texture, camera/lens detail, named light source, and composition/focal priority. Avoid `masterpiece`, `best quality`, `8k`, and embedded negative blocks.

## Operational Workflow

### 1. Extraction & Sanitization
1. **Parse MD:** Extract the raw prompt text from the provided `.md` file. Ignore all Markdown headers (`#`, `##`), bolding, or metadata blocks (like `CINEMATIC_BLUEPRINT`).
2. **Enforce Banned Phrase Filter:** You MUST scan and remove any of the following forbidden artifact phrases:
    - `stygian shadows`
    - `polished vitrification`
    - `amberous luminosity`
    - `saffron-tinted radiance`
    - `eroded morphology`
    - `masterpiece`
    - `best quality`
    - `ultra-high-resolution`
    - `hyper-realistic`
3. **Character Integrity:** Ensure "Sienna" and "Aura" are present if the context requires character presence, ensuring they aren't replaced by generic descriptors.
4. **Anti-Smoothness Injection:** If the prompt is about people, include natural skin texture, slight facial asymmetry, flyaway hair, realistic under-eye shadows, and wardrobe fabric weave. If it is about products, include exact material finish, edge wear or fingerprints where appropriate, reflections, and scale cues.

### 2. JSON Payload Assembly
1. **Load Template:** Load the base workflow JSON.
2. **Deep Copy:** Create a deep copy of the dictionary to avoid mutating the template.
3. **Inject Prompt:** Locate the CLIPTextEncode node and replace its `text` value with the sanitized prompt.
4. **Apply Dimensions:**
    - If the source filename contains "Video", set the width/height nodes to `1280x720`.
    - Otherwise, set them to `2048x2048`.
5. **Save Output:** Save the resulting JSON in a dedicated directory: `{Source_Directory}/JSON_PAYLOADS/` using the pattern `[Original_Filename].json`.

### 3. Verification
1. Confirm all files are written with absolute paths.
2. List the contents of the output directory to ensure parity with the input count.

## Pitfalls & Troubleshooting
- **Incorrect Node Index:** If Node 6 does not contain text, use `search_files` or a python script to inspect the workflow JSON for any node with type `CLIPTextEncode`.
- **Relative Paths:** Never use relative paths in Python scripts; always resolve against `/Users/zgbot/Desktop/Sienna_Nomad_Project`.
- **Markdown Noise:** If prompts look "messy" in the JSON, refine the regex used for extraction to better handle blockquotes or lists.
