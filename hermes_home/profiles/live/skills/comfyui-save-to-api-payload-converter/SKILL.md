---
name: comfyui-save-to-api-payload-converter
description: Converts ComfyUI "Save" JSON to "API" payload format.
---
# SKILL: comfyui-save-to-api-payload-converter

## DESCRIPTION
A specialized conversion logic used to transform a ComfyUI "Save" (Workflow) JSON format into the "API" JSON format required for direct HTTP POST injections.

## TRIGGER
Use when converting .json workflows exported from ComfyUI (which use a 'nodes' list) to payloads for the Direct API (which requires a 'prompt' dictionary).

## THE CORE LOGIC

⚠️ **Two variants of the UI Save format exist.** This skill handles the **legacy** nodes-list format (older ComfyUI exports). The newer ComfyUI 0.18.x UI export format uses `{"definitions": {"subgraphs": [{"nodes": [...]}]}}` — see `comfyui-workflow-query-analysis` for that parser.

1. **Structure Difference (Legacy Save Format):**
   - **Legacy Save Format:** `{"nodes": [{"id": 1, "inputs": [...], ...}]}`
   - **API Format:** `{"prompt": {"1": {"inputs": {"text": "..."}, ...}}}`
2. **Implementation Strategy:**
   - Iterate through the 'nodes' list from the 'Save' file.
   - Reconstruct a new dictionary where keys are stringified node IDs.
   - **CRITICAL:** The `inputs` field in the 'Save' format is a **list** (representing widget values), but the API requires a **dictionary**. 
   - When targeting a text node, replace the entire `inputs` list with the dictionary `{"text": "prompt_text"}`.

## PITFALLS
- **Input Type Mismatch:** In the "Save" format, `inputs` is a `list`. Attempting `node['inputs']['text']` will throw a `TypeError`.
- **Node ID Types:** Always cast node IDs to strings when building the `prompt` dictionary to ensure compatibility with the API.

## VERIFICATION
- Output JSON must have a top-level `"prompt"` key.
- The target node's `inputs` must be a dictionary in the output.
