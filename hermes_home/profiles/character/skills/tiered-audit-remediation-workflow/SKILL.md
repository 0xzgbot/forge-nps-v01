---
name: tiered-audit-remediation-workflow
description: A specialized workflow for implementing agentic "closed-loop" remediation where a visual failure (detected by a Vision LLM) triggers a creative rewrite (by a reasoning LLM).
---

# Skill: Tiered Audit Remediation Workflow

## Description
A specialized workflow for implementing agentic "closed-loop" remediation where a visual failure (detected by a Vision LLM) triggers a creative rewrite (by a reasoning LLM).

## Trigger Conditions
- When transitioning from text-only semantic consistency checks to multimodal (image + text) auditing.
- During the development of "Agent-in-the-loop" systems for generative media pipelines.

## Implementation Protocol

### 1. The Multimodal Audit (The Eyes)
Implement a `bridge` method that accepts:
- `target_image`: The generated asset.
- `reference_images`: Anchors/characters to ensure consistency.
- `prompt_context`: The original intent.

The output must be structured JSON containing: `is_consistent`, `confidence`, `issues` (list), and `error_category`.

### 2. The Semantic Fallback (The Safety Net)
Always maintain a text-only semantic audit as a fallback. If the Vision model fails or is unavailable, the system should still check if the prompt's *description* contradicts the Lore Bible using standard LLM reasoning.

### 3. The Creative Remediation (The Brain)
When an audit fails:
- **Tier 1 (Visual Failure):** Pass the `issues` from the Vision model + the original prompt to a high-reasoning LLM (e.g., Hermes-3).
- **Prompt Instruction:** "Analyze this visual mismatch and rewrite the prompt to explicitly fix it while maintaining cinematic style."
- **Tier 2 (Semantic/Logic Failure):** Use standard text-based remediation if no image is present.

### 4. The Feedback Loop
Integrate the `remediation_prompt` back into the `VisualAgent` or `Orchestrator` to re-trigger the generation cycle.

## Pitfalls & Lessons Learned
- **Latency:** Visual audits are slow. For demos, ensure models are "warm" and use fast inference endpoints.
- **Schema Drift:** Ensure the Auditor's output schema matches exactly what the Remediation Engine expects (e.g., `error_category` must be a consistent Enum).
- **False Positives:** Vision models can be overly sensitive to lighting/shadows; weight `confidence` heavily in decision logic.
