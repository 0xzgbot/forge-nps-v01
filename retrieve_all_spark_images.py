#!/usr/bin/env python3
"""
Retrieve ALL rendered images from Spark ComfyUI history.
Downloads to appropriate project folders based on filename prefix.
"""

import json
import requests
import os
from pathlib import Path

HOST = "http://100.112.87.8:8188"

OUTPUT_DIRS = {
    "FLUX2_TURBO": "/Users/zgbot/Desktop/projects/Sienna_Nomad_Project/RENDERED_OUTPUT",
    "Prompt_": "/Users/zgbot/Desktop/projects/Sienna_Nomad_Project/RENDERED_OUTPUT",
    "SPARK_TEST": "/Users/zgbot/Desktop/projects/Sienna_Nomad_Project/RENDERED_OUTPUT",
    "HACKATHON_": "/Users/zgbot/Desktop/projects/hackathon_vid/04_assets",
    "Flux2_dev": "/Users/zgbot/Desktop/projects/Sienna_Nomad_Project/RENDERED_OUTPUT",
}

def get_all_history():
    """Fetch complete history from Spark."""
    resp = requests.get(f"{HOST}/api/history", timeout=30)
    resp.raise_for_status()
    return resp.json()

def extract_images_from_history(history):
    """Find all image outputs in history."""
    images = []
    for pid, job in history.items():
        outputs = job.get("outputs", {})
        for node_id, node_out in outputs.items():
            for img in node_out.get("images", []):
                images.append({
                    "filename": img["filename"],
                    "subfolder": img.get("subfolder", ""),
                    "prompt_id": pid,
                })
    return images

def determine_output_dir(filename):
    """Route filename to correct project folder."""
    for prefix, path in OUTPUT_DIRS.items():
        if prefix in filename:
            return path
    return "/Users/zgbot/Desktop/projects/Sienna_Nomad_Project/RENDERED_OUTPUT"

def download_image(filename, subfolder, save_dir):
    """Download single image from Spark."""
    params = {"filename": filename, "type": "output", "subfolder": subfolder}
    resp = requests.get(f"{HOST}/view", params=params, timeout=30)
    resp.raise_for_status()
    
    save_path = Path(save_dir) / filename
    save_path.parent.mkdir(parents=True, exist_ok=True)
    with open(save_path, "wb") as f:
        f.write(resp.content)
    return save_path, len(resp.content)

def main():
    print("Fetching Spark history...")
    history = get_all_history()
    print(f"Found {len(history)} jobs in history")
    
    images = extract_images_from_history(history)
    print(f"Found {len(images)} images to download")
    
    if not images:
        print("No images found.")
        return
    
    downloaded = 0
    failed = 0
    total_bytes = 0
    
    for img in images:
        save_dir = determine_output_dir(img["filename"])
        try:
            path, size = download_image(img["filename"], img["subfolder"], save_dir)
            downloaded += 1
            total_bytes += size
            print(f"  ✅ {img['filename']} -> {path} ({size//1024}KB)")
        except Exception as e:
            failed += 1
            print(f"  ❌ {img['filename']}: {e}")
    
    print(f"\n{'='*60}")
    print(f"  Downloaded: {downloaded}/{len(images)}")
    print(f"  Failed: {failed}")
    print(f"  Total: {total_bytes//1024//1024:.1f} MB")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()
