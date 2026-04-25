---
name: comfyui-prompt-automation-orchestrator
description: Automates extraction of prompts from Markdown files, injection into ComfyUI 'Save' format JSONs, and execution via Direct API.
---

# Skill: comfyui-prompt-automation-orchestrator

## Description
Automates the end-to-end pipeline of extracting prompts from Markdown files, injecting them into ComfyUI 'Save' format JSON workflows, and executing them via the Direct API.

## Trigger Conditions
- When the user asks to "run the [Meal Name] prompts" or "generate images/video for [Meal Name]".
- When a batch of content needs to be pushed to the remote ComfyUI server.

## Workflow
1. **Locate Files:** Identify the `.md` prompt file and the target `.json` workflow in the `Food Prep Content` directory.
2. **Parse:** Use `prompt_parser_util.py` to extract text blocks from the Markdown.
3. **Inject:** Use the parser to inject the text into the target node's `widgets_values`.
4. **Wrap & Send:** Convert the "Save" format JSON into the `"prompt": { ... }` API format and use `curl` to POST to the remote ComfyUI endpoint.

## Pitfalls
- **Node IDs:** Ensure the Python script targets the correct `id` or `type` within the JSON.
- **JSON Wrapping:** Failure to wrap the 'Save' format into a 'prompt' object will result in 400 errors from ComfyUI.
- **VRAM:** High-resolution video tasks (Wan 2.2) require careful monitoring of the remote server's status.

## Dependencies
- `/Users/zgbot/.hermes/scripts/prompt_parser_util.py`
- ComfyUI Direct API (remote endpoint)
