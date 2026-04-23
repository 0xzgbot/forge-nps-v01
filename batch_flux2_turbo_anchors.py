#!/usr/bin/env python3
"""
Batch render all Sienna Nomad anchor frames using FLUX2 NVFP4 TURBO workflow.

Usage:
    python batch_flux2_turbo_anchors.py

Submits all 60 anchors to ComfyUI queue upfront, then polls for completion.
Downloads outputs to Sienna_Nomad_Project/RENDERED_OUTPUT/
"""

import json
import requests
import time
import random
import sys
from pathlib import Path

HOST = "http://localhost:8188"
PROJECT_ROOT = Path("~/Desktop/projects/Sienna_Nomad_Project/04_Prompt_Library")
OUTPUT_DIR = Path("~/Desktop/projects/Sienna_Nomad_Project/RENDERED_OUTPUT")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Load FLUX2 TURBO workflow template
with open("~/Downloads/image_flux2_text_to_image_TURBO.json") as f:
    TEMPLATE = json.load(f)


def extract_prompt_from_anchor_json(json_path: Path) -> str:
    """Read anchor JSON payload and extract the prompt text."""
    with open(json_path) as f:
        data = json.load(f)
    prompt = data.get("prompt", {})
    for node in prompt.values():
        if isinstance(node, dict) and node.get("class_type") == "CLIPTextEncode":
            return node.get("inputs", {}).get("text", "")
    return ""


def discover_anchors() -> list[tuple[Path, str]]:
    """Find all anchor JSON payloads and extract prompts."""
    anchors = []
    for json_file in sorted(PROJECT_ROOT.rglob("JSON_PAYLOADS/*_ANCHOR.json")):
        prompt = extract_prompt_from_anchor_json(json_file)
        if prompt:
            anchors.append((json_file, prompt))
    return anchors


def build_workflow(prompt_text: str, filename_prefix: str, seed: int) -> dict:
    """Clone template and inject prompt, prefix, and seed."""
    wf = json.loads(json.dumps(TEMPLATE))
    wf["98:6"]["inputs"]["text"] = prompt_text
    wf["9"]["inputs"]["filename_prefix"] = filename_prefix
    wf["98:25"]["inputs"]["noise_seed"] = seed
    return wf


def submit_workflow(workflow: dict) -> str | None:
    """POST to ComfyUI, return prompt_id."""
    try:
        resp = requests.post(f"{HOST}/prompt", json={"prompt": workflow}, timeout=30)
        resp.raise_for_status()
        return resp.json().get("prompt_id")
    except Exception as e:
        print(f"  SUBMIT ERROR: {e}")
        return None


def poll_and_download(prompt_id: str, label: str) -> bool:
    """Poll history, download image on completion. Returns True on success."""
    try:
        resp = requests.get(f"{HOST}/history/{prompt_id}", timeout=10)
        resp.raise_for_status()
        hist = resp.json()
        if prompt_id not in hist:
            return False

        job = hist[prompt_id]
        status = job.get("status", {})

        if status.get("status_str") == "error":
            msgs = status.get("messages", [])
            for msg in msgs:
                if isinstance(msg, list) and len(msg) > 1 and msg[0] == "execution_error":
                    print(f"  ❌ {label}: {msg[1].get('exception_message', 'unknown')}")
            return True  # Done (failed)

        outputs = job.get("outputs", {})
        if outputs:
            for node_id, node_out in outputs.items():
                for img in node_out.get("images", []):
                    fname = img["filename"]
                    url = f"{HOST}/view?filename={fname}&type=output"
                    try:
                        r = requests.get(url, timeout=30)
                        r.raise_for_status()
                        path = OUTPUT_DIR / fname
                        with open(path, "wb") as f:
                            f.write(r.content)
                        print(f"  ✅ {label}: {fname} ({len(r.content)//1024}KB)")
                    except Exception as e:
                        print(f"  ❌ {label}: download failed: {e}")
            return True

        return False
    except Exception as e:
        print(f"  POLL ERROR {label}: {e}")
        return False


def main():
    anchors = discover_anchors()
    print(f"Found {len(anchors)} anchor payloads\n")

    if not anchors:
        print("No anchors found.")
        sys.exit(1)

    # Submit all anchors upfront
    submissions = []
    for json_file, prompt_text in anchors:
        stem = json_file.stem.replace("_ANCHOR", "")
        prefix = f"FLUX2_{stem}"
        seed = random.randint(1, 2**32)
        wf = build_workflow(prompt_text, prefix, seed)

        print(f"Submitting {stem}...")
        prompt_id = submit_workflow(wf)
        if prompt_id:
            submissions.append((prompt_id, stem))
            print(f"  → {prompt_id}")
        else:
            print(f"  → FAILED")
        time.sleep(0.5)  # Small delay to avoid overwhelming the queue

    print(f"\nSubmitted {len(submissions)} / {len(anchors)} anchors")
    print("Polling for completion...\n")

    completed = set()
    failed_polls = {}
    max_polls = 360  # 30 minutes max

    for poll_round in range(max_polls):
        if len(completed) >= len(submissions):
            break

        for prompt_id, label in submissions:
            if prompt_id in completed:
                continue
            if poll_and_download(prompt_id, label):
                completed.add(prompt_id)

        pending = len(submissions) - len(completed)
        if pending > 0:
            print(f"  [{poll_round+1}/{max_polls}] {len(completed)} done, {pending} pending...")
            time.sleep(5)
        else:
            break

    print(f"\n{'='*60}")
    print(f"  Batch complete: {len(completed)} / {len(submissions)} done")
    print(f"  Output dir: {OUTPUT_DIR}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
