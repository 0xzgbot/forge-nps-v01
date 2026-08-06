#!/usr/bin/env python3
"""Cinesmith dashboard smoke checks.

This intentionally separates cheap API validation from expensive live render
runs. Use --live-campaign or --live-script only when the render stack is ready.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from typing import Any


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload).encode("utf-8")


class SmokeClient:
    def __init__(self, base_url: str, timeout: float = 20.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        stream: bool = False,
    ) -> tuple[int, Any]:
        data = _json_bytes(payload) if payload is not None else None
        req = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            method=method,
            headers={"Content-Type": "application/json"} if payload is not None else {},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                status = int(resp.status)
                body = resp.read(65536 if stream else -1).decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            status = int(exc.code)
            body = exc.read().decode("utf-8", errors="replace")
        if stream:
            return status, body
        try:
            return status, json.loads(body) if body else {}
        except json.JSONDecodeError:
            return status, body


def check(condition: bool, label: str, detail: str = "") -> bool:
    if condition:
        print(f"[OK] {label}")
        return True
    suffix = f": {detail}" if detail else ""
    print(f"[FAIL] {label}{suffix}")
    return False


def expect_json_ok(client: SmokeClient, method: str, path: str, payload: dict[str, Any] | None = None) -> bool:
    status, data = client.request(method, path, payload)
    ok = status < 400 and isinstance(data, dict)
    return check(ok, f"{method} {path}", f"status={status} body={str(data)[:240]}")


def run_light_checks(client: SmokeClient) -> bool:
    ok = True
    ok &= expect_json_ok(client, "GET", "/api/stats")
    ok &= expect_json_ok(client, "GET", "/api/config")
    ok &= expect_json_ok(client, "GET", "/api/config/effective")
    ok &= expect_json_ok(client, "GET", "/api/script/storyboard/image-models")
    ok &= expect_json_ok(client, "GET", "/api/memory/health")
    ok &= expect_json_ok(client, "POST", "/api/shots/reindex-storage", {})

    status, readiness = client.request("GET", "/api/system/readiness")
    ok &= check(status < 400 and isinstance(readiness, dict), "GET /api/system/readiness", f"status={status}")
    if isinstance(readiness, dict):
        checks = readiness.get("checks") or {}
        isolation = (checks.get("isolation") or {})
        iso_detail = isolation.get("detail") if isinstance(isolation, dict) else {}
        using_global = bool(iso_detail.get("using_global_hermes")) if isinstance(iso_detail, dict) else False
        ok &= check(not using_global, "Hermes isolation (not using ~/.hermes)", str(iso_detail)[:240])
        ok &= check("status" in readiness, "readiness has overall status", str(readiness.get("status")))

    # Product surface (modular routes)
    status, hub = client.request("GET", "/api/product/create-hub")
    ok &= check(
        status < 400 and isinstance(hub, dict) and hub.get("status") == "ok",
        "GET /api/product/create-hub",
        f"status={status}",
    )
    if isinstance(hub, dict):
        ok &= check(
            isinstance(hub.get("sample_briefs"), list) and len(hub.get("sample_briefs") or []) >= 1,
            "create-hub sample_briefs",
            str(type(hub.get("sample_briefs"))),
        )
        ok &= check(
            isinstance(hub.get("quick_path"), list) and len(hub.get("quick_path") or []) >= 3,
            "create-hub quick_path",
            str(hub.get("quick_path"))[:120],
        )
    ok &= expect_json_ok(client, "GET", "/api/product/suggestions?brief=cinematic+story&limit=4")
    ok &= expect_json_ok(client, "GET", "/api/product/queue-summary")
    ok &= expect_json_ok(client, "GET", "/api/product/wizard-state")
    ok &= expect_json_ok(client, "GET", "/api/product/review/queue")
    ok &= expect_json_ok(client, "GET", "/api/product/agency-desk")
    ok &= expect_json_ok(client, "GET", "/api/product/ab-compare/recent")
    ok &= expect_json_ok(client, "GET", "/api/script/series")
    # Static polish assets (coach + package guide for Spark recovery banner)
    for path in (
        "/static/js/cinesmith-coach.js",
        "/static/css/cinesmith-polish.css",
        "/static/docs/DESKTOP_SPARK_PACKAGE.md",
    ):
        st, _body = client.request("GET", path)
        ok &= check(st == 200, f"GET {path}", f"status={st}")
    status, score = client.request("POST", "/api/product/scorecard", {
        "shots": [
            {"prompt": "hero red jacket neon rain alley"},
            {"prompt": "hero red jacket neon rain rooftop"},
        ]
    })
    ok &= check(
        status < 400 and isinstance(score, dict) and isinstance(score.get("scorecard"), dict),
        "POST /api/product/scorecard",
        f"status={status} body={str(score)[:200]}",
    )
    # Export for smoke script project if present
    status, exp = client.request("POST", "/api/script/export-package?script_id=smoke_script_persistence", None)
    ok &= check(
        status < 400 and isinstance(exp, dict) and exp.get("status") == "ok",
        "POST /api/script/export-package (smoke project)",
        f"status={status} body={str(exp)[:220]}",
    )

    status, config_before = client.request("GET", "/api/config")
    default_provider = ""
    if isinstance(config_before, dict):
        default_provider = str(config_before.get("storyboard_images", {}).get("default_provider") or "spark:flux2_dev")
    status, data = client.request("POST", "/api/config/save", {"updates": {"storyboard_images.default_provider": default_provider}})
    ok &= check(status < 400 and isinstance(data, dict), "config persistence write", f"status={status} body={str(data)[:240]}")
    status, config_after = client.request("GET", "/api/config")
    saved_provider = ""
    if isinstance(config_after, dict):
        saved_provider = str(config_after.get("storyboard_images", {}).get("default_provider") or "")
    ok &= check(status < 400 and saved_provider == default_provider, "config persistence readback", f"{saved_provider} != {default_provider}")

    script_id = "smoke_script_persistence"
    save_payload = {
        "script_id": script_id,
        "title": "Smoke Script Persistence",
        "brief": "A short dashboard smoke test project.",
        "tone": "clean validation",
        "runtime_seconds": 15,
        "target_scenes": 1,
        "status": "draft",
    }
    status, data = client.request("POST", "/api/script/projects/save", save_payload)
    ok &= check(status < 400 and data.get("status") == "ok", "saved script persistence write", str(data)[:240])
    status, data = client.request("GET", f"/api/script/projects/{script_id}")
    project = data.get("project", {}) if isinstance(data, dict) else {}
    ok &= check(
        status < 400 and project.get("script_id") == script_id and project.get("brief") == save_payload["brief"],
        "saved script persistence readback",
        str(data)[:240],
    )

    legacy_routes: list[tuple[str, str, dict[str, Any]]] = [
        ("POST", "/api/shots/dispatch-all", {}),
        ("POST", "/api/shots/dispatch", {"shot_id": "smoke", "prompt": "smoke"}),
        ("POST", "/api/submit-recipe", {"recipe": {"prompt": "smoke"}}),
        ("POST", "/api/inject-prompt", {"prompt": "smoke"}),
        ("POST", "/api/render", {"prompt": "smoke"}),
        ("POST", "/api/render/audit", {"image_path": "", "prompt": "smoke"}),
    ]
    for method, path, payload in legacy_routes:
        status, data = client.request(method, path, payload)
        detail = data.get("detail", data) if isinstance(data, dict) else {}
        ok &= check(
            status == 410 and isinstance(detail, dict) and detail.get("status") == "legacy_disabled",
            f"legacy disabled {path}",
            f"status={status} body={str(data)[:240]}",
        )

    status, body = client.request("POST", "/api/hermes/chat", {"message": "Return a one word smoke response."}, stream=True)
    ok &= check(status < 400 and bool(str(body).strip()), "POST /api/hermes/chat stream", f"status={status} body={str(body)[:240]}")
    return bool(ok)


def run_live_script(client: SmokeClient) -> bool:
    payload = {
        "script_id": f"smoke_live_{int(time.time())}",
        "title": "Smoke Live Script Pipeline",
        "brief": "A tiny cinematic story: a maker finds a glowing button, presses it, and the workshop comes alive.",
        "tone": "sharp, cinematic, practical",
        "runtime_seconds": 20,
        "target_scenes": 2,
        "target_shots": 2,
        "storyboard_target_panels": 2,
        "storyboard_panels_per_board": 2,
        "storyboard_image_provider": "spark",
        "storyboard_spark_model": "flux2_dev",
        "run_video": False,
        "wait_for_videos": False,
        "stop_after": "frames",
    }
    status, data = client.request("POST", "/api/script/pipeline/start", payload)
    if not check(status < 400 and data.get("status") == "ok", "POST /api/script/pipeline/start", str(data)[:240]):
        return False
    job_id = data.get("job", {}).get("job_id")
    if not job_id:
        print("[FAIL] script pipeline job id missing")
        return False
    deadline = time.time() + 7200
    while time.time() < deadline:
        status, data = client.request("GET", f"/api/script/pipeline/jobs/{job_id}")
        if status >= 400 or not isinstance(data, dict):
            print(f"[FAIL] GET /api/script/pipeline/jobs/{job_id}: status={status} body={str(data)[:240]}")
            return False
        job = data.get("job", {})
        project = data.get("project", {})
        print(f"[INFO] script job {job.get('status')} phase={job.get('phase')} status={project.get('status')}")
        if job.get("status") == "complete":
            panel_jobs = project.get("storyboard_panel_jobs", {})
            ready = sum(
                1
                for items in panel_jobs.values()
                if isinstance(items, list)
                for item in items
                if isinstance(item, dict) and item.get("url")
            )
            return check(ready > 0, "live script frames completed", f"ready={ready}")
        if job.get("status") == "error":
            return check(False, "live script pipeline", str(job.get("error") or "")[:500])
        time.sleep(10)
    return check(False, "live script pipeline timeout")


def run_live_campaign(client: SmokeClient) -> bool:
    payload = {
        "brief": "Smoke campaign: premium desk lamp product photos, clean shadows, modern studio, cohesive brand look.",
        "length": "15s",
        "target_shots": 1,
        "workflow_ids": ["spark_image_z_image"],
        "platform_mode": "auto",
    }
    status, body = client.request("POST", "/api/hermes/run-campaign", payload, stream=True)
    if not check(status < 400, "POST /api/hermes/run-campaign stream", f"status={status} body={str(body)[:240]}"):
        return False
    lines = [line for line in str(body).splitlines() if line.strip()]
    event_types: list[str] = []
    for line in lines:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and event.get("type"):
            event_types.append(str(event["type"]))
    required = {"kimi", "compiler", "spark"}
    return check(bool(required.intersection(event_types)), "live campaign emitted pipeline events", ", ".join(event_types[:20]))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Cinesmith dashboard smoke checks.")
    parser.add_argument("--base-url", default="http://127.0.0.1:7000")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--live-script", action="store_true", help="Run a live Script Studio job through storyboard frames.")
    parser.add_argument("--live-campaign", action="store_true", help="Run a one-shot live campaign stream.")
    args = parser.parse_args()

    client = SmokeClient(args.base_url, timeout=args.timeout)
    ok = run_light_checks(client)
    if args.live_script:
        ok &= run_live_script(client)
    if args.live_campaign:
        ok &= run_live_campaign(client)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
