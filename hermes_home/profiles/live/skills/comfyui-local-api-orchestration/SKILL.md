---
name: comfyui-local-api-orchestration
description: Technical reference for the ComfyUI Direct API protocol. Covers all endpoints, payload formats, polling, retrieval, and batch orchestration for local ComfyUI instances. Use this as the execution layer alongside the MCP discovery layer.
---

# ComfyUI Direct API — Technical Reference

The direct API is the execution layer. MCP handles discovery; this handles everything else.

---

## Server Discovery

Always probe before use. Both ports are interchangeable — either may be up or down.

```bash
curl -s --max-time 3 http://localhost:8188/api/system_stats
curl -s --max-time 3 http://localhost:8189/api/system_stats
```

---

## Core Endpoints

### `GET /api/system_stats`
Server health + GPU info. ⚠️ Must use `/api/` prefix on ComfyUI 0.18.2+ — `/system_stats` returns nothing.
```json
{
  "system": {"os": "Linux", "python_version": "3.11", "pytorch_version": "2.x"},
  "devices": [{"name": "NVIDIA GeForce RTX 3090", "vram_total": 25769803776, "vram_free": 20000000000}]
}
```

### `GET /object_info/{NodeClass}`
Model catalog for a specific node type. Used by MCP's `list_models`.
```bash
curl -s http://localhost:8188/object_info/CheckpointLoaderSimple
```

### `POST /prompt`
Submit a generation job.

**Payload format:**
```json
{
  "prompt": { "<node_id>": { "class_type": "...", "inputs": {...} } },
  "client_id": "<uuid>"
}
```

**Always write to a temp file first:**
```bash
curl -s -X POST http://localhost:8188/prompt \
  -H "Content-Type: application/json" \
  -d @/tmp/comfy_payload.json
```

**Response:** `{"prompt_id": "abc-123-...", "number": 0}`

### `GET /history/{prompt_id}`
Poll job status and retrieve output metadata.

Complete when response contains `{prompt_id: {outputs: {...}}}`.

```python
import requests, time

def poll_until_done(host, prompt_id, interval=4, timeout=600):
    for _ in range(timeout // interval):
        r = requests.get(f"{host}/history/{prompt_id}").json()
        if prompt_id in r and r[prompt_id].get('outputs'):
            return r[prompt_id]['outputs']
        time.sleep(interval)
    raise TimeoutError(prompt_id)
```

### `GET /view`
Download a generated file.
```
GET /view?filename=<name>&subfolder=<subfolder>&type=output
```
Parse `filename`, `subfolder`, `type` from the `/history/` outputs object.

### `GET /queue`
Current queue state — running and pending jobs.

---

## Workflow JSON Formats

**Critical:** Two formats exist. Using the wrong one causes silent failures.

### API Format — submit this to `/prompt`
Flat dict, top-level keys are node ID strings:
```json
{
  "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "...", "clip": ["4", 1]}},
  "9": {"class_type": "KSampler", "inputs": {"seed": 42, "steps": 25, "cfg": 7.0, ...}}
}
```

### UI Save Format — exported from browser, NOT directly submittable
Nested structure, must parse to API format before submission:
```json
{
  "id": "workflow-uuid",
  "definitions": {
    "subgraphs": [{"nodes": [...], "links": [...]}]
  }
}
```

**To check format:** If top-level keys are numeric strings → API format. If top-level key is `"id"` or `"definitions"` → UI format.

---

## Node Injection Pattern

```python
import json, copy, uuid, random

# Load workflow (API format)
with open('/Users/zgbot/workflows/my_workflow.json') as f:
    base_workflow = json.load(f)

workflow = copy.deepcopy(base_workflow)

# Trace KSampler to find positive/negative nodes
for nid, node in workflow.items():
    if node['class_type'] in ('KSampler', 'KSamplerAdvanced'):
        pos_id = node['inputs']['positive'][0]
        neg_id = node['inputs']['negative'][0]
        node['inputs']['seed'] = random.randint(1, 999_999_999)
        break

workflow[pos_id]['inputs']['text'] = POSITIVE_PROMPT
workflow[neg_id]['inputs']['text'] = NEGATIVE_PROMPT

payload = {"prompt": workflow, "client_id": str(uuid.uuid4())}

with open('/tmp/payload.json', 'w') as f:
    json.dump(payload, f)
```

---

## Batch Orchestration

For processing multiple prompts across both servers:

```python
servers = [s for s in ['http://localhost:8188', 'http://localhost:8189']
           if is_up(s)]  # probe first

for i, prompt_text in enumerate(prompts):
    host = servers[i % len(servers)]  # round-robin
    # inject, submit, poll, retrieve...
```

---

## Pitfalls

| Problem | Cause | Fix |
|---|---|---|
| 404 on `/workflows` | ComfyUI has no file browser API endpoint | Use MCP `list_workflows` instead |
| Empty `{}` from `/history/` | Job not yet complete, or wrong prompt_id | Keep polling; verify prompt_id |
| "Unauthorized" from a node | Custom node calling external API (BFL etc.) | Switch to a workflow using standard nodes |
| JSON nested in `"prompt"` key | Some workflows wrap nodes under a `"prompt"` key | Check: `"prompt"` in payload vs `"prompt"` as a wrapper |
| Payload too large for shell args | Large workflows exceed shell arg limits | Always use `curl -d @file` pattern |
