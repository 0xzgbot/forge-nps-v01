---
name: forge-live-production-test-protocol
description: A high-precision protocol for verifying and executing the first live production run of the Forge MediaEngine on remote hardware (e.g., Spark). This moves the system from simulation to real GPU compute using the '--live' flag and direct API submission.
---

# Forge Live Production Test Protocol (FLPTP)

## Overview
This protocol is used when transitioning from a local/simulated environment to live production hardware. It ensures that connectivity is stable, workflows are valid for the remote host, and the "Architect $\rightarrow$ Dispatcher" pipeline is functioning before committing to large-scale batches.

## Trigger Conditions
- Initial setup of new production hardware (e.g., Spark integration).
- After resolving network/connectivity issues with a remote ComfyUI host.
- Prior to executing large-scale batch productions on live GPUs.

## Workflow Steps

### 1. Connectivity & API Validation
Before attempting execution, verify that the target IP and port are reachable and responding to API calls.
- **Command**: Use a Python script to perform a socket connection check and an `/object_info` request.
- **Success Criteria**: Socket connection is successful AND the `/object_info` endpoint returns a valid JSON object containing node types (e.g., `KSampler`, `CLIPTextEncode`).

### 2. Single-Unit Live Test (The "Pilot" Run)
Never run a full batch immediately after connectivity restoration. Execute a single-item test to verify the entire payload pipeline.
- **Action**: Use the `demo.py` or a custom execution script with the `--live` flag.
- **Payload Injection**: The agent must programmatically inject a high-quality test prompt into the correct node (typically the `CLIPTextEncode` node) within the selected workflow JSON to ensure the "Architect" logic is working.
- **Target Workflow**: Select an existing, tested workflow (e.g., `hermes_z_image_turbo_api`).

### 3. Polling & Verification
Monitor the job status via the `/history/{prompt_id}` endpoint.
- **Polling Loop**: Implement a loop with exponential backoff or fixed intervals (e.g., 5 seconds) to check for completion.
- **Success Criteria**: The API returns a history object containing the `prompt_id` and an `outputs` key specifying the generated filename (e.g., `hermes_z_image_turbo_00001_.png`).

## Pitfalls & Constraints
- **Simulation Mode**: Always verify the `--live` flag is present. Running without it will yield "successful" results in simulation mode, providing no insight into actual hardware performance or connectivity.
- **Node ID Drift**: When injecting prompts programmatically, do not hardcode Node IDs (e.g., `workflow["prompt"]["6"]`). Instead, search the JSON for the class type `CLIPTextEncode` to ensure compatibility with workflow updates.
- **Network Latency/Timeouts**: Remote hosts (like Spark) may have higher latency than localhost. Ensure API timeouts are set to at least 5-10 seconds and polling is robust against 404 errors (which occur while the job is in flight).

## Verification Checklist
- [ ] Connectivity check passes (Socket + `/object_info`).
- [ ] Single-unit test completes via `--live` flag.
- [ ] Asset filename is correctly reported in the API history.
