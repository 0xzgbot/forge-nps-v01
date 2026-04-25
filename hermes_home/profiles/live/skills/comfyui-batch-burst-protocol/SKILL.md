---
name: comfyui-batch-burst-protocol
version: "1.0"
category: mlops
description: A resilient protocol for executing large batches of ComfyUI jobs on remote servers when standard long-running background processes are terminated by system watchdogs (SIGTERM/Exit Code -15).
---

# ComfyUI Batch-Burst Protocol

Use this protocol when a single, continuous background process for multi-hundred image generations is being killed by the host OS or container manager.

## 1. Core Philosophy: "Micro-Orchestration"
Instead of one monolithic loop, decompose the workload into discrete, short-lived "bursts." This prevents the process from reaching the timeout/resource threshold that triggers a SIGTERM.

## 2. Execution Workflow

### Phase A: State Initialization
Before starting, create a `re_render_state.json` file in the project root to ensure idempotency.
- **Structure:**
  ```json
  {
    "/path/to/prompt_1.txt": {"status": "pending", "subfolder": "EP01", "filename": "prompt_1.txt"},
    ...
  }
  ```
- **Purpose:** Allows the agent to skip already completed tasks if a burst is interrupted.

### Phase B: The Burst Cycle (The "Burst" Agent)
Execute the following in a single, controlled session:
1. **Load State:** Read `re_render_state.json`.
2. **Filter:** Select the next $N$ items (e.g., $N=15$) where `status == "pending"`.
3. **Inject & Submit:** 
   - Load the ComfyUI JSON template.
   - Inject text into the target conditioning node (e.g., `98:6`).
   - POST to `/prompt` and capture `prompt_id`.
4. **Monitor (Polling):**
   - Poll `/history/{prompt_id}` every 5-10 seconds.
   - **Do not exit the loop until all $N$ jobs in the current batch are complete or failed.**
5. **Retrieve & Store:**
   - Once a job is done, use `/view` to download assets.
   - Save to `[OUTPUT_DIR]/[subfolder]/[original_filename]`.
6. **Update State:** Mark each processed item as `completed` in the JSON file.

### Phase C: Reporting
At the end of every burst, provide a summary:
- Total completed in this burst.
- Current global progress (e.g., 45/261).
- Status of the next batch.

## 3. Troubleshooting SIGTERM (-15)
If the agent receives a `-15` error:
- **Do not attempt to restart the full loop.**
- **Verify state:** Check `re_render_state.json` to see exactly where it died.
- **Reduce Burst Size:** If -15 recurs, reduce $N$ (the batch size) from 15 to 5 or 1.
- **Increase Polling Interval:** Slow down the frequency of API calls if hitting rate limits/timeouts.

## 4. Implementation Note for Hermes
When delegating this task, instruct the sub-agent to act as a "Burst Orchestrator" rather than a "Background Worker." Use `execute_code` for the burst itself to maintain direct control over the execution lifecycle.
