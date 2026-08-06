---
name: kimi-vl-integration-protocol
description: Standardized workflow for implementing and utilizing Kimi-VL multi-modal reasoning capabilities.
---

# Kimi-VL Multi-Modal Integration Protocol

This skill provides the standardized workflow for implementing and utilizing multi-modal (visual) reasoning capabilities via the Kimi-VL client within the Cinesmith intelligence stack.

## Overview
The `KimiVLClient` is a specialized extension of the `KimiBridge`. It is designed to handle visual assets (images/video frames) by encoding them into Base64 and injecting them into an OpenAI-compatible multi-modal message payload. This enables high-precision visual audits, consistency checks, and cinematic quality verification.

## Implementation Architecture
1.  **Class Structure**: `KimiVLClient(KimiBridge)`
2.  **Primary Method**: `analyze_visuals(image_path, system_prompt, user_prompt, schema, ...)`
3.  **Routing Logic**: Automatically forces the `ModelTier.VISUAL` tier via the `KimiModelRouter`.
4.  **Parameter Optimization**: Uses a hardcoded low temperature ($0.1$) to minimize hallucination and maximize precision during visual audits.

## Standard Workflow: Visual Auditing
When an agent (e.g., QA Agent) needs to perform a visual check:

1.  **Initialization**: Ensure the `kimi_bridge` provided to the agent is an instance of `KimiVLClient`.
2.  **Schema Definition**: Define a Pydantic model (e.g., `QAAuditSchema`) to enforce structured JSON output. 
    *   *Note: Avoid using reserved Python keywords like `pass` in schema fields; use `pass_flag` instead.*
3.  **Execution**: Call `analyze_visuals` with the absolute path to the asset and the specific audit prompts.
4.  **Remediation**: If validation fails, the client automatically triggers the `_handle_visual_remediation` loop, which extracts context from the failed payload and sends a text-only correction request.

## Pitfalls & Best Practices
- **Keyword Collision**: Never name a Pydantic field `pass`. It will break the model's ability to instantiate the object. Use `pass_flag`, `is_passed`, etc.
- **Path Integrity**: Always use absolute paths for images to prevent file system errors in distributed agent environments.
- **Temperature Control**: Do not increase temperature for visual tasks; precision is more critical than creativity during the audit phase.
- **Remediation Scope**: The remediation loop is text-based. It fixes JSON structure and logic based on the *description* of the failure, rather than re-sending the image in a recursive loop (which could be cost/token prohibitive).

## Error Handling
- `FileNotFoundError`: Raised if the `image_path` does not exist.
- `TypeError`: Raised by the QA Agent if it attempts a visual audit using a standard `KimiBridge` instead of `KimiVLClient`.
- `ValidationError`: Handled internally via `StrictSchemaGuard` and the remediation engine.
