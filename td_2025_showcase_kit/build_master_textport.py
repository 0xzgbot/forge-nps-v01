"""
Forge NPS — TD 2025 Showcase Kit Master Builder (Textport Method)
==================================================================

Run this directly in TouchDesigner's Textport (Alt+T):

    exec(open("~/Desktop/forge_nps_v01/td_2025_showcase_kit/build_master_textport.py").read())

No MCP required. Builds the same master network as build_master.py.
"""

import os
from pathlib import Path

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

ASSETS_DIR = Path("~/Desktop/forge_nps_v01/td_2025_showcase_kit/assets")
FORGE_MEDIA = Path(os.environ.get("FORGE_MEDIA_ROOT", "~/Desktop/FORGE_NPS_MEDIA"))

root = op('/project1')

# ------------------------------------------------------------------
# 1. Clean
# ------------------------------------------------------------------
print("[1/7] Cleaning project...")
for child in list(root.children):
    if child.valid:
        child.destroy()

# ------------------------------------------------------------------
# 2. Scene Containers
# ------------------------------------------------------------------
print("[2/7] Creating scene containers...")
for name, start, end, desc in SCENES:
    comp = root.create('containerCOMP', name)
    comp.par.w = 400
    comp.par.h = 300
    comp.par.bgcolorr = 0.05
    comp.par.bgcolorg = 0.05
    comp.par.bgcolorb = 0.05
    
    # Scene render output
    render = comp.create('renderSimpleTOP', 'scene_render')
    render.par.resolutionw = 1920
    render.par.resolutionh = 1080

# ------------------------------------------------------------------
# 3. Crossfader / Timer
# ------------------------------------------------------------------
print("[3/7] Creating crossfader and scene switching...")
master_timer = root.create('timerCHOP', 'master_timer')
master_timer.par.length = 90.0
master_timer.par.unitmenu = 0
master_timer.par.cycle = 0

scene_idx = root.create('countCHOP', 'scene_index')
scene_idx.par.reset.pulse()

cross_lfo = root.create('lfoCHOP', 'crossfade_lfo')
cross_lfo.par.type = 'sine'
cross_lfo.par.freq = 1.0 / 15.0
cross_lfo.par.amp = 0.5
cross_lfo.par.offset = 0.5

cross_top = root.create('choptoTOP', 'crossfade_val')
cross_top.par.chop = cross_lfo.path
cross_top.par.format = 'rgba32float'

# ------------------------------------------------------------------
# 4. Layer Mix
# ------------------------------------------------------------------
print("[4/7] Creating Layer Mix compositor...")
layer_mix = root.create('layerMixTOP', 'layer_compositor')
layer_mix.par.resolutionw = 1920
layer_mix.par.resolutionh = 1080

# ------------------------------------------------------------------
# 5. Final Output
# ------------------------------------------------------------------
print("[5/7] Creating final output chain...")
final_null = root.create('nullTOP', 'final_out')
final_null.par.resolutionw = 1920
final_null.par.resolutionh = 1080

win = root.create('windowCOMP', 'perform_window')
win.par.winop = final_null.path
win.par.winw = 1920
win.par.winh = 1080
win.par.winopen = False

movie = root.create('moviefileoutTOP', 'movie_out')
movie.par.type = 'movie'
movie.par.file = str(OUTPUT_DIR / 'forge_2025_showcase_master.mov')
movie.par.videocodec = 'h264'
movie.par.fps = 30
movie.par.resolutionw = 1920
movie.par.resolutionh = 1080
movie.inputConnectors[0].connect(final_null.outputConnectors[0])

# ------------------------------------------------------------------
# 6. Audio Reactive
# ------------------------------------------------------------------
print("[6/7] Creating audio-reactive input...")
audio_in = root.create('audiofileinCHOP', 'soundtrack')
audio_in.par.play = 1
audio_in.par.loop = 1

spectrum = root.create('audiospectrumCHOP', 'audio_spectrum')
spectrum.par.input = audio_in.path

math_gain = root.create('mathCHOP', 'audio_gain')
math_gain.par.input = spectrum.path
math_gain.par.gain = 10.0

audio_top = root.create('choptoTOP', 'audio_reactive')
audio_top.par.chop = math_gain.path
audio_top.par.format = 'rgba32float'
audio_top.par.resolutionw = 256
audio_top.par.resolutionh = 2

# ------------------------------------------------------------------
# 7. Save
# ------------------------------------------------------------------
print("[7/7] Saving master project...")
master_toe = OUTPUT_DIR / "forge_2025_master.toe"
project.save(str(master_toe))

print("\n✅ Master network built via Textport!")
print(f"Open: {master_toe}")
print("\nNext: Run scene scripts from the Textport:")
for name, _, _, desc in SCENES:
    print(f"    exec(open('scenes/{name}.py').read())")
