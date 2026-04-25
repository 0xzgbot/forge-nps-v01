---
name: prompt-library-audit-and-rebuild
description: Automated workflow for auditing and mass-refining large-scale AI prompt libraries (JSON + Markdown) to ensure semantic character consistency and technical compliance.
---

# prompt-library-audit-and-rebuild

Automated workflow for auditing and mass-refining large-scale AI prompt libraries (JSON + Markdown) to ensure semantic character consistency and technical compliance.

## Trigger Conditions
- After a structural rebuild of a prompt library where content integrity is suspect.
- When "generic" terms (e.g., 'a woman', 'a dog') are detected in production prompts.
- Before initiating high-volume ComfyUI batch runs to ensure character/gear anchors are present.

## Workflow Steps

### 1. Audit Phase (Detection)
Use a recursive Python script to scan the library for:
- **Character Anchor Compliance**: Verify presence of specific names (e.g., 'Sienna', 'Aura') and unique physical descriptors (e.g., 'Golden-Rust hair', 'hazel eyes'). Flag any use of generic terms ('a person', 'the girl', etc.).
- **Technical Fidelity**: Confirm mandatory gear strings are present (e.g., 'Arri Alexa 65', 'Zeiss Master Prime').
- **File Integrity**: Ensure every `.json` payload has a corresponding, synchronized `.md` file with matching filenames.

### 2. Rebuild Phase (Correction)
If failures > 0, execute a mass rebuild using an automation engine:
- **Narrative Weaving**: Do NOT simply append tags to the end of prompts. The script must rewrite/re-synthesize the prompt text so anchors are integrated into the descriptive narrative flow.
- **Format Dual-Write**: For every update, write both the `.json` payload (for API injection) and the `.md` file (for human review), ensuring headers match filenames exactly.

### 3. Verification Phase (Validation)
Run a final pass of the audit script to ensure:
- Compliance Rate = 100%.
- Total JSON Count == Total MD Count.

## Pitfalls & Lessons Learned
- **The "Structure vs. Content" Trap**: A library can be structurally perfect (correct folders, filenames, and JSON syntax) while being semantically broken (missing character anchors). Always audit the *content* of the strings, not just the file metadata.
- **Appendage vs. Integration**: Appending tags like "Sienna, hazel eyes" to a prompt often results in lower-quality AI generations compared to weaving them into the prose (e.g., "Sienna, with her signature hazel eyes, gazes at...").

## Reference Scripts
- `audit_prompt_library_v7.py`: The high-precision audit engine.
- `rebuild_prompts_v2.py`: The automated narrative weaving and sync engine.