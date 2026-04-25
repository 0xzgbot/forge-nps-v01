---
name: comfyui-workflow-query-analysis
version: "1.0"
description: Query remote ComfyUI servers and analyze workflow files using direct API access and local parsing.
---
# ComfyUI Workflow Query & Analysis (Direct API Edition)

A comprehensive guide for querying remote ComfyUI servers and analyzing workflow files locally.

## System Stats API

### Get Server Information
```bash
curl http://localhost:8188/api/system_stats | python3 -m json.tool
curl http://localhost:8189/api/system_stats | python3 -m json.tool
```

⚠️ Must use `/api/system_stats` — not `/system_stats` (returns nothing on ComfyUI 0.18.2+).

**Response includes:**
- OS (`win32`), Python version, PyTorch version
- GPU device info (name, VRAM total/free)

---

## Workflow File Formats — CRITICAL DISTINCTION

ComfyUI has **two different JSON formats**. Using the wrong parser for the wrong format is a common failure.

### Format 1: API Prompt Format (used for submission via `/prompt`)
Flat dictionary keyed by node ID string. This is what you inject into and POST.
```json
{
  "6": { "class_type": "CLIPTextEncode", "inputs": { "text": "...", "clip": ["4", 1] } },
  "8": { "class_type": "EmptyLatentImage", "inputs": { "width": 1024, "height": 1024 } }
}
```

### Format 2: UI Save Format (exported from ComfyUI browser interface)
Nested structure with a `nodes` array and a `definitions.subgraphs` wrapper (used in newer ComfyUI versions) or a top-level `nodes` array (older versions). **Cannot be submitted directly to `/prompt` — must be converted to Format 1 first.**

```json
{
  "id": "workflow-id",
  "definitions": {
    "subgraphs": [
      { "nodes": [...], "links": [...] }
    ]
  }
}
```

**Rule:** Workflows in `~/ComfyUI/workflows/` saved from the UI are Format 2. Workflows used for API injection must be Format 1. When in doubt, check whether the top-level keys are numeric strings — if yes, it's Format 1.

### Python Parser for UI Format (Format 2)
```python
import json
from pathlib import Path

def analyze_workflow(wf_file):
    with open(wf_file) as f:
        d = json.loads(f.read())
    
    # Get nodes from subgraphs (not flat 'nodes' field)
    defs = d.get('definitions', {})
    subgraphs = defs.get('subgraphs', [])
    all_nodes = []
    
    for sg in subgraphs:
        if isinstance(sg, dict):
            nodes_list = sg.get('nodes', [])
            if isinstance(nodes_list, list):
                all_nodes.extend(nodes_list)
    
    node_types = [n.get('class_type', 'unknown') for n in all_nodes]
    return len(all_nodes), node_types
```

### Python Parser for API Format (Format 1)
```python
def analyze_api_workflow(wf_file):
    with open(wf_file) as f:
        d = json.load(f)
    for node_id, node in d.items():
        print(f"Node {node_id}: {node.get('class_type')} — inputs: {list(node.get('inputs', {}).keys())}")
```

---

## Troubleshooting Tips

### Empty Subgraphs (0 nodes)
Some workflows may have empty subgraphs - these are typically:
- Template files awaiting configuration
- Incomplete imports

**Check:** Verify the workflow was fully saved by opening in ComfyUI and re-exporting.

### MCP Layer
For listing and reading workflow files, use the MCP layer (`list_workflows`, `read_workflow`) — those tools read local `~/workflows/` files without needing the server up. This skill handles the analysis and direct API query layer. See `comfyui-master-control` for the full two-layer architecture.

---

## Verification Checklist
- [ ] Server responds to `/api/system_stats`
- [ ] Workflow files parse without errors
- [ ] Node count matches visual inspection in ComfyUI
- [ ] Subgraph structure is properly nested