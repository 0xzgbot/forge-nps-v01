---
name: comfyui-master-control
version: "2.0"
category: mlops
description: Master operational guide for the dual-server ComfyUI setup. Enforces a strict two-layer architecture of MCP Discovery and Direct API Execution.
---

# ComfyUI Master Control (v2.0)

## Architecture Standard: The Two-Layer Protocol

ComfyUI interaction is split into two non-overlapping layers. **Mixing these responsibilities is a system failure.**

```
┌─────────────────────────────────────────────────────┐
│  LAYER 1 — MCP (Discovery & Inspection)             │
│  Tools: list_workflows, read_workflow, list_models  │
│  Source: Local ~/workflows/ + remote /object_info/  │
│  USE ONLY FOR: Finding workflows and inspecting      │
│               node structures and model availability. │
└─────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────┐
│  LAYER 2 — Direct API (Execution)                   │
│  Endpoints: /prompt, /history/{id}, /view           │
│  USE ONLY FOR: Submitting jobs, polling status,     │
│               and downloading output files.         │
└─────────────────────────────────────────────────────┘
```

**⚠️ CRITICAL:** MCP tools cannot submit jobs or modify parameters. All generation tasks must be executed via Layer 2 HTTP calls to the remote server.

---

## Server Inventory (Dual RTX 3090 Setup)

Two independent ComfyUI instances running on a single Windows machine.

| Port | GPU Assignment | VRAM | Status/Capability |
|---|---|---|---|
| `100.74.164.1:8188` | RTX 3090 #0 (`--cuda-device 0`) | 24GB | Primary Image/Video |
| `100.74.164.1:8189` | RTX 3090 #1 (`--cuda-device 1`) | 24GB | Secondary/Batch |

**Probe Availability:**
Always verify server health before attempting a job.

```bash
curl -s --max-time 3 http://100.74.164.1:8188/api/system_stats
curl -s --max-time 3 http://100.74.164.1:8189/api/system_stats
```

**Launch Flags (Standard):**
`--normalvram --reserve-vram 2.0 --fast --fp16-vae --cache-none --use-sage-attention`

---

## Layer 1 — MCP Tools (Discovery)

The `comfyui-mcp` server manages the inspection layer.

### `list_workflows`
Lists all `.json` files in the local Mac directory `~/workflows/`.
*   **Returns:** `{workflow_root, count, workflows: [{name, relative_path...}]}`

### `read_workflow(relative_path)`
Loads a workflow JSON and provides the parsed structure.
*   **Returns:** `{relative_path, text, json}` 
*   **Note:** Use the `json` field for all subsequent injection logic.

### `list_models(kind, recursive, search)`
Queries the remote server's `/object_info/` to see what is actually loaded in VRAM.
*   **Kinds:** `checkpoints`, `loras`, `vae`, `clip`, `controlnet`

---

## Layer 2 — Direct API (Execution)

All active generation work occurs here via direct HTTP calls.

### Submit a Job
Submit the payload as a POST request. **Always use a temporary file for payloads to avoid shell argument limits.**

```bash
curl -s -X POST http://100.74.164.1:8188/prompt \
  -H "Content-Type: application/json" \
  -d @/tmp/payload.json
```
*   **Required Payload Format:** `{"prompt": {<workflow_dict>}, "client_id": "<uuid>"}`

### Monitor & Retrieve
1.  **Poll History:** `GET http://100.74.164.1:8188/history/{prompt_id}`
    *   Wait for the response to contain an `outputs` key for your target nodes.
2.  **Download Asset:** `GET http://100.74.164.1:8188/view?filename=...&subfolder=...&type=output`

---

## Standard Workflow Sequence

1.  **PROBE (L2):** Check `/api/system_stats` to pick an available host.
2.  **DISCOVER (L1):** Use `list_workflows` and `read_workflow` to get the target JSON structure.
3.  **INJECT (Local):** Deep copy the workflow, modify prompt/seed/resolution nodes in Python.
4.  **SUBMIT (L2):** POST the wrapped payload to `/prompt`. Capture `prompt_id`.
5.  **POLL (L2):** Periodically check `/history/{prompt_id}`.
6.  **DOWNLOAD (L2):** Use `/view` to save results locally.

---

## Model Inventory (Reference)

| Type | Key Models / Checkpoints |
|---|---|
| **Video** | `ltx-2.3-22b-dev-fp8`, `ltx-2.3-22b-distilled-fp8` |
| **Z-Image** | `z_image_bf16`, `z_image_turbo_bf16` |
| **LoRAs** | `Wan2.2 T2V`, `ltx-2.3-id-lora`, `Qwen-Edit-2509` |

---

## Related Skills

| Task | Skill |
|---|---|
| Submitting Jobs | `expert-image-submitter-agent` |
| Batch Orchestration | `comfyui-local-api-orchestration` |
| Video Injection | `comfyui-video-direct-injector` |
| Workflow Analysis | `comfyui-workflow-query-analysis` |
