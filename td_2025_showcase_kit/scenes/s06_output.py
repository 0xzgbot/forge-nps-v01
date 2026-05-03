#!/usr/bin/env python3
"""
Scene 6: The Output — Particle Convergence + Video Playback
=============================================================

TD 2025 Features:
- forcePOP: explosive radial force for particle convergence/detonation
- moviefileinTOP: load ComfyUI-generated final video
- Layer Mix TOP: title card compositing with per-layer animation
- Render Simple TOP: particle screen made of millions of points

Visual: All particles from previous scenes converge into a single point.
        The point explodes outward, revealing a massive screen made of
        particles. The ComfyUI-generated final video plays on the screen.
        Tagline fades in. The Forge NPS logo crystallizes from particles.
"""

import json
import subprocess
import sys
from pathlib import Path

TD_MCP_PORT = 40404
TD_MCP_URL = f"http://127.0.0.1:{TD_MCP_PORT}/mcp"
ASSETS = Path("~/Desktop/forge_nps_v01/td_2025_showcase_kit/assets")


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

    print("[s06] Building The Output...")

    # ---------------------------------------------------------------
    # Particle Convergence — Attractor to center
    # ---------------------------------------------------------------
    td_call("td_execute_python", {"script": """
scene = op('/project1/s06_output')

# noisePOP: particles start scattered
chaos = scene.create('noisePOP', 'chaos_pop')
chaos.par.type = 'sparse'
chaos.par.period = 3.0
chaos.par.amplitude = 5.0
chaos.par.seed = 777

# forcePOP: strong attractor to center (convergence phase)
attract = scene.create('forcePOP', 'converge')
attract.par.type = 'attract'
attract.par.strength = 5.0
attract.par.falloff = 3.0
attract.par.fallofftype = 'gaussian'
attract.inputConnectors[0].connect(chaos.outputConnectors[0])

result = {'convergence': 'built'}
"""})

    # ---------------------------------------------------------------
    # Explosion Phase — Radial force outward
    # ---------------------------------------------------------------
    td_call("td_execute_python", {"script": """
scene = op('/project1/s06_output')

# forcePOP: explosive radial outward force
explode = scene.create('forcePOP', 'explosion')
explode.par.type = 'radial'
explode.par.strength = 8.0
explode.par.falloff = 0.3
explode.par.fallofftype = 'linear'
explode.inputConnectors[0].connect(op('/project1/s06_output/converge').outputConnectors[0])

# Second force: noise for chaotic spread
chaos_force = scene.create('forcePOP', 'chaos_spread')
chaos_force.par.type = 'noise'
chaos_force.par.strength = 2.0
chaos_force.inputConnectors[0].connect(explode.outputConnectors[0])

result = {'explosion': 'built'}
"""})

    # ---------------------------------------------------------------
    # Particle Screen — Points form a flat plane for video projection
    # ---------------------------------------------------------------
    td_call("td_execute_python", {"script": """
scene = op('/project1/s06_output')

# Grid POP for screen formation
screen_pop = scene.create('noisePOP', 'screen_grid')
screen_pop.par.type = 'grid'
screen_pop.par.period = 1.0
screen_pop.par.amplitude = 2.0

# forcePOP: planar force to flatten into screen
flatten = scene.create('forcePOP', 'screen_flatten')
flatten.par.type = 'planar'
flatten.par.strength = 3.0
flatten.par.dirx = 0
flatten.par.diry = 0
flatten.par.dirz = 1
flatten.inputConnectors[0].connect(screen_pop.outputConnectors[0])

# Color by UV for video mapping
uv_color = scene.create('noisePOP', 'screen_uv')
uv_color.par.type = 'rgb'
uv_color.par.period = 1.0
uv_color.par.attrib = 'color'
uv_color.inputConnectors[0].connect(flatten.outputConnectors[0])

result = {'screen': 'built'}
"""})

    # ---------------------------------------------------------------
    # Render Particles
    # ---------------------------------------------------------------
    td_call("td_execute_python", {"script": """
scene = op('/project1/s06_output')

# Render explosion particles
explosion_render = scene.create('renderSimpleTOP', 'explosion_render')
explosion_render.par.pop = op('/project1/s06_output/chaos_spread').path
explosion_render.par.resolutionw = 1920
explosion_render.par.resolutionh = 1080
explosion_render.par.bgcolorr = 0.01
explosion_render.par.bgcolorg = 0.01
explosion_render.par.bgcolorb = 0.02
explosion_render.par.cameratx = 0
explosion_render.par.cameraty = 0
explosion_render.par.cameratz = 6
explosion_render.par.pointsize = 0.012

# Render screen particles
screen_render = scene.create('renderSimpleTOP', 'screen_render')
screen_render.par.pop = op('/project1/s06_output/screen_uv').path
screen_render.par.resolutionw = 1920
screen_render.par.resolutionh = 1080
screen_render.par.bgcolorr = 0
screen_render.par.bgcolorg = 0
screen_render.par.bgcolorb = 0
screen_render.par.cameratx = 0
screen_render.par.cameraty = 0
screen_render.par.cameratz = 4
screen_render.par.pointsize = 0.008

result = {'render': 'configured'}
"""})

    # ---------------------------------------------------------------
    # Final Video — ComfyUI-generated output
    # ---------------------------------------------------------------
    td_call("td_execute_python", {"script": f"""
scene = op('/project1/s06_output')

video = scene.create('moviefileinTOP', 'final_video')
video.par.file = '{ASSETS / "final_output_video.mov"}'
video.par.play = 1
video.par.loop = 0  # play once

# Scale to fill
video_fit = scene.create('fitTOP', 'video_fit')
video_fit.par.resolutionw = 1920
video_fit.par.resolutionh = 1080
video_fit.par.fit = 'fill'
video_fit.inputConnectors[0].connect(video.outputConnectors[0])

result = {{'video': 'loaded'}}
"""})

    # ---------------------------------------------------------------
    # Tagline — Geo Text COMP with Face Camera
    # ---------------------------------------------------------------
    td_call("td_execute_python", {"script": """
scene = op('/project1/s06_output')

# Main tagline
tagline = scene.create('geoTextCOMP', 'tagline')
tagline.par.text = 'FORGE NPS'
tagline.par.fontsize = 0.4
tagline.par.colorr = 1.0
tagline.par.colorg = 1.0
tagline.par.colorb = 1.0
tagline.par.facecamera = 1
tagline.par.sizeaffectedbyfov = 1
tagline.par.lifttowardscamera = 0.3
tagline.par.tx = 0
tagline.par.ty = 0.5
tagline.par.tz = 2

# Subtitle
subtitle = scene.create('geoTextCOMP', 'subtitle')
subtitle.par.text = 'Every shot, accounted for.'
subtitle.par.fontsize = 0.15
subtitle.par.colorr = 0.8
subtitle.par.colorg = 0.8
subtitle.par.colorb = 0.9
subtitle.par.facecamera = 1
subtitle.par.sizeaffectedbyfov = 1
subtitle.par.lifttowardscamera = 0.2
subtitle.par.tx = 0
subtitle.par.ty = -0.3
subtitle.par.tz = 2

result = {'text': 'created'}
"""})

    # ---------------------------------------------------------------
    # Layer Mix: Explosion + Video + Screen + Text
    # ---------------------------------------------------------------
    td_call("td_execute_python", {"script": """
scene = op('/project1/s06_output')

layer_mix = scene.create('layerMixTOP', 'output_comp')
layer_mix.par.resolutionw = 1920
layer_mix.par.resolutionh = 1080

# Layer 0: explosion particles (add)
explosion = op('/project1/s06_output/explosion_render')
layer_mix.inputConnectors[0].connect(explosion.outputConnectors[0])
layer_mix.par.layer1composite = 'add'
layer_mix.par.layer1opacity = 0.8

# Layer 1: video
video = op('/project1/s06_output/video_fit')
layer_mix.inputConnectors[1].connect(video.outputConnectors[0])
layer_mix.par.layer2composite = 'over'
layer_mix.par.layer2opacity = 1.0

# Layer 2: screen particles over video
screen = op('/project1/s06_output/screen_render')
layer_mix.inputConnectors[2].connect(screen.outputConnectors[0])
layer_mix.par.layer3composite = 'add'
layer_mix.par.layer3opacity = 0.4

result = {'layer_mix': 'configured'}
"""})

    # ---------------------------------------------------------------
    # Final Post-FX + Output
    # ---------------------------------------------------------------
    td_call("td_execute_python", {"script": """
scene = op('/project1/s06_output')

# Bloom on everything
bloom = scene.create('blurTOP', 'final_bloom')
bloom.par.size = 25
bloom.inputConnectors[0].connect(op('/project1/s06_output/output_comp').outputConnectors[0])

bloom_level = scene.create('levelTOP', 'final_bloom_level')
bloom_level.par.brightness1 = 2.0
bloom_level.par.opacity = 0.35
bloom_level.inputConnectors[0].connect(bloom.outputConnectors[0])

bloom_over = scene.create('overTOP', 'final_bloom_over')
bloom_over.inputConnectors[0].connect(op('/project1/s06_output/output_comp').outputConnectors[0])
bloom_over.inputConnectors[1].connect(bloom_level.outputConnectors[0])

# Final grade
grade = scene.create('levelTOP', 'final_grade')
grade.par.brightness1 = 1.05
grade.par.contrast = 1.1
grade.par.saturation = 1.15
grade.inputConnectors[0].connect(bloom_over.outputConnectors[0])

# Connect to scene output
scene_out = op('/project1/s06_output/scene_render')
scene_out.inputConnectors[0].connect(grade.outputConnectors[0])

result = {'post_fx': 'complete'}
"""})

    # ---------------------------------------------------------------
    # Animation Timeline
    # ---------------------------------------------------------------
    td_call("td_execute_python", {"script": """
scene = op('/project1/s06_output')

timer = scene.create('timerCHOP', 'scene_timer')
timer.par.length = 20.0
timer.par.unitmenu = 0

# Master ramp for scene phases
phase = scene.create('rampCHOP', 'scene_phase')
phase.par.type = 'linear'
phase.par.amp = 1.0
phase.par.period = 20.0

# Convergence: 0-5s
# Explosion: 5-8s
# Video reveal: 8-18s
# Logo: 15-20s

result = {'animation': 'ready'}
"""})

    print("[s06] The Output built.")


if __name__ == "__main__":
    build()
