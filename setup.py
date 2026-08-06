#!/usr/bin/env python3
"""Backward-compatible entrypoint.

Historically this file was an environment validator (not a setuptools setup).
Prefer:

  python3 scripts/validate_env.py
  bash scripts/launch_cinesmith.sh

This wrapper keeps old docs working: `python3 setup.py`
"""

from pathlib import Path
import runpy
import sys

SCRIPT = Path(__file__).resolve().parent / "scripts" / "validate_env.py"
if not SCRIPT.exists():
    print(f"[!] Missing {SCRIPT}")
    sys.exit(1)
sys.argv[0] = str(SCRIPT)
runpy.run_path(str(SCRIPT), run_name="__main__")
