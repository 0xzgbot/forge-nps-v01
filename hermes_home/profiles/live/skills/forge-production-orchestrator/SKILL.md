---
name: forge-production-orchestrator
description: Standardized protocol for executing the complete Forge production pipeline via a single command.
---

# forge-production-orchestrator

A standardized protocol for executing the complete Forge production pipeline from a single entry point. This skill governs the transition from creative concept to ready-to-render ComfyUI payloads.

## Workflow Overview
The orchestrator follows a linear, high-velocity sequence to transform an idea into production assets:
1. **Genesis Phase (D1-D3):** Generates World Bible and Pilot Script $\rightarrow$ Initializes Project Folder Structure.
2. **Prompting Phase (J9):** Decomposes script scenes into individual cinematic shots $\rightarrow$ Injects high-fidelity technical parameters (Lens, Motion, Lighting) $\rightarrow$ Saves JSON payloads in `JSON_PAYLOADS/`.
3. **Submission Phase (J8):** Picks up JSON payloads $\rightarrow$ Distributes them via round-robin across dual ComfyUI hosts $\rightarrow$ Polls and downloads final assets.

## Execution Command
The primary entry point is the `forge_run.py` script located in the project root.

```bash
python forge_run.py --idea "Concept description" [--name "project_folder_name"] [--hosts "http://host1:port" "http://host2:port"]
```

## Key Parameters & Flags
- `--idea`: (Required) The core creative concept or prompt string.
- `--name`: (Optional) Custom directory name for the project. Defaults to a sanitized version of the idea.
- `--hosts`: (Optional) List of available ComfyUI API endpoints for load balancing.

## Technical Requirements & Dependencies
- **KimiBridge:** Required for all LLM-based reasoning/generation stages.
- **Directory Structure:** Requires `data/projects` to be writable.
- **Payload Format:** The system expects JSON files in the `JSON_PAYLOADS/` subfolder of a project to follow the schema established by the `AssetPromptGenerator`.

## Pitfalls & Troubleshooting
- **Kimi API Errors:** If Kimi fails, the pipeline will halt. Ensure `KIMI_API_KEY` is set in the environment.
- **ComfyUI Connectivity:** If no hosts are reachable, the submission phase will fail immediately. Verify host URLs and ports.
- **Pathing Issues:** Always run from the project root to ensure `sys.path` correctly resolves `core.*` modules.
