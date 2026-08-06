"""Cinesmith runtime environment: portable paths and Hermes isolation.

Hard rule: Cinesmith-scoped Hermes runs use the repo-local hermes_home/ and
vendored hermes_engine/ launcher. They must never silently fall back to a
user's global ~/.hermes install.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Dict, List, Mapping, MutableMapping, Optional

# PATH bare names that must never be used as-is (often wrap ~/.hermes).
_BARE_HERMES_RUNNERS = frozenset({"", "auto", "hermes", "cinesmith", "cinesmith-hermes", "cinesmith_hermes"})


def repo_root() -> Path:
    """Return the Cinesmith repository root (parent of core/)."""
    return Path(__file__).resolve().parent.parent


def default_media_root(root: Optional[Path] = None) -> Path:
    """Resolve media root without hard-coding a user home path.

    Priority:
      1. CINESMITH_MEDIA_ROOT env
      2. Sibling folder CINESMITH_MEDIA (common local layout)
      3. <repo>/media (created if missing)
    """
    root = root or repo_root()
    env = (os.getenv("CINESMITH_MEDIA_ROOT") or os.getenv("FORGE_MEDIA_ROOT") or "").strip()
    if env:
        path = Path(env).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        return path.resolve()

    for sibling_name in ("CINESMITH_MEDIA", "FORGE_NPS_MEDIA"):
        sibling = (root.parent / sibling_name).resolve()
        if sibling.exists():
            return sibling

    local = (root / "media").resolve()
    local.mkdir(parents=True, exist_ok=True)
    for sub in ("images", "videos", "imports", "legacy", "identity_assets", "identity_templates"):
        (local / sub).mkdir(parents=True, exist_ok=True)
    return local


def cinesmith_hermes_home(root: Optional[Path] = None) -> Path:
    """Repo-local Hermes home — never ~/.hermes."""
    root = root or repo_root()
    path = (root / "hermes_home").resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def cinesmith_hermes_engine_root(root: Optional[Path] = None) -> Path:
    """Vendored hermes_engine directory under the Cinesmith repo."""
    root = root or repo_root()
    return (root / "hermes_engine").resolve()


def cinesmith_hermes_launcher(root: Optional[Path] = None) -> Path:
    """Vendored Hermes CLI entrypoint under hermes_engine/."""
    root = root or repo_root()
    return (cinesmith_hermes_engine_root(root) / "hermes").resolve()


def cinesmith_hermes_python(root: Optional[Path] = None) -> Path:
    """Python interpreter for Hermes CLI subprocesses.

    Prefer hermes_engine's local venv when present so hermes_cli imports work;
    otherwise fall back to the current interpreter (with PYTHONPATH set by
    hermes_isolated_env).
    """
    root = root or repo_root()
    engine = cinesmith_hermes_engine_root(root)
    for candidate in (
        engine / ".venv" / "bin" / "python",
        engine / ".venv" / "bin" / "python3",
        engine / "venv" / "bin" / "python",
        engine / "venv" / "bin" / "python3",
    ):
        if candidate.is_file():
            return candidate.resolve()
    return Path(sys.executable).resolve()


def _is_bare_hermes_runner(runner: str) -> bool:
    name = (runner or "").strip()
    if not name:
        return True
    # Absolute/relative path to something other than a bare name → custom.
    base = Path(name).name.lower()
    # Strip common Windows .exe for comparison.
    if base.endswith(".exe"):
        base = base[:-4]
    return base in _BARE_HERMES_RUNNERS or name.lower() in _BARE_HERMES_RUNNERS


def cinesmith_hermes_cli_argv(
    *cli_args: str,
    root: Optional[Path] = None,
    runner: Optional[str] = None,
) -> List[str]:
    """Build argv for a Cinesmith-isolated Hermes CLI invocation.

    Bare names (``hermes``, ``cinesmith``, empty, ``auto``) are rewritten to
    ``[python, <repo>/hermes_engine/hermes, ...]`` so PATH wrappers that point
    at ``~/.hermes`` are never used. An explicit non-bare runner path is kept
    as-is (still must be paired with hermes_isolated_env).
    """
    root = root or repo_root()
    if runner is None:
        runner = (os.getenv("CINESMITH_PROFILE_CLI_RUNNER") or os.getenv("FORGE_PROFILE_CLI_RUNNER") or "").strip()
    else:
        runner = str(runner).strip()

    if _is_bare_hermes_runner(runner):
        return [str(cinesmith_hermes_python(root)), str(cinesmith_hermes_launcher(root)), *cli_args]
    return [runner, *cli_args]


def hermes_isolated_env(
    base: Optional[Mapping[str, str]] = None,
    *,
    root: Optional[Path] = None,
    extra: Optional[Mapping[str, str]] = None,
) -> Dict[str, str]:
    """Build an env dict that forces Cinesmith Hermes isolation.

    Always sets:
      - HERMES_HOME -> <repo>/hermes_home
      - CINESMITH_HERMES_HOME (mirror for diagnostics)
      - PYTHONPATH includes <repo> and <repo>/hermes_engine (for vendored launcher)
      - HERMES_QUIET / NO_COLOR for cleaner subprocess output

    Explicitly does NOT inherit a caller's desire to use ~/.hermes unless
    CINESMITH_ALLOW_GLOBAL_HERMES=1 is set (escape hatch for advanced users).
    """
    root = root or repo_root()
    env: Dict[str, str] = dict(os.environ if base is None else base)
    allow_global = (env.get("CINESMITH_ALLOW_GLOBAL_HERMES") or env.get("FORGE_ALLOW_GLOBAL_HERMES")
                    or os.getenv("CINESMITH_ALLOW_GLOBAL_HERMES") or os.getenv("FORGE_ALLOW_GLOBAL_HERMES") or "").strip() in {
        "1",
        "true",
        "TRUE",
        "yes",
        "YES",
    }
    if not allow_global:
        env["HERMES_HOME"] = str(cinesmith_hermes_home(root))
    elif not (env.get("HERMES_HOME") or "").strip():
        env["HERMES_HOME"] = str(cinesmith_hermes_home(root))

    env["CINESMITH_HERMES_HOME"] = str(cinesmith_hermes_home(root))
    env["CINESMITH_REPO_ROOT"] = str(root.resolve())
    env.setdefault("HERMES_QUIET", "1")
    env.setdefault("NO_COLOR", "1")

    # Ensure vendored hermes_engine is importable for `python hermes_engine/hermes`.
    engine = str(cinesmith_hermes_engine_root(root))
    repo = str(root.resolve())
    existing_parts = [p for p in (env.get("PYTHONPATH") or "").split(os.pathsep) if p]
    prepend: List[str] = []
    for path in (engine, repo):
        if path not in existing_parts and path not in prepend:
            prepend.append(path)
    if prepend:
        env["PYTHONPATH"] = os.pathsep.join(prepend + existing_parts)

    if extra:
        env.update({k: str(v) for k, v in extra.items()})
    return env


def apply_hermes_isolation(environ: Optional[MutableMapping[str, str]] = None, *, root: Optional[Path] = None) -> Path:
    """Mutate process env so this Python process never defaults to ~/.hermes."""
    target = environ if environ is not None else os.environ
    root = root or repo_root()
    home = cinesmith_hermes_home(root)
    allow_global = (target.get("CINESMITH_ALLOW_GLOBAL_HERMES") or target.get("FORGE_ALLOW_GLOBAL_HERMES") or "").strip() in {"1", "true", "TRUE", "yes", "YES"}
    if not allow_global:
        target["HERMES_HOME"] = str(home)
    elif not (target.get("HERMES_HOME") or "").strip():
        target["HERMES_HOME"] = str(home)
    target["CINESMITH_HERMES_HOME"] = str(home)
    target["CINESMITH_REPO_ROOT"] = str(root.resolve())

    engine = str(cinesmith_hermes_engine_root(root))
    repo = str(root.resolve())
    existing_parts = [p for p in (target.get("PYTHONPATH") or "").split(os.pathsep) if p]
    prepend: List[str] = []
    for path in (engine, repo):
        if path not in existing_parts and path not in prepend:
            prepend.append(path)
    if prepend:
        target["PYTHONPATH"] = os.pathsep.join(prepend + existing_parts)
    return home


def hermes_isolation_status(root: Optional[Path] = None) -> Dict[str, object]:
    """Diagnostic payload for readiness UI / smoke tests."""
    root = root or repo_root()
    home = cinesmith_hermes_home(root)
    launcher = cinesmith_hermes_launcher(root)
    current = (os.getenv("HERMES_HOME") or "").strip()
    global_default = str(Path.home() / ".hermes")
    using_global = bool(current) and Path(current).expanduser().resolve() == Path(global_default).resolve()
    return {
        "repo_root": str(root.resolve()),
        "hermes_home": str(home),
        "hermes_launcher": str(launcher),
        "hermes_launcher_exists": launcher.exists(),
        "hermes_home_exists": home.exists(),
        "process_hermes_home": current or None,
        "using_global_hermes": using_global,
        "allow_global_hermes": (os.getenv("CINESMITH_ALLOW_GLOBAL_HERMES") or os.getenv("FORGE_ALLOW_GLOBAL_HERMES") or "").strip() in {"1", "true", "TRUE", "yes", "YES"},
        "isolation_ok": launcher.exists() and home.exists() and not using_global,
        "hermes_cli_argv_prefix": cinesmith_hermes_cli_argv(root=root)[:2],
    }


def ensure_media_layout(media_root: Optional[Path] = None) -> Dict[str, str]:
    """Create standard media subdirectories and return path map."""
    root = Path(media_root) if media_root is not None else default_media_root()
    root.mkdir(parents=True, exist_ok=True)
    paths = {
        "root": root,
        "images": root / "images",
        "videos": root / "videos",
        "imports": root / "imports",
        "legacy": root / "legacy",
        "identity_assets": root / "identity_assets",
        "identity_templates": root / "identity_templates",
        "local_spark_media": root / "local_spark_media",
    }
    for p in paths.values():
        p.mkdir(parents=True, exist_ok=True)
    return {k: str(v.resolve()) for k, v in paths.items()}
