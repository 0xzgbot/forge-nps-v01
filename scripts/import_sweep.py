"""Import sweep: import every project module to surface import-time breakage."""
import importlib
import os
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

DIRS = ["core", "agents", "pipelines", "cinesmith_nexus", "dashboard", "marketing", "scripts", "promo_video_kit", "workflows", "templates"]
SKIP_PREFIXES = ("dashboard.cinesmith_dashboard", "scripts.llm_", "scripts.test_", "promo_video_kit.touchdesigner", "scripts._import_sweep")

failures = []
count = 0
for d in DIRS:
    base = ROOT / d
    if not base.exists():
        continue
    for py in sorted(base.rglob("*.py")):
        rel = py.relative_to(ROOT)
        parts = list(rel.with_suffix("").parts)
        if d in ("workflows", "templates", "promo_video_kit") and len(parts) > 2:
            continue
        mod = ".".join(parts)
        if mod.startswith(SKIP_PREFIXES):
            continue
        count += 1
        try:
            importlib.import_module(mod)
        except Exception as e:
            failures.append((mod, f"{type(e).__name__}: {e}"))
            if isinstance(e, (ImportError, ModuleNotFoundError)):
                continue  # dependency missing — note it
            print(f"--- {mod} ---")
            traceback.print_exc(limit=3)

print(f"\nIMPORT SWEEP: {count} modules, {len(failures)} failures")
for mod, err in failures:
    print(f"  FAIL {mod}: {err}")
