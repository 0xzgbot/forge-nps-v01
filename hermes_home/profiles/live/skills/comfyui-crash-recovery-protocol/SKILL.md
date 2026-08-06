---
name: comfyui-crash-recovery-protocol
description: Protocol for recovering assets after a ComfyUI or automation script crash.
---

# ComfyUI / Automation Crash Recovery Protocol

## Trigger
A crash occurs during a large-scale rendering or automation job (e.g., Cinesmith batch, ComfyUI mega-render), resulting in missing expected output files.

## Procedure

1. **Process Audit**: 
   - Run `ps aux | grep [script_name]` to check if the orchestration script is still active or hung.
2. **Script Forensics**: 
   - Read the source code of the responsible automation script (e.g., `re-render_batch.py`).
   - Identify hardcoded paths, dynamic path logic (`Path(__file__).parent`), and explicit output directory variables.
3. **Log Analysis**: 
   - Locate recent `.log` or `.txt` files in the user's home directory (e.g., `job_debug.log`) to find the last successfully written file path.
4. **Broad Sweep Recovery**:
   - Perform a manual `os.walk` through common project and desktop directories.
   - Filter by `mtime` (last 24h) and extension (`.png`, `.jpg`) to bypass shell permission errors that `find` might encounter.
5. **Verification**:
   - Cross-reference found files with the expected file naming convention defined in the project's prompt library/metadata.

## Pitfalls
- Standard `find` commands often fail due to permission restrictions on macOS; use Python-based `os.walk` for more resilient recovery sweeps.
- Don't assume a process is dead just because it's not in the standard ComfyUI UI; check the system process list (`ps aux`).