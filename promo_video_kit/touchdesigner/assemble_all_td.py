#!/usr/bin/env python3
"""
Cinesmith — Master TouchDesigner Scene Builder
================================================

Builds ALL TouchDesigner scenes for the marketing video in sequence.
Run this after opening TouchDesigner with twozero.tox loaded.

Usage:
    python3 assemble_all_td.py

Scenes built:
  1. cinesmith_memory_graph_v2.toe      — Enhanced living memory graph
  2. cinesmith_pipeline_flow.toe        — 5-model orbital pipeline
  3. cinesmith_audit_gate.toe           — Dramatic PASS/FAIL portal
  4. cinesmith_command_center.toe       — HUD dashboard visualization
  5. cinesmith_provenance_web.toe       — 3D retry lineage web

Each scene outputs a .toe file and has a pre-wired MovieFileOut TOP
ready for recording.
"""

import subprocess
import sys
from pathlib import Path

SCENES = [
    ("Memory Graph V2", "build_memory_graph_v2.py", "/tmp/cinesmith_memory_graph_v2.toe", "/tmp/cinesmith_memory_graph_v2_output.mov"),
    ("Pipeline Flow", "build_pipeline_flow.py",
     "/tmp/cinesmith_pipeline_flow.toe", "/tmp/cinesmith_pipeline_flow_output.mov"),
    ("Audit Gate", "build_audit_gate.py",
     "/tmp/cinesmith_audit_gate.toe", "/tmp/cinesmith_audit_gate_output.mov"),
    ("Command Center", "build_command_center.py",
     "/tmp/cinesmith_command_center.toe", "/tmp/cinesmith_command_center_output.mov"),
    ("Provenance Web", "build_provenance_web.py",
     "/tmp/cinesmith_provenance_web.toe", "/tmp/cinesmith_provenance_web_output.mov"),
]

SCRIPT_DIR = Path("~/Desktop/cinesmith_v01/promo_video_kit/touchdesigner")


def main():
    print("=" * 70)
    print("  Cinesmith — Master TouchDesigner Scene Builder")
    print("=" * 70)
    print()
    print("This will build 5 complete TD scenes for your marketing video.")
    print("Make sure TouchDesigner is running with twozero.tox loaded.")
    print()
    input("Press ENTER to begin...")
    print()

    for i, (name, script, toe_path, mov_path) in enumerate(SCENES, 1):
        print(f"\n{'─' * 70}")
        print(f"  Scene {i}/5: {name}")
        print(f"{'─' * 70}")
        script_path = SCRIPT_DIR / script
        if not script_path.exists():
            print(f"[ERROR] Script not found: {script_path}")
            continue
        result = subprocess.run([sys.executable, str(script_path)], capture_output=False, text=True)
        if result.returncode == 0:
            print(f"\n[OK] {name} built successfully!")
            print(f"     .toe:  {toe_path}")
            print(f"     .mov:  {mov_path}")
        else:
            print(f"\n[WARN] {name} build returned code {result.returncode}")

    print("\n" + "=" * 70)
    print("  ALL SCENES BUILT")
    print("=" * 70)
    print("\nNEXT STEPS:")
    print("  1. Open each .toe file in TouchDesigner")
    print("  2. Press F1 for Perform Mode")
    print("  3. Click the 'recorder' TOP, set 'Record' to ON")
    print("  4. Record 15-30 seconds per scene")
    print("  5. Set 'Record' to OFF")
    print("\nThen run the assembly script to stitch everything together:")
    print("  cd ~/Desktop/cinesmith_v01/promo_video_kit/scripts")
    print("  ./assemble_promo.sh")


if __name__ == "__main__":
    main()
