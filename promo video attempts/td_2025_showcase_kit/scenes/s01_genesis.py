#!/usr/bin/env python3
"""
Scene 1: Genesis — Particle Birth + ComfyUI Image Emergence
=============================================================

TD 2025 Features:
- noisePOP: millions of GPU points born from noise
- forcePOP: attractor pulling particles to convergence
- renderSimpleTOP: direct POP rendering, no Geometry/Camera/Light needed
- Layer Mix TOP: per-layer glow and fade compositing

Visual: Particles condense from chaos → form a luminous sphere →
        ComfyUI hero image materializes within the cloud → fade to white
"""

import json
import subprocess
import sys
from pathlib import Path

TD_MCP_PORT = 40404
TD_MCP_URL = f"http://127.0.0.1:{TD_MCP_PORT}/mcp"
ASSETS = Path("/Users/zgbot/Desktop/forge_nps_v01/td_2025_showcase_kit/assets")


def td_call(method: str, params: dict = None):
    payload = {
        "jsonrpc": "2.0", "id": 1,
        "method": method, "params": params or {}
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
        print(f"[ERROR] {e}")
        return {}


def build():
    health = td_call("td_test_session")
    if not health:
        print("[FAIL] MCP not responding.")
        sys.exit(1)

    print("[s01] Building Genesis scene...")

    # ---------------------------------------------------------------
    # POP Particle System: Chaos → Convergence
    # ---------------------------------------------------------------
    td_call("td_execute_python", {"script": """
scene = op('/project1/s01_genesis')

# 1. noisePOP — generate 500k points in chaotic sphere
noise_pop = scene.create('noisePOP', 'birth_noise')
noise_pop.par.type = 'sparse'
noise_pop.par.period = 2.0
noise_pop.par.amplitude = 3.0
noise_pop.par.seed = 42
# noisePOP writes to 'P' (position) attribute by default
# In TD 2025, noisePOP generates point attributes directly on GPU

# 2. forcePOP — attractor pulling all points to center
attractor = scene.create('forcePOP', 'converge_force')
attractor.par.type = 'attract'
attractor.par.strength = 2.5
attractor.par.falloff = 1.0
attractor.par.fallofftype = 'linear'
attractor.inputConnectors[0].connect(noise_pop.outputConnectors[0])

# 3. Second forcePOP — slight spiral rotation as they converge
spiral = scene.create('forcePOP', 'spiral_force')
spiral.par.type = 'spiral'
spiral.par.strength = 0.8
spiral.par.axisx = 0
spiral.par.axisy = 1
spiral.par.axisz = 0
spiral.inputConnectors[0].connect(attractor.outputConnectors[0])

# 4. renderSimpleTOP — render POP directly, no geo/camera/light needed!
render = scene.create('renderSimpleTOP', 'particle_render')
render.par.pop = spiral.path
render.par.resolutionw = 1920
render.par.resolutionh = 1080
render.par.bgcolorr = 0.02
render.par.bgcolorg = 0.02
render.par.bgcolorb = 0.03
# renderSimpleTOP has built-in camera and light controls
render.par.cameratx = 0
render.par.cameraty = 0
render.par.cameratz = 5
render.par.pointsize = 0.015

result = {'pop_chain': 'built'}
"""})

    # ---------------------------------------------------------------
    # ComfyUI Hero Image — Materializes via Layer Mix
    # ---------------------------------------------------------------
    hero_path = ASSETS / "hero_genesis.png"
    td_call("td_execute_python", {"script": f"""
scene = op('/project1/s01_genesis')

# Load hero image
hero = scene.create('moviefileinTOP', 'hero_image')
hero.par.file = '{hero_path}'
hero.par.reload.pulse()

# Pre-multiply for transparency handling
hero_premul = scene.create('premultTOP', 'hero_premul')
hero_premul.inputConnectors[0].connect(hero.outputConnectors[0])

# Scale to fit with grace
hero_fit = scene.create('fitTOP', 'hero_fit')
hero_fit.par.resolutionw = 1920
hero_fit.par.resolutionh = 1080
hero_fit.par.fit = 'contain'
hero_fit.inputConnectors[0].connect(hero_premul.outputConnectors[0])

result = {{'hero': 'loaded'}}
"""})

    # ---------------------------------------------------------------
    # Layer Mix TOP — Per-layer control
    # ---------------------------------------------------------------
    td_call("td_execute_python", {"script": """
scene = op('/project1/s01_genesis')

# Layer Mix: particle layer + hero layer + glow layer
layer_mix = scene.create('layerMixTOP', 'genesis_comp')
layer_mix.par.resolutionw = 1920
layer_mix.par.resolutionh = 1080

# Connect inputs
particle_render = op('/project1/s01_genesis/particle_render')
hero_fit = op('/project1/s01_genesis/hero_fit')

layer_mix.inputConnectors[0].connect(particle_render.outputConnectors[0])
layer_mix.inputConnectors[1].connect(hero_fit.outputConnectors[0])

# Layer 0: particles — slight brightness boost
layer_mix.par.layer1opacity = 1.0
layer_mix.par.layer1brightness = 1.2

# Layer 1: hero image — starts invisible, fades in via expression
# User can keyframe layer2opacity from 0→1 over the 10s shot
layer_mix.par.layer2opacity = 0.0  # set to 0.0, animate manually or via CHOP
layer_mix.par.layer2composite = 'over'

# Layer 2: bloom/glow pass (we'll add via separate TOP)
result = {'layer_mix': 'configured'}
"""})

    # ---------------------------------------------------------------
    # Bloom / Glow Post-FX
    # ---------------------------------------------------------------
    td_call("td_execute_python", {"script": """
scene = op('/project1/s01_genesis')

# Extract bright areas
threshold = scene.create('thresholdTOP', 'bright_extract')
threshold.par.low = 0.6
threshold.inputConnectors[0].connect(op('/project1/s01_genesis/genesis_comp').outputConnectors[0])

# Blur bright areas
bloom_blur = scene.create('blurTOP', 'bloom_blur')
bloom_blur.par.size = 40
bloom_blur.par.sigma = 4.0
bloom_blur.inputConnectors[0].connect(threshold.outputConnectors[0])

# Layer Mix: composite bloom back
final_mix = scene.create('layerMixTOP', 'final_comp')
final_mix.par.resolutionw = 1920
final_mix.par.resolutionh = 1080
final_mix.inputConnectors[0].connect(op('/project1/s01_genesis/genesis_comp').outputConnectors[0])
final_mix.inputConnectors[1].connect(bloom_blur.outputConnectors[0])
final_mix.par.layer2opacity = 0.6
final_mix.par.layer2composite = 'add'

# Film grain
grain = scene.create('noiseTOP', 'film_grain')
grain.par.type = 'random'
grain.par.resolutionw = 1920
grain.par.resolutionh = 1080
grain.par.monochrome = True

grain_level = scene.create('levelTOP', 'grain_level')
grain_level.par.opacity = 0.03
grain_level.inputConnectors[0].connect(grain.outputConnectors[0])

grain_comp = scene.create('overTOP', 'grain_over')
grain_comp.inputConnectors[0].connect(final_mix.outputConnectors[0])
grain_comp.inputConnectors[1].connect(grain_level.outputConnectors[0])

# Connect to scene output
scene_out = op('/project1/s01_genesis/scene_render')
scene_out.inputConnectors[0].connect(grain_comp.outputConnectors[0])

result = {'post_fx': 'complete'}
"""})

    # ---------------------------------------------------------------
    # Animation CHOPs
    # ---------------------------------------------------------------
    td_call("td_execute_python", {"script": """
scene = op('/project1/s01_genesis')

# Timer for scene (10 seconds)
timer = scene.create('timerCHOP', 'scene_timer')
timer.par.length = 10.0
timer.par.unitmenu = 0

# LFO for breathing particle size
breathe = scene.create('lfoCHOP', 'breathe')
breathe.par.type = 'sine'
breathe.par.freq = 0.15
breathe.par.amp = 0.3
breathe.par.offset = 0.7

# Export to renderSimpleTOP point size
# In TD 2025: renderSimpleTOP.par.pointsize can be bound to CHOP channel

# Ramp for hero fade-in
hero_fade = scene.create('rampCHOP', 'hero_fade')
hero_fade.par.type = 'linear'
hero_fade.par.amp = 1.0
hero_fade.par.offset = 0.0
hero_fade.par.phase = 0.0
hero_fade.par.period = 10.0  # fades over 10s

result = {'animation': 'ready'}
"""})

    print("[s01] Genesis built. Set hero_fade phase to control image emergence.")


if __name__ == "__main__":
    build()
