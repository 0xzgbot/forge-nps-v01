---
name: comfyui-api-workflow-automation
description: Workflow for integrating new ComfyUI workflows into an MCP server and handling directory restriction errors.
---

# ComfyUI API Workflow Automation (Symlink vs Copy)

This skill provides a workflow for integrating new or shared ComfyUI workflows into an active MCP server environment.

## Trigger Conditions
- When adding new `.json` workflows to a remote ComfyUI server via MCP.
- When encountering "Attempted to read workflow outside of the configured directory" errors despite files being visible in `list_workflows`.

## Workflow Steps

1. **Identify Source:** Locate the target workflow (e.g., in a Google Drive shared folder).
2. **Initial Integration (Symlink):** Attempt to symlink the file to the ComfyUI root directory using `ln -sf <source> <target>`. This is preferred for real-time updates.
3. **Verification:** Run `mcp_comfyui_mcp_list_workflows` to ensure the file is visible.
4. **Test Read:** Attempt `mcp_comfyui_mcp_read_workflow` on the new file.
5. **Error Handling (The "Symlink Trap"):** 
   - If `read_workflow` returns an error stating the file is "outside of the configured directory" even though it appears in the list, the MCP server is failing to resolve the symlink.
6. **Resolution (Hard Copy):** 
   - Instead of a symlink, perform a direct copy: `cp <source> <target>`.
7. **Final Verification:** Re-run `mcp_comfyui_mcp_read_workflow` to confirm successful access.

## Pitfalls & Lessons Learned
- **Symlink Resolution:** Some MCP server implementations do not follow symlinks for security reasons, even if the link points to a valid path within the allowed root. A hard copy is the most reliable fallback.
- **Sandbox Limitations:** Do NOT attempt to use `execute_code` (Python) to call MCP tools directly; they are agent-level tools and cannot be imported into the Python sandbox. Use direct tool calls instead.

## Node Mapping Standard
When automating via API, always inspect the JSON structure first to map:
- **Prompt Text Node ID** (e.g., `6`)
- **Resolution/Latent Node ID** (e.g., `8`)
