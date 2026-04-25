---
name: brand-consistency-protocol
description: Enforces strict brand guidelines for all generated assets (images, videos, text) to ensure commercial-grade consistency across any niche or theme.
model: gemma-4-26b
category: marketing-system
---

# Brand Consistency Protocol (Universal)

This protocol ensures that every asset produced by the AI team—regardless of whether it is for a food brand, a tech influencer, or a cinematic series—adheres to a unified visual and tonal identity.

## 1. Identity Definition Phase
Before any generation begins, the following "Brand DNA" must be established:
- **Visual Signature:** Color palette (HEX/RGB), lighting style (e.g., high-key, moody, cinematic), lens language (e.g., macro, wide-angle), and texture/grain.
- **Tonal Voice:** The linguistic personality (e.g., authoritative, playful, minimalist, chaotic).
- **Compositional Rules:** Standard framing (e.g., rule of thirds, centered symmetry) and depth of field preferences.

## 2. Asset-Specific Enforcement

### A. Image Generation (Flux/SDXL)
- **Prompt Injection:** Automatically append the "Visual Signature" to all image prompts.
- **Consistency Check:** Verify that lighting and color grading match the established Brand DNA.

### B. Video Generation (LTX 2.5 / Manim)
- **Cinematic Language:** Enforce consistent camera movement (e.g., slow pans, dolly zooms) as defined in the brand profile.
- **Motion Style:** Ensure temporal consistency (the "feel" of motion) matches the brand's energy level.

### C. Copywriting (Textual Assets)
- **Vocabulary Control:** Use a curated list of "Power Words" and avoid "Forbidden Words" that break character.
- **Formatting:** Enforce platform-native formatting (e.g., X threads vs. Instagram captions).

## 3. Quality Assurance Loop
Every asset must pass through the `quality-assurance-iteration-agent` using these criteria:
1. Does it match the Color Palette?
2. Is the Tonal Voice correct?
3. Does the composition follow the Brand Rules?

## Pitfalls to Avoid
- **Niche Drift:** Allowing a single asset to adopt a style that contradicts the core brand identity.
- **Prompt Dilution:** Adding too many conflicting descriptors that wash out the specific brand signature.
