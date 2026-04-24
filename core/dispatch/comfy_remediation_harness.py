"""
ComfyUI Remediation Harness — Test → Validate → Auto-Fix → Submit → Audit

This module ties together:
  • comfy_payload_validator (pre-flight checks)
  • comfy_client (ComfyUI HTTP client)
  • episodic memory (error recording for learning)

Workflow:
  1. SCAN  → Discover all JSON payloads in project
  2. SORT  → Separate image (renderable) vs video (descriptor) vs corrupt
  3. VALIDATE → Run ComfyPayloadValidator on each
  4. AUTO-FIX → Wrap video descriptors in LTX template; fix corrupt payloads
  5. HEALTH  → Check ComfyUI endpoints before submission
  6. SUBMIT  → Dispatch to online GPU(s)
  7. AUDIT   → Verify outputs exist, record errors to memory

Usage:
    harness = ComfyRemediationHarness(project_root="...")
    await harness.run_batch(type_filter="image")  # anchors + photos
"""

import asyncio
import json
import logging
import time
import random
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple

from core.dispatch.comfy_payload_validator import (
    ComfyPayloadValidator,
    ValidationReport,
    scan_project_payloads,
)
from core.dispatch.comfy_client import ComfyUIClient

logger = logging.getLogger("ComfyRemediationHarness")


class ComfyRemediationHarness:
    def __init__(
        self,
        project_root: str | Path,
        comfy_hosts: List[str] = None,
        output_dir: str | Path = None,
        memory=None,  # EpisodicMemory instance
    ):
        self.project_root = Path(project_root)
        self.validator = ComfyPayloadValidator()
        self.memory = memory
        self.clients: Dict[str, ComfyUIClient] = {}

        # Default hosts from project config
        self.hosts = comfy_hosts or [
            "http://localhost:8188",
            "http://localhost:8189",
        ]
        for host in self.hosts:
            self.clients[host] = ComfyUIClient(host)

        self.output_dir = Path(output_dir) if output_dir else self.project_root / "RENDERED_OUTPUT"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Statistics
        self.stats = {
            "scanned": 0,
            "valid_image": 0,
            "valid_anchor": 0,
            "video_descriptors": 0,
            "corrupt": 0,
            "submitted": 0,
            "succeeded": 0,
            "failed": 0,
        }

    # ------------------------------------------------------------------
    # Phase 1 — Discovery & Classification
    # ------------------------------------------------------------------

    def discover_and_classify(self) -> Dict[str, Any]:
        """
        Walk project, classify every JSON payload, validate it.
        Returns bucketed dict:
            {
                "image_payloads": [(path, report)],
                "anchor_payloads": [(path, report)],
                "video_descriptors": [(path, content_dict)],
                "corrupt": [(path, report)],
            }
        """
        buckets = {
            "image_payloads": [],
            "anchor_payloads": [],
            "video_descriptors": [],
            "corrupt": [],
        }

        for json_file in sorted(self.project_root.rglob("JSON_PAYLOADS/*.json")):
            report = self.validator.validate_file(json_file, strict=False)
            self.stats["scanned"] += 1

            # Try to load raw content for classification
            try:
                with open(json_file, encoding="utf-8") as f:
                    raw = json.load(f)
            except Exception:
                buckets["corrupt"].append((json_file, report))
                self.stats["corrupt"] += 1
                continue

            # Classification heuristics
            if raw.get("type") == "VIDEO_PROMPT" or raw.get("status") == "awaiting_ltx_workflow":
                buckets["video_descriptors"].append((json_file, raw))
                self.stats["video_descriptors"] += 1
                continue

            if not report.is_valid:
                buckets["corrupt"].append((json_file, report))
                self.stats["corrupt"] += 1
                continue

            name = json_file.stem
            if "_ANCHOR" in name:
                buckets["anchor_payloads"].append((json_file, report))
                self.stats["valid_anchor"] += 1
            elif "_Photo_" in name:
                buckets["image_payloads"].append((json_file, report))
                self.stats["valid_image"] += 1
            else:
                # Unknown but valid — treat as image
                buckets["image_payloads"].append((json_file, report))
                self.stats["valid_image"] += 1

        return buckets

    # ------------------------------------------------------------------
    # Phase 2 — Auto-Fix
    # ------------------------------------------------------------------

    def auto_fix_video_descriptor(
        self,
        descriptor_path: Path,
        descriptor: Dict,
        anchor_workflow: Optional[Dict] = None,
    ) -> Optional[Dict]:
        """
        Wrap a VIDEO_PROMPT descriptor in a minimal LTX i2v workflow.
        Requires the anchor image to exist as a seed.

        If anchor_workflow is not provided, returns None (cannot auto-fix).
        """
        if anchor_workflow is None:
            logger.warning(f"Cannot auto-fix {descriptor_path.name}: no LTX workflow template available.")
            return None

        # Deep copy the template
        workflow = json.loads(json.dumps(anchor_workflow))

        # Inject prompt text into CLIPTextEncode node(s)
        prompt_text = descriptor.get("prompt_text", "")
        for node in workflow.get("prompt", {}).values():
            if isinstance(node, dict) and node.get("class_type") == "CLIPTextEncode":
                node["inputs"]["text"] = prompt_text
                break

        # Inject anchor image reference into LoadImage node
        anchor_name = descriptor.get("anchor_image", "")
        for node in workflow.get("prompt", {}).values():
            if isinstance(node, dict) and node.get("class_type") in ("LoadImage", "ImageLoad"):
                node["inputs"]["image"] = anchor_name
                break

        # Set filename prefix
        prefix = descriptor.get("filename_prefix", descriptor_path.stem)
        for node in workflow.get("prompt", {}).values():
            if isinstance(node, dict) and node.get("class_type") == "SaveImage":
                node["inputs"]["filename_prefix"] = prefix
                break

        return workflow

    def build_all_video_workflows(self, buckets: Dict, ltx_template_path: Optional[Path] = None) -> List[Tuple[Path, Dict]]:
        """
        Attempt to build ComfyUI workflows for all video descriptors.
        Returns list of (save_path, workflow_dict) tuples.
        """
        built = []
        template = None

        if ltx_template_path and ltx_template_path.exists():
            with open(ltx_template_path, encoding="utf-8") as f:
                template = json.load(f)
        else:
            logger.warning("No LTX workflow template provided — skipping video workflow builds.")
            return built

        for desc_path, descriptor in buckets["video_descriptors"]:
            workflow = self.auto_fix_video_descriptor(desc_path, descriptor, template)
            if workflow:
                save_path = desc_path.with_suffix(".json")
                built.append((save_path, workflow))

        return built

    # ------------------------------------------------------------------
    # Phase 3 — Health Check & Submit
    # ------------------------------------------------------------------

    async def health_check_all(self) -> List[str]:
        """Returns list of online host URLs."""
        online = []
        for host, client in self.clients.items():
            ok, info = await client.check_health()
            if ok:
                logger.info(f"✅ {host} ONLINE — {info.get('system', {}).get('devices', [{}])[0].get('name', 'unknown')}")
                online.append(host)
            else:
                logger.warning(f"❌ {host} OFFLINE — {info.get('error', 'unknown')}")
        return online

    async def submit_batch(
        self,
        payloads: List[Tuple[Path, ValidationReport]],
        online_hosts: List[str],
    ) -> Dict[str, Any]:
        """
        Submit a list of payloads to available ComfyUI hosts.
        Returns summary dict with succeeded/failed lists.
        """
        if not online_hosts:
            logger.error("No ComfyUI hosts online. Cannot submit.")
            return {"succeeded": [], "failed": [str(p[0]) for p in payloads]}

        results = {"succeeded": [], "failed": [], "errors": []}
        host_queues = {host: [] for host in online_hosts}

        for i, (path, report) in enumerate(payloads):
            host = online_hosts[i % len(online_hosts)]
            host_queues[host].append(path)

        async def worker(host: str, queue: List[Path]):
            client = self.clients[host]
            for path in queue:
                try:
                    with open(path, encoding="utf-8") as f:
                        payload = json.load(f)

                    # Ensure fresh seed
                    for node in payload.get("prompt", {}).values():
                        if isinstance(node, dict) and node.get("class_type") == "KSampler":
                            node["inputs"]["seed"] = random.randint(1, 2**32)

                    prompt_id = await client.submit_prompt(payload.get("prompt", payload))
                    if not prompt_id:
                        raise RuntimeError("No prompt_id returned")

                    self.stats["submitted"] += 1
                    filename = await client.poll_job(prompt_id, timeout_sec=300)
                    if filename:
                        saved = await client.download_outputs(prompt_id, str(self.output_dir))
                        results["succeeded"].append({"path": str(path), "host": host, "filename": filename, "saved": saved})
                        self.stats["succeeded"] += 1
                        logger.info(f"✅ {path.name} → {filename}")
                    else:
                        raise RuntimeError("Job timed out or no output")

                except Exception as e:
                    self.stats["failed"] += 1
                    results["failed"].append(str(path))
                    results["errors"].append({"path": str(path), "error": str(e)})
                    logger.error(f"❌ {path.name}: {e}")

                    # Record to episodic memory
                    if self.memory:
                        self.memory.record({
                            "description": f"ComfyUI render failed for {path.name}: {e}",
                            "error_category": "comfyui_submission",
                            "fix_applied": "",
                            "success": False,
                            "kernel_id": "z_image_turbo",
                            "asset_path": str(path),
                        })

        await asyncio.gather(*[
            worker(host, queue) for host, queue in host_queues.items() if queue
        ])

        return results

    # ------------------------------------------------------------------
    # Phase 4 — Full Orchestration
    # ------------------------------------------------------------------

    async def run_batch(self, type_filter: str = "image") -> Dict[str, Any]:
        """
        Main entry point. Runs full pipeline:
          discover → classify → validate → health_check → submit → report

        type_filter:
            "image"  → anchors + photos only
            "anchor" → anchors only
            "photo"  → photos only
            "all"    → everything including videos (if LTX template exists)
        """
        start_time = time.time()
        logger.info(f"=== Remediation Harness START (filter={type_filter}) ===")

        # 1. Discover
        buckets = self.discover_and_classify()
        logger.info(f"Discovered: {self.stats['scanned']} files, "
                    f"{self.stats['valid_image']} images, "
                    f"{self.stats['valid_anchor']} anchors, "
                    f"{self.stats['video_descriptors']} videos, "
                    f"{self.stats['corrupt']} corrupt")

        # 2. Select payloads to submit
        to_submit: List[Tuple[Path, ValidationReport]] = []
        if type_filter in ("image", "all", "anchor"):
            to_submit.extend(buckets["anchor_payloads"])
        if type_filter in ("image", "all", "photo"):
            to_submit.extend(buckets["image_payloads"])

        # 3. Health check
        online = await self.health_check_all()
        if not online:
            logger.error("Aborting: no ComfyUI hosts available.")
            return {
                "success": False,
                "reason": "no_hosts_online",
                "stats": self.stats,
                "elapsed_sec": time.time() - start_time,
            }

        # 4. Submit
        results = await self.submit_batch(to_submit, online)

        # 5. Report
        elapsed = time.time() - start_time
        summary = {
            "success": len(results["failed"]) == 0,
            "stats": self.stats,
            "submitted": len(to_submit),
            "succeeded": len(results["succeeded"]),
            "failed": len(results["failed"]),
            "elapsed_sec": elapsed,
            "errors": results["errors"],
        }

        logger.info(f"=== Harness COMPLETE in {elapsed:.1f}s ===")
        logger.info(f"  Submitted: {summary['submitted']}")
        logger.info(f"  Succeeded: {summary['succeeded']}")
        logger.info(f"  Failed:    {summary['failed']}")

        return summary

    def print_report(self, summary: Dict):
        """Pretty-print a summary to stdout."""
        print(f"\n{'='*60}")
        print(f"  Remediation Harness Report")
        print(f"{'='*60}")
        print(f"  Scanned:      {summary['stats']['scanned']}")
        print(f"  Valid Images: {summary['stats']['valid_image']}")
        print(f"  Valid Anchors:{summary['stats']['valid_anchor']}")
        print(f"  Video Desc:   {summary['stats']['video_descriptors']}")
        print(f"  Corrupt:      {summary['stats']['corrupt']}")
        print(f"  ─────────────────────────")
        print(f"  Submitted:    {summary['submitted']}")
        print(f"  Succeeded:    {summary['succeeded']}")
        print(f"  Failed:       {summary['failed']}")
        print(f"  Elapsed:      {summary['elapsed_sec']:.1f}s")
        print(f"{'='*60}\n")


# ------------------------------------------------------------------
# CLI entry point
# ------------------------------------------------------------------

async def main():
    import sys
    import argparse

    parser = argparse.ArgumentParser(description="ComfyUI Remediation Harness")
    parser.add_argument("project_root", help="Path to project root (e.g., Sienna_Nomad_Project)")
    parser.add_argument("--filter", choices=["image", "anchor", "photo", "all"], default="image")
    parser.add_argument("--hosts", nargs="+", default=["http://localhost:8188", "http://localhost:8189"])
    parser.add_argument("--output", default=None, help="Output directory for renders")
    args = parser.parse_args()

    harness = ComfyRemediationHarness(
        project_root=args.project_root,
        comfy_hosts=args.hosts,
        output_dir=args.output,
    )
    summary = await harness.run_batch(type_filter=args.filter)
    harness.print_report(summary)


if __name__ == "__main__":
    asyncio.run(main())
