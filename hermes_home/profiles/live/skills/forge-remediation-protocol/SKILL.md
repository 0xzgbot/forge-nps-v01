---
name: forge-remediation-protocol
description: Protocol for performing targeted remediation of Forge pipeline failures identified during specialist audits.
---

# Forge Remediation Protocol

## Trigger Condition
Use when an independent audit or verification step (e.g., Specialist Agent) identifies critical logical failures, non-compliance with the Build Plan, or hardcoded/unstable logic in newly implemented pipeline scripts.

## Procedure
1. **Identify Discrepancies**: Map findings from the auditor to specific requirements in `FORGE_BUILD_PLAN.md`.
2. **Categorize Failures**:
   - **Compliance Failure**: Using banned terms (e.g., "Flux 2") or incorrect constants.
   - **Logic Failure**: Hardcoded placeholders instead of metadata extraction, or broken regex/parsing logic.
   - **Pathing Failure**: Use of hardcoded absolute paths that reduce project portability.
3. **Execute Targeted Patches**:
   - For compliance: Use `patch` to scrub and replace terms with mandated alternatives.
   - For logic: Rewrite the file using a more robust, metadata-driven approach (e.g., filename regex parsing).
   - For constants: Update files to match the exact string requirements of the Build Plan.
4. **Verify**: Re-run the specific verification checklist for that Chunk to ensure the fix is successful.

## Pitfalls
- Do not attempt a "blanket" rewrite of the entire project; only patch the identified failed components to maintain stability in previously verified chunks.
- Ensure any rewritten script (like `caption_images.py`) accounts for the naming convention established by previous scripts (like `generate_training_images.py`).