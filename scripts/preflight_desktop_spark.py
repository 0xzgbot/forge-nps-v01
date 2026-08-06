#!/usr/bin/env python3
"""Desktop + Spark package preflight.

Checks local install health for a creator Mac/PC + LAN Spark layout.
Prints PASS / FAIL / WARN per check.

Exit codes:
  0 — no hard FAILs (WARNs allowed, e.g. Spark offline)
  1 — one or more hard FAILs
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

# Repo root on path for core.cinesmith_env
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BLUE = "\033[94m"
RESET = "\033[0m"
DIM = "\033[2m"

# Core workflow stems / patterns expected for Desktop + Spark (flux2 t2i, ltx i2v, first_last).
CORE_WORKFLOW_SPECS: List[Tuple[str, Tuple[str, ...]]] = [
    (
        "flux2 text-to-image",
        (
            "01_flux2_text_to_image.json",
            "02_flux2_text_to_image_turbo.json",
        ),
    ),
    (
        "flux2 multi-ref character sheet",
        (
            "04_flux2_multi_reference_character_sheet.json",
            "02_flux2_multi_reference_character_sheet.json",
            "08_1_click_multiple_character_angles.json",
        ),
    ),
    (
        "ltx image-to-video",
        (
            "04_ltx2.3_image_to_video.json",
            "04_ltx2.3_image_to_video_v1.1.json",
            "11_ltx23_image_to_video.json",
            "14_ltx23_i2v_nvfp4.json",
        ),
    ),
    (
        "ltx first_last frame",
        (
            "05_ltx2.3_first_last_frame_to_video.json",
            "12_ltx23_first_last_frame_to_video.json",
        ),
    ),
]


def _line(level: str, label: str, detail: str = "") -> None:
    color = {"PASS": GREEN, "FAIL": RED, "WARN": YELLOW}.get(level, RESET)
    suffix = f"  {DIM}{detail}{RESET}" if detail else ""
    print(f"  [{color}{level:4s}{RESET}] {label}{suffix}")


def _load_dotenv(root: Path) -> None:
    """Best-effort load of .env into os.environ without requiring python-dotenv."""
    env_path = root / ".env"
    if not env_path.is_file():
        return
    try:
        for raw in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
    except OSError:
        pass


def check_python() -> bool:
    major, minor = sys.version_info[:2]
    ver = f"{major}.{minor}.{sys.version_info[2]}"
    if (major, minor) >= (3, 11):
        _line("PASS", "Python version", f"{ver} (>= 3.11)")
        return True
    _line("FAIL", "Python version", f"{ver} — need Python 3.11+")
    return False


def check_imports() -> bool:
    modules = [
        ("fastapi", "fastapi"),
        ("uvicorn", "uvicorn"),
        ("httpx", "httpx"),
        ("PIL", "Pillow"),
        ("pydantic", "pydantic"),
    ]
    ok = True
    missing: List[str] = []
    for import_name, pip_name in modules:
        try:
            __import__(import_name)
        except ImportError:
            ok = False
            missing.append(pip_name)
    if ok:
        _line("PASS", "Core imports", "fastapi, uvicorn, httpx, PIL, pydantic")
    else:
        _line(
            "FAIL",
            "Core imports",
            f"missing: {', '.join(missing)} — pip install -r requirements.txt",
        )
    return ok


def check_hermes_home(root: Path) -> bool:
    from core.cinesmith_env import apply_hermes_isolation, cinesmith_hermes_home

    apply_hermes_isolation(root=root)
    home = cinesmith_hermes_home(root)
    if not home.exists():
        try:
            home.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            _line("FAIL", "repo hermes_home", f"cannot create {home}: {exc}")
            return False
    if not home.is_dir():
        _line("FAIL", "repo hermes_home", f"not a directory: {home}")
        return False
    try:
        probe = home / ".cinesmith_preflight_write"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
    except OSError as exc:
        _line("FAIL", "repo hermes_home writable", f"{home}: {exc}")
        return False
    _line("PASS", "repo hermes_home", str(home))
    return True


def check_hermes_isolation(root: Path) -> bool:
    from core.cinesmith_env import apply_hermes_isolation, hermes_isolation_status

    apply_hermes_isolation(root=root)
    status = hermes_isolation_status(root=root)
    allow = bool(status.get("allow_global_hermes"))
    using_global = bool(status.get("using_global_hermes"))
    if using_global and not allow:
        _line(
            "FAIL",
            "HERMES_HOME isolation",
            f"points at ~/.hermes ({status.get('process_hermes_home')}); "
            "relaunch with scripts/launch_cinesmith.sh or set CINESMITH_ALLOW_GLOBAL_HERMES=1 only if intentional",
        )
        return False
    if using_global and allow:
        _line(
            "WARN",
            "HERMES_HOME isolation",
            "using global ~/.hermes (CINESMITH_ALLOW_GLOBAL_HERMES=1)",
        )
        return True
    detail = status.get("process_hermes_home") or status.get("hermes_home")
    _line("PASS", "HERMES_HOME isolation", str(detail))
    return True


def check_workflows(root: Path) -> bool:
    wf_dir = root / "workflows"
    if not wf_dir.is_dir():
        _line("FAIL", "workflows/", f"missing directory: {wf_dir}")
        return False
    ok = True
    for label, candidates in CORE_WORKFLOW_SPECS:
        found = next((name for name in candidates if (wf_dir / name).is_file()), None)
        if found:
            _line("PASS", f"workflow: {label}", found)
        else:
            # Fuzzy: any matching pattern in directory
            fuzzy = _fuzzy_workflow(wf_dir, label)
            if fuzzy:
                _line("PASS", f"workflow: {label}", fuzzy)
            else:
                ok = False
                _line(
                    "FAIL",
                    f"workflow: {label}",
                    f"none of {', '.join(candidates[:2])}…",
                )
    return ok


def _fuzzy_workflow(wf_dir: Path, label: str) -> Optional[str]:
    names = [p.name for p in wf_dir.glob("*.json")]
    if "flux2" in label and "text" in label:
        for n in names:
            if "flux2" in n.lower() and "text_to_image" in n.lower() and "klein" not in n.lower():
                return n
    if "image-to-video" in label or "i2v" in label:
        for n in names:
            low = n.lower()
            if "ltx" in low and ("image_to_video" in low or "i2v" in low):
                return n
    if "first_last" in label or "first" in label:
        for n in names:
            if "first_last" in n.lower() or "first-last" in n.lower():
                return n
    return None


def check_media_root(root: Path) -> bool:
    from core.cinesmith_env import default_media_root, ensure_media_layout

    try:
        media = default_media_root(root)
        paths = ensure_media_layout(media)
        media_path = Path(paths["root"])
        # Write probe
        with tempfile.NamedTemporaryFile(dir=media_path, prefix=".cinesmith_preflight_", delete=True) as fh:
            fh.write(b"ok")
            fh.flush()
        _line("PASS", "media root writable", str(media_path))
        return True
    except Exception as exc:
        _line("FAIL", "media root writable", str(exc)[:200])
        return False


def check_comfyui() -> bool:
    """Reachability is WARN-only when down (not a hard fail)."""
    url = (
        os.getenv("COMFYUI_PRIMARY")
        or os.getenv("SPARK_URL")
        or "http://127.0.0.1:8188"
    ).strip().rstrip("/")
    if not url.startswith("http"):
        _line("WARN", "COMFYUI_PRIMARY", f"invalid URL: {url}")
        return True  # not a hard fail
    probe = f"{url}/system_stats"
    try:
        import httpx
    except ImportError:
        _line("WARN", "COMFYUI_PRIMARY", "httpx missing — skip probe")
        return True
    try:
        with httpx.Client(timeout=3.0) as client:
            resp = client.get(probe)
        if resp.status_code < 500:
            _line("PASS", "COMFYUI_PRIMARY reachable", f"{url} (HTTP {resp.status_code})")
        else:
            _line("WARN", "COMFYUI_PRIMARY", f"{url} HTTP {resp.status_code}")
    except Exception as exc:
        _line(
            "WARN",
            "COMFYUI_PRIMARY unreachable",
            f"{url} — start Spark/ComfyUI or fix Settings ({type(exc).__name__})",
        )
    return True


def check_lm_studio() -> bool:
    """Optional — always WARN/PASS, never hard fail."""
    host = (os.getenv("LMSTUDIO_HOST") or "http://127.0.0.1:1234").strip().rstrip("/")
    if host and not host.startswith("http"):
        host = "http://" + host
    probe = f"{host}/v1/models"
    try:
        import httpx
    except ImportError:
        _line("WARN", "LM Studio (optional)", "httpx missing — skip probe")
        return True
    try:
        with httpx.Client(timeout=3.0) as client:
            resp = client.get(probe)
        if resp.status_code < 500:
            _line("PASS", "LM Studio (optional)", f"{host} (HTTP {resp.status_code})")
        else:
            _line("WARN", "LM Studio (optional)", f"{host} HTTP {resp.status_code}")
    except Exception:
        _line(
            "WARN",
            "LM Studio (optional) offline",
            f"{host} — only needed for local Hermes/Director",
        )
    return True


def main() -> int:
    root = _ROOT
    os.chdir(root)
    _load_dotenv(root)

    print(f"\n{BLUE}══ Cinesmith Desktop + Spark preflight ══{RESET}")
    print(f"{DIM}repo: {root}{RESET}\n")

    hard_ok = True
    hard_ok &= check_python()
    hard_ok &= check_imports()
    hard_ok &= check_hermes_home(root)
    hard_ok &= check_hermes_isolation(root)
    hard_ok &= check_workflows(root)
    hard_ok &= check_media_root(root)
    # Soft checks (never flip hard_ok to False)
    check_comfyui()
    check_lm_studio()

    print()
    if hard_ok:
        print(f"{GREEN}RESULT: PASS{RESET} — no hard failures (WARN lines are OK for package mode).")
        print(f"{DIM}Launch: ./scripts/launch_cinesmith.sh --package{RESET}\n")
        return 0
    print(f"{RED}RESULT: FAIL{RESET} — fix hard failures above before shipping/demo.")
    print(f"{DIM}See docs/DESKTOP_SPARK_PACKAGE.md{RESET}\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
