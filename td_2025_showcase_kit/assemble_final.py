#!/usr/bin/env python3
"""
Forge 2025 Showcase — Final Assembly Script
============================================

Assembles all recorded scene MOV files into the final MP4.

Prerequisites:
    - All scenes recorded to /tmp/forge_2025_showcase/
    - ffmpeg installed

Usage:
    python3 assemble_final.py
"""

import subprocess
from pathlib import Path

SCENE_DIR = Path("/tmp/forge_2025_showcase")
OUTPUT_DIR = Path("~/Desktop/FORGE_NPS_MEDIA")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

SCENES = [
    "s01_genesis.mov",
    "s02_pipeline.mov",
    "s03_forge.mov",
    "s04_audit.mov",
    "s05_memory.mov",
    "s06_output.mov",
]


def assemble():
    print("[Forge 2025] Assembling final video...\n")
    
    # Build concat list
    concat_file = SCENE_DIR / "concat_list.txt"
    with open(concat_file, "w") as f:
        for scene in SCENES:
            scene_path = SCENE_DIR / scene
            if scene_path.exists():
                f.write(f"file '{scene_path}'\n")
                print(f"  ✓ {scene}")
            else:
                print(f"  ✗ {scene} NOT FOUND — skipping")
    
    final_mov = SCENE_DIR / "forge_2025_showcase_final.mov"
    final_mp4 = OUTPUT_DIR / "forge_2025_showcase_final.mp4"
    
    # Concatenate with ffmpeg
    cmd_concat = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_file),
        "-c", "copy",
        str(final_mov)
    ]
    
    print(f"\n[1/2] Concatenating scenes...")
    result = subprocess.run(cmd_concat, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[ERROR] Concat failed:\n{result.stderr}")
        return
    
    # Convert to MP4 for sharing
    cmd_mp4 = [
        "ffmpeg", "-y",
        "-i", str(final_mov),
        "-c:v", "libx264",
        "-crf", "18",
        "-preset", "slow",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        str(final_mp4)
    ]
    
    print(f"[2/2] Converting to MP4...")
    result = subprocess.run(cmd_mp4, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[ERROR] MP4 conversion failed:\n{result.stderr}")
        return
    
    print(f"\n✅ DONE")
    print(f"ProRes master: {final_mov}")
    print(f"MP4 delivery:  {final_mp4}")


if __name__ == "__main__":
    assemble()
