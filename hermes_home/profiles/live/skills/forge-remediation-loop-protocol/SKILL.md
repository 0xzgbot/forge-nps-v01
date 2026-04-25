---
name: forge-remediation-loop-protocol
description: Protocol for integrating automated quality auditing (J9) with autonomous remediation loops (J8).
---

# J8/J9 Closed-Loop Remediation Protocol

This skill defines the operational protocol for integrating automated quality auditing (J9) with autonomous remediation loops (J8) in the Forge system. It ensures that generation errors are not just detected, but systematically resolved through a multi-tier escalation architecture.

## Overview
The goal is to create an "Error Loop" where a failed asset triggers a reasoning step rather than manual human intervention, minimizing production friction.

## The 3-Tier Escalation Architecture (J8)

When the **Continuity Auditor (J9)** returns `is_consistent: False`, the **Remediation Loop (J8)** executes the following hierarchy:

### Tier 1: Skill Registry Lookup
*   **Trigger:** Semantic or Photometric error detected.
*   **Action:** Search the local `SkillRegistry` for known fixes related to the `error_category`.
*   **Goal:** Rapid, low-compute resolution using pre-defined templates.

### Tier 2: Kimi Reasoning (LLM Intervention)
*   **Trigger:** Tier 1 fails or confidence is too low.
*   **Action:** Dispatch the `mismatch_report` and original prompt to the **Kimi Bridge**. 
*   **Logic:** Kimi performs root-cause analysis and returns a `fix_prompt`.
*   **Goal:** High-intelligence reasoning for complex, novel errors.

### Tier 3: Direct Prompt Rewrite / Human Review
*   **Trigger:** Kimi fails or the error persists after Tier 2 regeneration.
*   **Action:** Flag asset for `needs_human_review` and provide a detailed report.

## Integration Schema (J9 $\rightarrow$ J8)

The Auditor (J9) **MUST** return the following JSON structure to trigger the loop:

```json
{
  "is_consistent": boolean,
  "confidence_score": float,
  "error_category": "Photometric | Anatomical | Temporal | Semantic",
  "mismatch_report": "String describing the specific lore/visual contradiction",
  "remediation_prompt": "Optional: A pre-computed fix if Tier 1 is successful"
}
```

## Implementation Verification (Testing Workflow)
To validate a new remediation logic, run an integration test following this flow:
1.  **Inject Failure:** Define a `bad_asset` (e.g., prompt contradicts lore).
2.  **Audit:** Call `auditor.audit_asset()`. Verify it returns `is_consistent: False`.
3.  **Remediate:** Pass the report to `remediation_engine.remediate()`.
4.  **Verify Loop:** Ensure the engine calls `hermes.dispatch_shots()` with a corrected prompt and that the *second* audit passes.

## Pitfalls & Lessons Learned
*   **Dependency Stability:** The remediation loop is highly dependent on the stability of the `core/bridge` (KimiBridge, ConfigManager). If the bridge is broken, Tier 2 will fail. Always stabilize the configuration layer before testing reasoning tiers.
*   **Infinite Loops:** Always implement a `max_iterations` constraint in the `RemediationLoop` to prevent the system from endlessly regenerating failing assets.
