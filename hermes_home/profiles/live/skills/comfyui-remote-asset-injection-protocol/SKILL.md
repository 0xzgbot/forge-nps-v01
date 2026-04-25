---
name: comfyui-remote-asset-injection-protocol
description: Specialized workflow for executing I2V batches on remote ComfyUI servers when anchor images reside in the wrong directory (output/ instead of input/).
---

# ComfyUI Remote Asset Injection Protocol

## Trigger Conditions
- Large batch I2V jobs are pending.
- Assets (anchor frames) have been generated but reside in the remote `~/ComfyUI/output/` folder.
- The user has moved files to `~/ComfyUI/input/` via SSH.

## Execution Steps

1. **Map Assets to Prompts**: Identify deterministic relationships between filenames and motion prompts (e.g., from a prompt library).
2. **Load Workflow Template**: Use a flattened ComfyUI API JSON template compatible with the remote server's node structure.
3. **Prepare Payloads**: 
    - Iterate through mapping.
    - Create deep copies of the workflow template for each shot.
    - Inject the filename into the `LoadImage` node (verify Node ID first).
    - Inject the motion prompt into the text/conditioning node (verify Node ID first).
4. **Batch Submission**: Submit payloads via HTTP POST to the remote `/prompt` endpoint.
5. **Verify Execution**: Log all returned `prompt_id`s for tracking and retrieval.

## Pitfalls & Troubleshooting
- **Path Mismatch**: If submissions fail with 400 errors, verify filenames match exactly what is in the remote `input/` folder.
- **Node ID Drift**: Different workflows use different IDs for `LoadImage`. Always check the template JSON before running injection scripts.
