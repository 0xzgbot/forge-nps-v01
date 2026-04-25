---
name: forge-visual-audit-protocol
description: End-to-end workflow for implementing high-precision visual continuity auditing using KimiVL and canvas frame capture.
---

# Skill: Forge Visual Audit (KimiVL Integration)

## Overview
This skill outlines the end-to-end workflow for implementing high-precision visual continuity auditing within the Forge NPS architecture. It combines canvas-based client-side frame capture with KimiVL's multimodal analysis to validate video/image renders against character "Lore Bible" DNA.

## Trigger Conditions
- When extending the Forge NPS dashboard to include video playback capabilities.
- When adding automated semantic quality assurance for visual assets.

## Implementation Protocol

### 1. Backend: Multimodal Auditor (`kimi_vl_client.py`)
Implement an `audit_frame()` method in the `KimiVLClient` class.
- **Input**: Base64 image, shot metadata (ID, expected description), and Lore Bible excerpt.
- **Prompting Strategy**: Use a persona-based system prompt ("You are a Visual Continuity Auditor...") to force comparison between provided visual data and text-based character DNA.
- **Output Structure**: Must return a JSON object containing:
  - `is_consistent` (bool)
  - `confidence_score` (float 0-1)
  - `mismatch_details` (str, optional)
  - `suggested_fix` (str, optional)

### 2. Backend: API Integration (`forge_dashboard.py`)
Create a POST endpoint `/api/visual-audit`.
- **Pydantic Models**: Define strict schemas for the incoming frame and metadata to ensure robust validation.
- **Episodic Memory**: Log every audit result (pass/fail) into the `EpisodicMemory` system to allow the agent to learn from recurring visual errors.

### 3. Frontend: Frame Capture Engine (`video-player.js`)
Implement a dedicated `ForgeVideoPlayer` class to manage the lifecycle of video playback and auditing.
- **Canvas Interception**: Use an offscreen `<canvas>` element.
- **Capture Logic**:
  1. Get current timestamp from `<video>`.
  2. `ctx.drawImage(video, 0, 0)` onto the canvas.
  3. `canvas.toDataURL('image/jpeg', 0.9)` to generate a high-quality JPEG base64 string.
- **State Management**: Handle loading states and "Analyzing..." UI feedback during API calls.

### 4. Frontend: Dashboard Integration (`app.js`)
Modify the rendering loop to differentiate between image and video assets.
- **Asset Detection**: Use regex (e.g., `/\.(mp4|webm|mov)$/i`) on file paths.
- **Factory Pattern**: Replace standard thumb generators with a `createRenderCard()` function that returns different HTML structures based on asset type.
- **Lightbox Architecture**: Implement `openVideoLightbox()` to inject the `ForgeVideoPlayer` into a modal overlay, providing a focused environment for analysis.

## Pitfalls & Solutions
- **Memory Leaks**: Always ensure the lightbox and player instance are properly cleaned up/removed from the DOM when closing.
- **Base64 Overhead**: Large 4K frames can bloat JSON payloads; use `image/jpeg` with quality compression (0.8-0.9) to balance detail vs. network latency.
- **Context Loss**: When passing lore to KimiVL, ensure the excerpt is highly relevant to the specific character being audited to prevent "hallucinated" inconsistencies.

## Verification Steps
1. Load a video render in the dashboard.
2. Trigger `openVideoLightbox`.
3. Click "Analyze Frame".
4. Verify:
   - The loading spinner appears.
   - The KimiVL response correctly identifies character traits (e.g., eye color, clothing).
   - The verdict badge (Cyan/Magenta/Amber) matches the consistency score.
