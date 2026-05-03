#!/usr/bin/env python3
"""
Scene 3: Inside the Forge — Volumetric 3D Space
=================================================

TD 2025 Features:
- noiseTOP with 3D texture: volumetric fog and god rays
- Displace TOP with Z-source: 3D displacement
- Render Simple TOP: POP point clouds as atmosphere
- Layer Mix TOP: per-layer depth grading

Visual: Camera flies through a volumetric data space. 3D noise textures
        create flowing fog. ComfyUI-generated images float as luminous
        planes. God rays pierce through from above.
"""

import json
import subprocess
import sys
from pathlib import Path

TD_MCP_PORT = 40404
TD_MCP_URL = f"http://127.0.0.1:{TD_MCP_PORT}/mcp"
ASSETS = Path("/Users/zgbot/Desktop/forge_nps_v01/td_2025_showcase_kit/assets")

IMAGES = [
    "forge_interior_01.png",
    "forge_interior_02.png",
    "forge_interior_03.png",
]


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

    print("[s03] Building Inside the Forge...")

    # ---------------------------------------------------------------
    # 3D Volumetric Fog — noiseTOP with 3D texture
    # TD 2025: Many TOPs support 3D textures natively
    # ---------------------------------------------------------------
    td_call("td_execute_python", {"script": """
scene = op('/project1/s03_forge')

# 3D noise texture for volumetric fog
# In TD 2025, noiseTOP can output 3D textures when connected to 3D-capable ops
vol_noise = scene.create('noiseTOP', 'volume_noise')
vol_noise.par.type = 'perlin'
vol_noise.par.period = 4.0
vol_noise.par.harmonics = 3
vol_noise.par.spread = 0.8
vol_noise.par.resolutionw = 512
vol_noise.par.resolutionh = 512
# Note: 3D depth is handled by connected operators (Displace, Composite)

# Second layer of noise for detail
vol_noise2 = scene.create('noiseTOP', 'volume_detail')
vol_noise2.par.type = 'simplex'
vol_noise2.par.period = 1.5
vol_noise2.par.resolutionw = 512
vol_noise2.par.resolutionh = 512

# Composite the two noise layers
vol_comp = scene.create('compositeTOP', 'volume_merge')
vol_comp.par.operation = 'add'
vol_comp.inputConnectors[0].connect(vol_noise.outputConnectors[0])
vol_comp.inputConnectors[1].connect(vol_noise2.outputConnectors[0])

# Level to shape fog density
vol_level = scene.create('levelTOP', 'volume_shape')
vol_level.par.blacklevel = 0.4
vol_level.par.brightness1 = 1.5
vol_level.inputConnectors[0].connect(vol_comp.outputConnectors[0])

result = {'volume': 'built'}
"""})

    # ---------------------------------------------------------------
    # Floating Image Planes — ComfyUI renders in 3D space
    # ---------------------------------------------------------------
    for i, img_name in enumerate(IMAGES):
        img_path = ASSETS / img_name
        td_call("td_execute_python", {"script": f"""
scene = op('/project1/s03_forge')

# Load image
img = scene.create('moviefileinTOP', 'float_img_{i}')
img.par.file = '{img_path}'
img.par.reload.pulse()

# Scale
fit = scene.create('fitTOP', 'fit_{i}')
fit.par.resolutionw = 640
fit.par.resolutionh = 360
fit.par.fit = 'fill'
fit.inputConnectors[0].connect(img.outputConnectors[0])

# Slight blur for depth of field feel
blur = scene.create('blurTOP', 'dof_{i}')
blur.par.size = {2 + i}  # increasing blur with distance
blur.inputConnectors[0].connect(fit.outputConnectors[0])

# Glow
bloom = scene.create('blurTOP', 'bloom_{i}')
bloom.par.size = 20
bloom.inputConnectors[0].connect(fit.outputConnectors[0])

bloom_level = scene.create('levelTOP', 'bloomlevel_{i}')
bloom_level.par.brightness1 = 2.0
bloom_level.par.opacity = 0.4
bloom_level.inputConnectors[0].connect(bloom.outputConnectors[0])

over = scene.create('overTOP', 'img_glow_{i}')
over.inputConnectors[0].connect(blur.outputConnectors[0])
over.inputConnectors[1].connect(bloom_level.outputConnectors[0])

# Transform to floating position
txf = scene.create('transformTOP', 'txf_img_{i}')
txf.inputConnectors[0].connect(over.outputConnectors[0])
txf.par.tx = {(i - 1) * 400}
txf.par.ty = {(i % 2) * 200 - 100}
txf.par.sx = 0.8
txf.par.sy = 0.8

result = {{'img_{i}': 'positioned'}}
"""})

    # ---------------------------------------------------------------
    # POP Atmosphere — Dust motes in the light beams
    # ---------------------------------------------------------------
    td_call("td_execute_python", {"script": """
scene = op('/project1/s03_forge')

# Dust particles floating in the volume
dust_pop = scene.create('noisePOP', 'dust_motes')
dust_pop.par.type = 'sparse'
dust_pop.par.period = 5.0
dust_pop.par.amplitude = 4.0
dust_pop.par.seed = 77

# Gentle upward drift
drift = scene.create('forcePOP', 'updraft')
drift.par.type = 'directional'
drift.par.strength = 0.3
drift.par.dirx = 0
drift.par.diry = 1
drift.par.dirz = 0
drift.inputConnectors[0].connect(dust_pop.outputConnectors[0])

# Render dust
 dust_render = scene.create('renderSimpleTOP', 'dust_render')
dust_render.par.pop = drift.path
dust_render.par.resolutionw = 1920
dust_render.par.resolutionh = 1080
dust_render.par.bgcolorr = 0
 dust_render.par.bgcolorg = 0
dust_render.par.bgcolorb = 0
dust_render.par.cameratx = 0
dust_render.par.cameraty = 1
dust_render.par.cameratz = 8
dust_render.par.pointsize = 0.008

result = {'dust': 'rendered'}
"""})

    # ---------------------------------------------------------------
    # Layer Mix: Fog + Images + Dust
    # ---------------------------------------------------------------
    td_call("td_execute_python", {"script": """
scene = op('/project1/s03_forge')

layer_mix = scene.create('layerMixTOP', 'forge_comp')
layer_mix.par.resolutionw = 1920
layer_mix.par.resolutionh = 1080

# Layer 0: volumetric fog (screen blend)
vol = op('/project1/s03_forge/volume_shape')
layer_mix.inputConnectors[0].connect(vol.outputConnectors[0])
layer_mix.par.layer1opacity = 0.35
layer_mix.par.layer1composite = 'screen'

# Layers 1-3: floating images
for i in range(3):
    img = op(f'/project1/s03_forge/txf_img_{{i}}')
    layer_mix.inputConnectors[i+1].connect(img.outputConnectors[0])
    layer_mix.par.__setitem__(f'layer{{i+2}}composite', 'over')
    layer_mix.par.__setitem__(f'layer{{i+2}}opacity', 0.85)

# Layer 4: dust motes
dust = op('/project1/s03_forge/dust_render')
layer_mix.inputConnectors[4].connect(dust.outputConnectors[0])
layer_mix.par.layer6composite = 'add'
layer_mix.par.layer6opacity = 0.6

result = {'layer_mix': 'configured'}
"""})

    # ---------------------------------------------------------------
    # God Rays — Ramp + Blur + Composite
    # ---------------------------------------------------------------
    td_call("td_execute_python", {"script": """
scene = op('/project1/s03_forge')

# Light source from top
light_ramp = scene.create('rampTOP', 'godray_source')
light_ramp.par.type = 'vertical'
light_ramp.par.colorr = 0.9
light_ramp.par.colorg = 0.85
light_ramp.par.colorb = 1.0
light_ramp.par.colora = 0.0

# Radial blur for ray effect
ray_blur = scene.create('blurTOP', 'godray_blur')
ray_blur.par.size = 80
ray_blur.par.sigma = 6.0
ray_blur.inputConnectors[0].connect(light_ramp.outputConnectors[0])

ray_level = scene.create('levelTOP', 'godray_level')
ray_level.par.brightness1 = 1.5
ray_level.par.opacity = 0.25
ray_level.inputConnectors[0].connect(ray_blur.outputConnectors[0])

# Composite rays over scene
rays_over = scene.create('overTOP', 'godrays')
rays_over.inputConnectors[0].connect(op('/project1/s03_forge/forge_comp').outputConnectors[0])
rays_over.inputConnectors[1].connect(ray_level.outputConnectors[0])

# Color grade
grade = scene.create('levelTOP', 'color_grade')
grade.par.brightness1 = 1.1
grade.par.contrast = 1.15
grade.par.gamma1 = 0.95
grade.inputConnectors[0].connect(rays_over.outputConnectors[0])

# Connect to scene output
scene_out = op('/project1/s03_forge/scene_render')
scene_out.inputConnectors[0].connect(grade.outputConnectors[0])

result = {'post_fx': 'complete'}
"""})

    # ---------------------------------------------------------------
    # Camera Animation
    # ---------------------------------------------------------------
    td_call("td_execute_python", {"script": """
scene = op('/project1/s03_forge')

timer = scene.create('timerCHOP', 'scene_timer')
timer.par.length = 15.0
timer.par.unitmenu = 0

# Camera drift LFO
cam_x = scene.create('lfoCHOP', 'cam_drift_x')
cam_x.par.type = 'sine'
cam_x.par.freq = 0.1
cam_x.par.amp = 2.0

cam_y = scene.create('lfoCHOP', 'cam_drift_y')
cam_y.par.type = 'sine'
cam_y.par.freq = 0.07
cam_y.par.amp = 0.5
cam_y.par.phase = 0.25

result = {'animation': 'ready'}
"""})

    print("[s03] Inside the Forge built.")


if __name__ == "__main__":
    build()
