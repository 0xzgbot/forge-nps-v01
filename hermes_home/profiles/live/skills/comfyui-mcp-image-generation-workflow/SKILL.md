---
name: comfyui-mcp-image-generation-workflow
category: mlops
description: Reference for the ComfyUI MCP layer — what it does, what tools it exposes, its limitations, and how it fits into the full generation pipeline. MCP handles discovery and inspection only; job submission goes through direct API.
---

# ComfyUI MCP Layer — Reference

## What the MCP Server Is

The `comfyui-mcp` server (Python package v0.1.0) runs as an MCP process on the Mac. It has two responsibilities:

1. **Serve workflow files** from the local `~/workflows/` directory as MCP resources and tools
2. **Query the remote ComfyUI server** for model catalog information

It is a **read-only discovery layer**. It cannot submit generation jobs, poll for completion, or retrieve outputs. Those operations go through direct API calls (see `comfyui-master-control`).

---

## Configuration

From `~/.hermes/config.yaml`:

```yaml
mcp_servers:
  comfyui-mcp:
    command: comfyui-mcp
    args:
      - --workflow-dir
      - ~/workflows
    env:
      COMFYUI_API_BASE_URL: http://localhost:8188/
      COMFYUI_HTTP_TIMEOUT: '300'
    timeout: 300
    connect_timeout: 60
```

**Note:** `COMFYUI_API_BASE_URL` only points to `:8188`. If that server is down, `list_models` will fail, but `list_workflows` and `read_workflow` still work because they operate on local files only.

---

## Available Tools

### `list_workflows(include_preview: bool = False)`

Lists all `.json` files under `~/workflows/` recursively.

**Returns:**
```json
{
  "workflow_root": "/Users/zgbot/workflows",
  "count": 12,
  "workflows": [
    {
      "name": "image_flux2_text_to_image",
      "relative_path": "image_flux2_text_to_image.json",
      "size_bytes": 4821,
      "modified": "2026-04-12T02:14:00+00:00"
    }
  ]
}
```

Set `include_preview: true` to also get the raw JSON content of each file inline.

**Reliability:** Always works. No server connection needed.

---

### `read_workflow(relative_path: str)`

Reads a specific workflow file by its path relative to `~/workflows/`.

**Example:** `read_workflow("image_flux2_text_to_image.json")`

**Returns:**
```json
{
  "relative_path": "image_flux2_text_to_image.json",
  "text": "{...raw json string...}",
  "json": { ...parsed workflow object... }
}
```

Use the `json` field directly — it's already parsed.

**Reliability:** Always works for files that exist. No server connection needed.

**⚠️ Symlink Trap:** The MCP server resolves symlinks and checks that the resolved path starts with the workflow root. If a file is a symlink pointing outside `~/workflows/`, the server throws:
```
Attempted to read workflow outside of the configured directory
```
**Fix:** Use a hard copy instead of a symlink: `cp /source/file.json ~/workflows/file.json`

---

### `list_models(kind, recursive, search)`

Queries the remote ComfyUI server's `/object_info/{NodeClass}` endpoint to enumerate loaded models.

**Supported kinds:** `checkpoints`, `loras`, `vae`, `clip`, `controlnet`

**Example calls:**
- `list_models()` — all kinds, summary
- `list_models(kind="checkpoints")` — flat list of checkpoint filenames
- `list_models(recursive=True)` — all kinds aggregated
- `list_models(kind="checkpoints", search="ltx")` — filtered

**Returns (summary mode):**
```json
{
  "base_url": "http://localhost:8188",
  "kinds": ["checkpoints", "loras", "vae", "clip", "controlnet"],
  "counts": {"checkpoints": 7, "loras": 3, ...},
  "models": {
    "checkpoints": ["flux2-dev-fp8mixed.safetensors", "ltx-2.3-22b-dev-fp8.safetensors", ...],
    "loras": [...]
  }
}
```

**Reliability:** Requires `:8188` to be running. Fails gracefully (returns empty list with error key) if server is down.

---

## What MCP Does NOT Do

These operations do **not** exist in the MCP server. Do not attempt to call them:

| Non-existent tool | What to use instead |
|---|---|
| `get_prompt()` | Does not exist. Read the workflow with `read_workflow`, modify it in Python, submit via `POST /prompt` |
| `queue_workflow()` | Does not exist. Use `curl POST /prompt` |
| `generate()` | Does not exist. Use direct API |
| `get_status()` | Does not exist. Use `GET /history/{id}` |

The "Unknown prompt" errors in Hermes session history were caused by calling `get_prompt()` — a tool that was never part of this MCP server.

---

## MCP Resources

In addition to tools, the MCP server registers each workflow file as a resource with URI format:

```
workflow://local/image_flux2_text_to_image.json
```

These can be read via MCP resource access, but `read_workflow` is simpler and returns parsed JSON.

---

## Full Generation Pattern

```
list_workflows          → find the right workflow file
read_workflow           → load its JSON
[modify JSON in Python] → inject prompt, seed, dimensions
[probe /api/system_stats] → confirm target server is up
[POST /prompt]          → submit job, get prompt_id
[GET /history/{id}]     → poll until outputs appear
[GET /view?filename=..] → download result
```

See `comfyui-master-control` for the complete implementation pattern.
