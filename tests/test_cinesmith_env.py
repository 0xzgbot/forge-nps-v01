"""Tests for portable paths and Hermes isolation."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from core.cinesmith_env import (
    apply_hermes_isolation,
    default_media_root,
    cinesmith_hermes_cli_argv,
    cinesmith_hermes_engine_root,
    cinesmith_hermes_home,
    cinesmith_hermes_launcher,
    cinesmith_hermes_python,
    hermes_isolated_env,
    hermes_isolation_status,
    repo_root,
)
from core.hermes.pipeline.profile_cli import HermesProfileCLI


def test_repo_root_points_at_cinesmith():
    root = repo_root()
    assert (root / "dashboard" / "cinesmith_dashboard.py").exists()
    assert (root / "core" / "cinesmith_env.py").exists()


def test_hermes_home_is_repo_local(tmp_path, monkeypatch):
    monkeypatch.delenv("CINESMITH_ALLOW_GLOBAL_HERMES", raising=False)
    monkeypatch.setenv("HERMES_HOME", str(Path.home() / ".hermes"))
    env = hermes_isolated_env(root=repo_root())
    assert env["HERMES_HOME"] == str(cinesmith_hermes_home())
    assert Path(env["HERMES_HOME"]).resolve() != (Path.home() / ".hermes").resolve()
    assert env["HERMES_HOME"].endswith("hermes_home")


def test_apply_hermes_isolation_overrides_global(monkeypatch):
    monkeypatch.delenv("CINESMITH_ALLOW_GLOBAL_HERMES", raising=False)
    monkeypatch.setenv("HERMES_HOME", str(Path.home() / ".hermes"))
    home = apply_hermes_isolation()
    assert Path(os.environ["HERMES_HOME"]).resolve() == home.resolve()
    assert Path(os.environ["HERMES_HOME"]).resolve() != (Path.home() / ".hermes").resolve()


def test_isolation_status_reports_ok():
    status = hermes_isolation_status()
    assert status["hermes_home_exists"] is True
    assert "hermes_home" in str(status["hermes_home"])
    # launcher may or may not exist depending on checkout depth; only assert key present
    assert "hermes_launcher_exists" in status
    assert status["using_global_hermes"] is False or status.get("allow_global_hermes") is True
    prefix = status.get("hermes_cli_argv_prefix") or []
    assert len(prefix) == 2
    assert "hermes_engine" in str(prefix[1]) or str(prefix[1]).endswith("hermes")


def test_default_media_root_honors_env(tmp_path, monkeypatch):
    target = tmp_path / "custom_media"
    monkeypatch.setenv("CINESMITH_MEDIA_ROOT", str(target))
    root = default_media_root()
    assert root == target.resolve()
    assert root.exists()


def test_cinesmith_hermes_launcher_path():
    launcher = cinesmith_hermes_launcher()
    assert launcher.name == "hermes"
    assert launcher.parent.name == "hermes_engine"


def test_isolated_env_never_points_at_global_home(monkeypatch):
    monkeypatch.delenv("CINESMITH_ALLOW_GLOBAL_HERMES", raising=False)
    monkeypatch.setenv("HERMES_HOME", str(Path.home() / ".hermes"))
    env = hermes_isolated_env(base={"HERMES_HOME": str(Path.home() / ".hermes"), "PATH": "/usr/bin"})
    home = Path(env["HERMES_HOME"]).resolve()
    assert home == cinesmith_hermes_home().resolve()
    assert home != (Path.home() / ".hermes").resolve()
    assert "hermes_home" in str(home)


def test_isolated_env_prepends_hermes_engine_to_pythonpath(monkeypatch):
    monkeypatch.delenv("CINESMITH_ALLOW_GLOBAL_HERMES", raising=False)
    monkeypatch.setenv("PYTHONPATH", "/some/other/path")
    env = hermes_isolated_env()
    parts = env["PYTHONPATH"].split(os.pathsep)
    engine = str(cinesmith_hermes_engine_root())
    repo = str(repo_root().resolve())
    assert parts[0] == engine
    assert repo in parts
    assert "/some/other/path" in parts


def test_cinesmith_hermes_cli_argv_rewrites_bare_hermes_names(monkeypatch):
    monkeypatch.delenv("CINESMITH_PROFILE_CLI_RUNNER", raising=False)
    launcher = str(cinesmith_hermes_launcher())
    python = str(cinesmith_hermes_python())

    for bare in ("", "hermes", "cinesmith", "auto", "HERMES"):
        argv = cinesmith_hermes_cli_argv("chat", "-q", "hi", runner=bare if bare else None)
        assert argv[0] == python
        assert argv[1] == launcher
        assert argv[2:] == ["chat", "-q", "hi"]
        # Never a bare PATH name as argv0
        assert argv[0] not in {"hermes", "cinesmith"}
        assert Path(argv[1]).name == "hermes"
        assert "hermes_engine" in argv[1]


def test_cinesmith_hermes_cli_argv_preserves_explicit_runner():
    custom = "/opt/custom/hermes-wrapper"
    argv = cinesmith_hermes_cli_argv("--version", runner=custom)
    assert argv == [custom, "--version"]


def test_cinesmith_hermes_cli_argv_honors_env_runner(monkeypatch):
    monkeypatch.setenv("CINESMITH_PROFILE_CLI_RUNNER", "cinesmith")
    argv = cinesmith_hermes_cli_argv("doctor")
    # Bare env name still rewritten to vendored launcher
    assert argv[1] == str(cinesmith_hermes_launcher())
    assert argv[-1] == "doctor"


def test_profile_cli_runtime_env_is_isolated(monkeypatch):
    monkeypatch.delenv("CINESMITH_ALLOW_GLOBAL_HERMES", raising=False)
    monkeypatch.setenv("HERMES_HOME", str(Path.home() / ".hermes"))
    monkeypatch.setenv("CINESMITH_PROFILE_MODEL", "test-model")
    monkeypatch.setenv("CINESMITH_PROFILE_BASE_URL", "http://localhost:1234/v1")
    _args, env, debug = HermesProfileCLI()._runtime_args_and_env()
    assert Path(env["HERMES_HOME"]).resolve() == cinesmith_hermes_home().resolve()
    assert Path(env["HERMES_HOME"]).resolve() != (Path.home() / ".hermes").resolve()
    assert debug["hermes_home"] == env["HERMES_HOME"]
    assert str(cinesmith_hermes_engine_root()) in (env.get("PYTHONPATH") or "")


@pytest.mark.asyncio
async def test_profile_cli_subprocess_uses_isolated_env_and_vendored_launcher(monkeypatch):
    """CLI mode must spawn vendored launcher with HERMES_HOME=repo hermes_home."""
    monkeypatch.setenv("CINESMITH_PROFILE_USE_CLI", "true")
    monkeypatch.setenv("CINESMITH_PROFILE_MODEL", "test-model")
    monkeypatch.setenv("CINESMITH_PROFILE_BASE_URL", "http://localhost:1234/v1")
    monkeypatch.delenv("CINESMITH_ALLOW_GLOBAL_HERMES", raising=False)
    monkeypatch.setenv("HERMES_HOME", str(Path.home() / ".hermes"))
    monkeypatch.delenv("CINESMITH_PROFILE_CLI_RUNNER", raising=False)

    captured: dict = {}

    class FakeProc:
        returncode = 0

        async def communicate(self):
            return (b'{"ok": true, "compiled_prompt": "x"}', b"")

    async def fake_exec(*cmd, **kwargs):
        captured["cmd"] = list(cmd)
        captured["env"] = kwargs.get("env") or {}
        return FakeProc()

    with patch("asyncio.create_subprocess_exec", new=AsyncMock(side_effect=fake_exec)):
        result = await HermesProfileCLI().run_json("compiler", {"prompt": "test"})

    assert result is not None
    assert result.get("ok") is True
    cmd = captured["cmd"]
    env = captured["env"]
    assert len(cmd) >= 2
    assert cmd[0] == str(cinesmith_hermes_python())
    assert cmd[1] == str(cinesmith_hermes_launcher())
    assert "hermes_engine" in cmd[1]
    assert Path(env["HERMES_HOME"]).resolve() == cinesmith_hermes_home().resolve()
    assert Path(env["HERMES_HOME"]).resolve() != (Path.home() / ".hermes").resolve()
    # Never bare PATH hermes/cinesmith
    assert cmd[0] not in {"hermes", "cinesmith"}
    exchange = result.get("__exchange") or {}
    assert exchange.get("transport") == "cinesmith_hermes_cli"
    assert exchange.get("hermes_home") == env["HERMES_HOME"]


def test_allow_global_hermes_escape_hatch(monkeypatch, tmp_path):
    custom = tmp_path / "my-global-hermes"
    custom.mkdir()
    monkeypatch.setenv("CINESMITH_ALLOW_GLOBAL_HERMES", "1")
    env = hermes_isolated_env(base={"HERMES_HOME": str(custom), "CINESMITH_ALLOW_GLOBAL_HERMES": "1"})
    assert Path(env["HERMES_HOME"]).resolve() == custom.resolve()
    # Mirror still reports cinesmith home for diagnostics
    assert env["CINESMITH_HERMES_HOME"] == str(cinesmith_hermes_home())
