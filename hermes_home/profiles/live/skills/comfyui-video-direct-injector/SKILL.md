---
name: comfyui-video-direct-injector
version: "1.0"
description: High-precision video generation injector for standard ComfyUI JSON files (unwrapped format). Handles wrapping the JSON into the 'prompt' payload and targeting text nodes for Wan 2.2 or LTX 2.3 video workflows.
---
# ComfyUI Video Direct Injecter

A specialized execution skill for injecting prompts into standard (unwrapped) ComfyUI workflow files for video generation (Wan 2.2, LTX 2.3).

## Workflow Logic

⚠️ **Always check wrapping status before submitting.** The hermes workflow files (`hermes_flux2_api.json`, `hermes_z_image_turbo_api.json`) are **already pre-wrapped** in `{"prompt": {...}}`. External or downloaded video workflows may be raw.

```python
raw = json.load(f)
# Detect pre-wrapped
if "prompt" in raw and isinstance(raw["prompt"], dict):
    workflow = raw["prompt"]  # unwrap to flat node dict
else:
    workflow = raw  # already flat
```

Then after injection, always wrap for submission:
```python
payload = {"prompt": workflow, "client_id": str(uuid.uuid4())}
```

Pipeline:
1. Load JSON and unwrap if pre-wrapped (see above).
2. Locate the text input node via `class_type` tracing (never hardcode IDs).
3. Inject the prompt.
4. Wrap in `{"prompt": ..., "client_id": ...}` and write to `/tmp/payload.json`.
5. Execute via `curl -d @/tmp/payload.json` to the ComfyUI endpoint.

## Operational Steps
1. **Identify Workflow Path:** Locate the `.json` file.
2. **Inject via Python:** Use `execute_code` to perform the wrapping and injection logic.
3. **Submit via Terminal:** Send the payload to `http://<IP>:<PORT>/prompt`.

## Pitfalls & Troubleshooting

### Identifying Positive vs Negative CLIPTextEncode
Video workflows (LTX 2.3, Wan 2.2) always have at least two `CLIPTextEncode` nodes — one positive, one negative. To identify which is which, trace the node's output connection in the workflow JSON:

```python
# In API Format (Format 1): find which KSampler/conditioning input each CLIPTextEncode feeds
for node_id, node in workflow.items():
    if node.get('class_type') in ('KSampler', 'LTXVConditioning', 'KSamplerAdvanced'):
        inputs = node.get('inputs', {})
        pos = inputs.get('positive')  # e.g., ["6", 0] — node 6 is positive
        neg = inputs.get('negative')  # e.g., ["7", 0] — node 7 is negative
        print(f"Positive node: {pos[0]}, Negative node: {neg[0]}")
```

Always inject your prompt into the **positive** node ID. Never guess by order.

### VRAM for Video Models
Wan 2.2 and LTX 2.3 (22B) are heavy. If the workflow has a `virtual_vram_gb` parameter node (DisTorch2), set it explicitly. For 24GB cards without DisTorch2, ensure `--lowvram` or `--normalvram` is set in the ComfyUI launch args on the server.

### Payload Size
Large video workflow JSONs can exceed shell argument limits. Always write the payload to a temp file and reference it with `curl -d @/tmp/payload.json` rather than inlining the JSON.

## Verification Checklist
- [ ] Payload is correctly wrapped in `{"prompt": ...}`
- [ ] Prompt is injected into the correct `node_id`
- [ ] Server returns a valid `prompt_id`
- [ ] Video generation task appears in ComfyUI queue