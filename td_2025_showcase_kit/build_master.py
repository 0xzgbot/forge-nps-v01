#!/usr/bin/env python3
"""
Forge NPS — TD 2025 Showcase Kit Master Builder (MCP Method)
=============================================================

Builds the master network skeleton with 6 scene containers, crossfader,
timer-driven scene switching, and Movie File Out for recording.

Usage:
    1. Open TouchDesigner, drag in twozero.tox, enable MCP
    2. python3 build_master.py
    3. Open generated .toe files, record each scene
"""

import json
import os
import subprocess
import sys
from pathlib import Path

TD_MCP_PORT = 40404
TD_MCP_URL = f"http://127.0.0.1:{TD_MCP_PORT}/mcp"
OUTPUT_DIR = Path("/tmp/forge_2025_showcase")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

SCENES = [
    ("s01_genesis",     0,   10, "Genesis — Particle Birth"),
    ("s02_pipeline",   10,   25, "The Five Minds — Orbital Streams"),
    ("s03_forge",      25,   40, "Inside the Forge — Volumetric"),
    ("s04_audit",      40,   55, "The Audit Gate — Force Portal"),
    ("s05_memory",     55,   70, "Memory Palace — Crystalline"),
    ("s06_output",     70,   90, "The Output — Convergence"),
]

ASSETS_DIR = Path("/Users/zgbot/Desktop/forge_nps_v01/td_2025_showcase_kit/assets")
FORGE_MEDIA = Path(os.environ.get("FORGE_MEDIA_ROOT", "/Users/zgbot/Desktop/FORGE_NPS_MEDIA"))


def td_call(method: str, params: dict = None):
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params or {}
    }
    cmd = [
        "curl", "-s", "-X", "POST", TD_MCP_URL,
        "-H", "Content-Type: application/json",
        "-d", json.dumps(payload)
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return json.loads(result.stdout) if result.stdout else {}
    except Exception as e:
        print(f"[ERROR] MCP call failed: {e}")
        return {}


def build():
    health = td_call("td_test_session")
    if not health:
        print("[FAIL] TD MCP not responding. Open TD + twozero.tox first.")
        sys.exit(1)

    print("[1/7] Cleaning project...")
    td_call("td_execute_python", {
        "script": """
root = op('/project1')
for child in list(root.children):
    if child.valid: child.destroy()
result = {'cleaned': True}
"""
    })

    print("[2/7] Creating scene containers...")
    for name, start, end, desc in SCENES:
        td_call("td_execute_python", {
            "script": f"""
root = op('/project1')
comp = root.create('containerCOMP', '{name}')
comp.par.w = 400
comp.par.h = 300
comp.par.bgcolorr = 0.05
comp.par.bgcolorg = 0.05
comp.par.bgcolorb = 0.05

# Scene render output inside container
render = comp.create('renderSimpleTOP', 'scene_render')
render.par.resolutionw = 1920
render.par.resolutionh = 1080

# Or use standard renderTOP for more control
# render = comp.create('renderTOP', 'scene_render')
# render.par.resolutionw = 1920
# render.par.resolutionh = 1080

result = {{'{name}': 'created'}}
"""
        })

    print("[3/7] Creating crossfader and scene switching...")
    td_call("td_execute_python", {
        "script": """
root = op('/project1')

# Timer CHOP drives scene progression
master_timer = root.create('timerCHOP', 'master_timer')
master_timer.par.length = 90.0  # 90 seconds total
master_timer.par.unitmenu = 0   # seconds
master_timer.par.cycle = 0      # don't loop automatically

# Scene index counter
scene_idx = root.create('countCHOP', 'scene_index')
scene_idx.par.reset.pulse()

# LFO for smooth crossfade modulation
cross_lfo = root.create('lfoCHOP', 'crossfade_lfo')
cross_lfo.par.type = 'sine'
cross_lfo.par.freq = 1.0 / 15.0  # 15s per scene transition
cross_lfo.par.amp = 0.5
cross_lfo.par.offset = 0.5

# CHOP to TOP for crossfade value
cross_top = root.create('choptoTOP', 'crossfade_val')
cross_top.par.chop = cross_lfo.path
cross_top.par.format = 'rgba32float'

result = {'crossfader': 'created'}
"""
    })

    print("[4/7] Creating Layer Mix compositor...")
    td_call("td_execute_python", {
        "script": """
root = op('/project1')

# Layer Mix TOP for advanced per-layer compositing
layer_mix = root.create('layerMixTOP', 'layer_compositor')
layer_mix.par.resolutionw = 1920
layer_mix.par.resolutionh = 1080

# We'll wire scene outputs into this in the scene scripts
# Layer Mix allows per-layer: crop, scale, rotation, opacity,
# brightness, levels, composite operation

result = {'layer_mix': 'created'}
"""
    })

    print("[5/7] Creating final output chain...")
    td_call("td_execute_python", {
        "script": f"""
root = op('/project1')

# Final output null
final_null = root.create('nullTOP', 'final_out')
final_null.par.resolutionw = 1920
final_null.par.resolutionh = 1080

# Optional: Color space transform if working in linear
# color_xform = root.create('colorspaceTOP', 'color_xform')
# color_xform.par.inputcolorspace = 'linear'
# color_xform.par.outputcolorspace = 'srgb'

# Window COMP for preview
win = root.create('windowCOMP', 'perform_window')
win.par.winop = final_null.path
win.par.winw = 1920
win.par.winh = 1080
win.par.winopen = False

# Movie File Out TOP — TD 2025 supports AV1, VVC/H.266, AAC, Opus
movie = root.create('moviefileoutTOP', 'movie_out')
movie.par.type = 'movie'
movie.par.file = '{OUTPUT_DIR}/forge_2025_showcase_master.mov'
movie.par.videocodec = 'h264'  # or 'prores', 'av1', 'h265'
movie.par.fps = 30
movie.par.resolutionw = 1920
movie.par.resolutionh = 1080
movie.inputConnectors[0].connect(final_null.outputConnectors[0])

result = {{'output': 'ready'}}
"""
    })

    print("[6/7] Creating audio-reactive input...")
    td_call("td_execute_python", {
        "script": """
root = op('/project1')

# Audio input (user can connect their soundtrack)
audio_in = root.create('audiofileinCHOP', 'soundtrack')
audio_in.par.play = 1
audio_in.par.loop = 1
# Leave file empty for now — user sets their audio

# Audio spectrum analysis
spectrum = root.create('audiospectrumCHOP', 'audio_spectrum')
spectrum.par.input = audio_in.path

# Math CHOP to boost levels
math_gain = root.create('mathCHOP', 'audio_gain')
math_gain.par.input = spectrum.path
math_gain.par.gain = 10.0

# CHOP to TOP for shader/audio-reactive use
audio_top = root.create('choptoTOP', 'audio_reactive')
audio_top.par.chop = math_gain.path
audio_top.par.format = 'rgba32float'
audio_top.par.resolutionw = 256
audio_top.par.resolutionh = 2

result = {'audio': 'ready'}
"""
    })

    print("[7/7] Saving master project...")
    master_toe = OUTPUT_DIR / "forge_2025_master.toe"
    td_call("td_execute_python", {
        "script": f"""
project.save('{master_toe}')
result = {{'saved_to': '{master_toe}'}}
"""
    })

    print("\n✅ Master network built!")
    print(f"Open: {master_toe}")
    print("\nNext steps:")
    print("  1. Run individual scene scripts to populate each container")
    print("  2. Place ComfyUI-generated media in assets/")
    print("  3. Press F1 and record via movie_out")
    print("\nScene scripts to run:")
    for name, _, _, desc in SCENES:
        print(f"    python3 scenes/{name}.py")


if __name__ == "__main__":
    build()
