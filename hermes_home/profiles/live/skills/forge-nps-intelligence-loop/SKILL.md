---
name: forge-nps-intelligence-loop
description: Protocol for the Forge NPS "Sense-Think-Act-Correct" autonomous filmmaking loop.
---

# Forge NPS Intelligence Loop Protocol

This skill defines the "Sense-Think-Act-Correct" closed-loop architecture for the Forge NPS filmmaking pipeline. It moves agents from passive dispatchers to active creative directors.

## Overview
The core objective is to transition from manual prompt engineering to an autonomous agentic loop where:
1. **Hermes-3 (Brain)** generates intent/prompts.
2. **Visual Agent (Muscles)** executes renders via ComfyUI.
3. **Kimi-VL (Eyes)** audits visual continuity against character anchors.
4. **Remediation Loop** uses Hermes to diagnose and rewrite prompts based on visual failures.

## The Intelligence Loop Workflow

### 1. Prompt Generation (Think)
- **Agent:** `HermesAgent` using `NousHermesBridge`.
- **Process:** Instead of simple string concatenation, the agent calls an LLM (via LM Studio/Local API) with a high-density system prompt: *"You are Hermes, an AI creative director specialized in visual storytelling..."*
- **Contextual Awareness:** The prompt must include the `director_schema` and `memory_context` (recent successful/failed shots).

### 2. Execution (Act)
- **Agent:** `VisualAgent`.
- **Process:** Converts the generated prompt into a technical ComfyUI JSON payload.
- **Communication:** Submits via POST to `/prompt` on the Spark server and polls the `/history/{prompt_id}` endpoint for completion.

### 3. Visual Auditing (Sense)
- **Agent:** `ContinuityAuditor` using `KimiBridge`.
- **Process:** Performs a dual-layer check:
    - **Layer 1 (Semantic):** Keyword/metadata check (Fallback).
    - **Layer 2 (Visual - KILLER FEATURE):** Uses Kimi-VL to compare the rendered PNG against character anchor images. It returns `is_consistent`, `confidence_score`, and a `mismatch_report`.

### 4. Automated Remediation (Correct)
- **Agent:** `RemediationLoop` $\rightarrow$ `HermesAgent`.
- **Process:**
    - If audit fails, the error is passed back to Hermes.
    - Hermes performs "Failure Analysis": *Why did this look wrong?* (e.g., "lighting mismatch").
    - Hermes generates a **corrected prompt** specifically addressing the visual discrepancy.
    - The loop restarts with the new directive.

## Implementation Details & Pitfalls

### File Structure Requirements
- `core/bridge/nous_hermes_bridge.py`: Wrapper for local LM Studio API.
- `core/bridge/kimi_bridge.py`: Wrapper for Kimi-VL multimodal API.
- `agents/visual/visual_agent.py`: ComfyUI API orchestration.
- `agents/auditor/continuity_auditor.py`: The decision logic for pass/fail.

### Common Pitfalls
- **Mocking vs. Reality:** Ensure agents are not just returning "mocked_success". Every step must involve a real tool call or API interaction to be demo-ready.
- **Indentation Errors in Automation:** When using `execute_code` to patch files, use robust string replacement or full rewrites rather than fragile line-number indexing to avoid Python IndentationErrors.
- **Async Deadlocks:** Ensure all bridge calls and polling loops are properly awaited within the `asyncio` event loop.

## Verification Steps
1. Run `python3 demo.py` (or equivalent test script).
2. Verify `[HERMES-3 🧠]` logs appear before rendering starts.
3. Verify `[KIMI-VL 👁]` logs appear after a render finishes.
4. Trigger an intentional failure (e.g., prompt for "incorrect color") and verify Hermes rewrites the prompt autonomously.
