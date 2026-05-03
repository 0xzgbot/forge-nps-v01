"""
Forge Cinema Kit — Master Network Builder
Run this in TouchDesigner's Textport to construct the entire project.

Usage:
    exec(open("/path/to/hackathon_cinema_kit/td_scripts/build_master_network.py").read())
"""

import os

KIT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
def clear_project():
    """Remove default /project1 contents but keep the COMP itself."""
    proj = op('/project1')
    for c in proj.children:
        c.destroy()

def ensure_comp(path, clone_from=None):
    """Create a COMP if it doesn't exist."""
    if op(path):
        return op(path)
    parent_path, name = path.rsplit('/', 1)
    parent = op(parent_path) if parent_path else root
    if clone_from and op(clone_from):
        return parent.create(op(clone_from).type, name)
    return parent.create('containerCOMP', name)

def ensure_op(path, optype):
    """Create an operator if it doesn't exist."""
    if op(path):
        return op(path)
    parent_path, name = path.rsplit('/', 1)
    parent = op(parent_path) if parent_path else root
    return parent.create(optype, name)

# ------------------------------------------------------------------
# Build Pipeline
# ------------------------------------------------------------------
clear_project()

proj = op('/project1')

# Master controller
ctrl = ensure_comp('/project1/master_ctrl')
ctrl.viewer = True

# Time-based scene switching
scene_index = ensure_op('/project1/master_ctrl/scene_index', 'countCHOP')
scene_index.par.reset.pulse()

# Constants for scene timing (in seconds at 30fps)
SCENES = [
    ("scene_spark",   0,   8),
    ("scene_mitosis", 8,  18),
    ("scene_forge",  18,  32),
    ("scene_social", 32,  48),
    ("scene_theater",48,  62),
    ("scene_infinite",62, 75),
]

# Build each scene container
for name, start, end in SCENES:
    comp = ensure_comp(f'/project1/{name}')
    comp.par.w = 300
    comp.par.h = 200
    # Scene timer
    timer = ensure_op(f'/project1/{name}/timer', 'timerCHOP')
    timer.par.length = (end - start) / 30.0  # in seconds
    timer.par.unitmenu = 0  # seconds
    # Scene render output
    render = ensure_op(f'/project1/{name}/render_out', 'renderTOP')
    render.par.resolutionw = 1920
    render.par.resolutionh = 1080

# Crossfader between scenes
xfd = ensure_op('/project1/crossfader', 'crossTOP')
xfd.par.resolutionw = 1920
xfd.par.resolutionh = 1080

# Final output
final = ensure_op('/project1/final_out', 'outTOP')
final.par.resolutionw = 1920
final.par.resolutionh = 1080

# Movie File Out for recording
movie = ensure_op('/project1/movie_out', 'moviefileoutTOP')
movie.par.resolutionw = 1920
movie.par.resolutionh = 1080
movie.par.type = 'h264'
movie.par.codec = 'h264'
movie.par.file = os.path.join(KIT_DIR, 'assets', 'render', 'forge_cinema_v2.mp4')
os.makedirs(os.path.dirname(movie.par.file), exist_ok=True)

# Wire them up (basic chain — each scene script will connect internals)
print("[Forge Cinema Kit] Master network skeleton built.")
print("[Forge Cinema Kit] Scenes:", [s[0] for s in SCENES])
print("[Forge Cinema Kit] Run individual scene scripts next.")
print("[Forge Cinema Kit] Kit dir:", KIT_DIR)
