#!/usr/bin/env python3
"""
Batch render all hackathon_vid anchor frames using FLUX2 NVFP4 TURBO workflow.

Usage:
    python batch_flux2_turbo_hackathon.py

Renders 10 anchors at 1280x720 from flux2_anchor_frames.md
Downloads outputs to hackathon_vid/04_assets/
"""

import json
import requests
import time
import random
import re
import sys
from pathlib import Path

HOST = "http://localhost:8188"
PROMPT_FILE = Path("~/Desktop/projects/hackathon_vid/03_prompts/flux2_anchor_frames.md")
OUTPUT_DIR = Path("~/Desktop/projects/hackathon_vid/04_assets")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

with open("~/Downloads/image_flux2_text_to_image_TURBO.json", encoding="utf-8") as f:
    TEMPLATE = json.load(f)


def parse_anchors(filepath: Path) -> list[tuple[str, str]]:
    """Parse [ANCHOR_X.X] titles and prompt texts from markdown."""
    with open(filepath, encoding="utf-8") as f:
        content = f.read()

    pattern = r'### \[(ANCHOR_\d+\.\d+)\] .*?\n(.*?)(?=\n\s*### \[|\n\s*---|\s*$)'
    matches = re.findall(pattern, content, re.DOTALL)
    return [(anchor_id, text.strip()) for anchor_id, text in matches]


def build_workflow(prompt_text: str, filename_prefix: str, seed: int) -> dict:
    wf = json.loads(json.dumps(TEMPLATE))
    wf["98:6"]["inputs"]["text"] = prompt_text
    wf["9"]["inputs"]["filename_prefix"] = filename_prefix
    wf["98:25"]["inputs"]["noise_seed"] = seed
    # Hackathon vid resolution: 1280x720
    wf["98:47"]["inputs"]["width"] = 1280
    wf["98:47"]["inputs"]["height"] = 720
    wf["98:48"]["inputs"]["width"] = 1280
    wf["98:48"]["inputs"]["height"] = 720
    return wf


def submit_workflow(workflow: dict) -> str | None:
    try:
        resp = requests.post(f"{HOST}/prompt", json={"prompt": workflow}, timeout=30)
        resp.raise_for_status()
        return resp.json().get("prompt_id")
    except Exception as e:
        print(f"  SUBMIT ERROR: {e}")
        return None


def poll_and_download(prompt_id: str, label: str) -> bool:
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
            return True

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
    anchors = parse_anchors(PROMPT_FILE)
    print(f"Found {len(anchors)} hackathon anchors\n")

    if not anchors:
        print("No anchors found.")
        sys.exit(1)

    submissions = []
    for anchor_id, prompt_text in anchors:
        prefix = f"HACKATHON_{anchor_id}"
        seed = random.randint(1, 2**32)
        wf = build_workflow(prompt_text, prefix, seed)

        print(f"Submitting {anchor_id}...")
        prompt_id = submit_workflow(wf)
        if prompt_id:
            submissions.append((prompt_id, anchor_id))
            print(f"  → {prompt_id}")
        else:
            print(f"  → FAILED")
        time.sleep(0.5)

    print(f"\nSubmitted {len(submissions)} / {len(anchors)} anchors")
    print("Polling for completion...\n")

    completed = set()
    max_polls = 180
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
    print(f"  Hackathon batch complete: {len(completed)} / {len(submissions)} done")
    print(f"  Output dir: {OUTPUT_DIR}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
