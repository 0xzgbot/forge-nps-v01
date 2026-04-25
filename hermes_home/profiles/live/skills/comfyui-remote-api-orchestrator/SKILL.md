---
name: comfyui-remote-api-orchestrator
version: "1.0"
category: mlops
description: Protocol for discovering, injecting, submitting, and monitoring ComfyUI jobs via Direct API on remote hosts.
---

# ComfyUI Remote API Orchestration Protocol

Use this protocol when you need to execute a workflow on a remote ComfyUI server (e.g., SPARK or Dual-3090) rather than locally.

## 1. Discovery Phase
Before submitting, verify the target environment and locate the workflow.
- **Find Workflow:** Use `find` via terminal to locate `.json` files if the path is unknown.
- **Verify Connectivity:** Always run a connectivity check (`curl -s --max-time 5 http://<IP>:<PORT>/object_info`) before attempting submission.

## 2. Injection Phase (Python)
Do not rely on shell commands for injection; use Python to ensure JSON integrity.
1. **Load:** `json.load(f)` the workflow.
2. **Locate Nodes:** Iterate through `workflow.items()` to find target nodes by `class_type` (e.g., `CLIPTextEncode`, `KSampler`, `SaveImage`).
3. **Modify:** Inject values into the `inputs` dictionary of the identified node ID.
4. **Payload Wrap:** Wrap the modified dict in: `{"prompt": workflow, "client_id": "<uuid>"}`.

## 3. Execution & Monitoring Phase
Submit via `curl` and implement a robust polling loop.

### Submission
```bash
curl -s -X POST http://<IP>:<PORT>/prompt \
  -H 'Content-Type: application/json' \
  -d @/tmp/payload.json
```
**Capture the `prompt_id` from the response immediately.**

### Polling Loop Logic
Implement a loop in Python to check `/history/{prompt_id}`. 
- **Poll Interval:** 5 seconds is standard for high-end GPUs.
- **Resilience:** If a network interruption occurs (e.g., Tailscale reset), **do not restart the job**. Instead, retry the `GET /history/{prompt_id}` request using the existing `prompt_id`. The job continues on the server regardless of client connectivity.

## 4. Retrieval Phase
Once history returns an `outputs` key:
1. Parse `node_id -> outputs -> images`.
2. Construct download URL: `http://<IP>:<PORT>/view?filename=<file>&subfolder=<folder>&type=<type>`.
3. Download using `curl -o <local_path>`.

## Pitfalls & Troubleshooting
- **Dimension Mismatch Errors:** Often caused by network drops during tensor communication or improper LoRA/Scheduler combinations in the JSON. If it happens, check if the server actually finished the task via `/history` first.
- **Tailscale Resets:** Always design monitoring scripts to be "idempotent" regarding the prompt ID—the ability to pick up where they left off.
- **Empty Outputs:** If history returns but `outputs` is empty, the workflow likely failed mid-execution. Check the `status` field in the history response for `exception_message`.
