#!/usr/bin/env python3
"""
Scene 2: The Five Minds — Orbital Particle Streams
====================================================

TD 2025 Features:
- noisePOP: 5 separate point clouds for each agent
- forcePOP: orbital rotation + radial forces
- instancePOP: data packet geometry instanced per particle
- renderSimpleTOP: direct render of instanced POPs
- Layer Mix TOP: per-agent color grading and glow

Visual: 5 glowing orbital nodes with distinct colors. Millions of tiny
        data-packet particles stream along curved paths between nodes.
        Each node has a ComfyUI-generated portrait at its center.
"""

import json
import subprocess
import sys
from pathlib import Path

TD_MCP_PORT = 40404
TD_MCP_URL = f"http://127.0.0.1:{TD_MCP_PORT}/mcp"
ASSETS = Path("~/Desktop/forge_nps_v01/td_2025_showcase_kit/assets")

NODES = [
    {"name": "KIMI",    "color": (0.0, 0.8, 1.0),   "portrait": "portrait_kimi.png",    "angle": 0.0},
    {"name": "HERMES",  "color": (0.74, 0.0, 1.0),  "portrait": "portrait_hermes.png",  "angle": 1.256},
    {"name": "SPARK",   "color": (1.0, 0.6, 0.0),   "portrait": "portrait_spark.png",   "angle": 2.513},
    {"name": "VISION",  "color": (0.0, 1.0, 0.4),   "portrait": "portrait_vision.png",  "angle": 3.770},
    {"name": "MEMORY",  "color": (1.0, 0.9, 0.0),   "portrait": "portrait_memory.png",  "angle": 5.027},
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

    print("[s02] Building The Five Minds...")

    # ---------------------------------------------------------------
    # Master noisePOP — 1 million points in orbital disc
    # ---------------------------------------------------------------
    td_call("td_execute_python", {"script": """
scene = op('/project1/s02_pipeline')

# noisePOP generates the base particle field
base_pop = scene.create('noisePOP', 'base_particles')
base_pop.par.type = 'sparse'
base_pop.par.period = 1.0
base_pop.par.amplitude = 2.0
base_pop.par.seed = 123

# forcePOP: orbital rotation around Y axis
orbit = scene.create('forcePOP', 'orbit_force')
orbit.par.type = 'spiral'
orbit.par.strength = 1.2
orbit.par.axisx = 0
orbit.par.axisy = 1
orbit.par.axisz = 0
orbit.inputConnectors[0].connect(base_pop.outputConnectors[0])

# forcePOP: slight inward pull to keep disc shape
inward = scene.create('forcePOP', 'inward_force')
inward.par.type = 'attract'
inward.par.strength = 0.5
inward.par.falloff = 2.0
inward.inputConnectors[0].connect(orbit.outputConnectors[0])

result = {'orbital_pop': 'built'}
"""})

    # ---------------------------------------------------------------
    # Data Packet Streams — Small instanced geometry
    # ---------------------------------------------------------------
    td_call("td_execute_python", {"script": """
scene = op('/project1/s02_pipeline')

# Create a tiny cube SOP for instancing
packet_geo = scene.create('boxSOP', 'packet_geo')
packet_geo.par.size1 = 0.02
packet_geo.par.size2 = 0.02
packet_geo.par.size3 = 0.02

# instancePOP: instance the cube at every point
instancer = scene.create('instancePOP', 'packet_instances')
instancer.par.geo = packet_geo.path
instancer.inputConnectors[0].connect(op('/project1/s02_pipeline/inward_force').outputConnectors[0])

# Color the instances by velocity/position using noisePOP color attrib
color_pop = scene.create('noisePOP', 'color_noise')
color_pop.par.type = 'rgb'
color_pop.par.period = 3.0
color_pop.par.amplitude = 1.0
color_pop.par.attrib = 'color'
color_pop.inputConnectors[0].connect(instancer.outputConnectors[0])

result = {'instances': 'built'}
"""})

    # ---------------------------------------------------------------
    # Render Simple TOP
    # ---------------------------------------------------------------
    td_call("td_execute_python", {"script": """
scene = op('/project1/s02_pipeline')

render = scene.create('renderSimpleTOP', 'pipeline_render')
render.par.pop = op('/project1/s02_pipeline/color_noise').path
render.par.resolutionw = 1920
render.par.resolutionh = 1080
render.par.bgcolorr = 0.01
render.par.bgcolorg = 0.01
render.par.bgcolorb = 0.02
render.par.cameratx = 0
render.par.cameraty = 2
render.par.cameratz = 6
render.par.cameraroty = 15
render.par.pointsize = 0.01

# Enable wireframe for tech aesthetic
# render.par.wireframe = 1  # if available

result = {'render': 'configured'}
"""})

    # ---------------------------------------------------------------
    # Agent Portraits — Floating images at orbital positions
    # ---------------------------------------------------------------
    for node in NODES:
        portrait_path = ASSETS / node["portrait"]
        td_call("td_execute_python", {"script": f"""
scene = op('/project1/s02_pipeline')

# Load portrait
img = scene.create('moviefileinTOP', 'portrait_{node['name'].lower()}')
img.par.file = '{portrait_path}'
img.par.reload.pulse()

# Fit to square
fit = scene.create('fitTOP', 'fit_{node['name'].lower()}')
fit.par.resolutionw = 256
fit.par.resolutionh = 256
fit.par.fit = 'fill'
fit.inputConnectors[0].connect(img.outputConnectors[0])

# Add glow
blur = scene.create('blurTOP', 'glow_{node['name'].lower()}')
blur.par.size = 15
blur.inputConnectors[0].connect(fit.outputConnectors[0])

glow_level = scene.create('levelTOP', 'glowlevel_{node['name'].lower()}')
glow_level.par.brightness1 = 2.0
glow_level.par.opacity = 0.5
glow_level.inputConnectors[0].connect(blur.outputConnectors[0])

over = scene.create('overTOP', 'portrait_glow_{node['name'].lower()}')
over.inputConnectors[0].connect(fit.outputConnectors[0])
over.inputConnectors[1].connect(glow_level.outputConnectors[0])

result = {{'portrait_{node['name']}': 'loaded'}}
"""})

    # ---------------------------------------------------------------
    # Layer Mix: Pipeline render + 5 portrait layers
    # ---------------------------------------------------------------
    td_call("td_execute_python", {"script": """
scene = op('/project1/s02_pipeline')

layer_mix = scene.create('layerMixTOP', 'pipeline_comp')
layer_mix.par.resolutionw = 1920
layer_mix.par.resolutionh = 1080

# Layer 0: particle pipeline
pipeline_render = op('/project1/s02_pipeline/pipeline_render')
layer_mix.inputConnectors[0].connect(pipeline_render.outputConnectors[0])
layer_mix.par.layer1opacity = 1.0
layer_mix.par.layer1brightness = 1.1

# Layers 1-5: portraits (positioned via transformTOP before Layer Mix)
# We'll use transformTOPs to position each portrait in 2D screen space
# corresponding to their orbital angle

result = {'layer_mix': 'started'}
"""})

    # Position portraits in 2D using transformTOPs
    for i, node in enumerate(NODES):
        # Calculate screen position from orbital angle
        angle = node["angle"]
        radius = 300  # pixels from center
        cx, cy = 960, 540
        tx = cx + radius * __import__('math').cos(angle) - 128  # center the 256px image
        ty = cy + radius * __import__('math').sin(angle) - 128

        td_call("td_execute_python", {"script": f"""
scene = op('/project1/s02_pipeline')

# Transform to orbital position
txf = scene.create('transformTOP', 'txf_{node['name'].lower()}')
txf.inputConnectors[0].connect(op('/project1/s02_pipeline/portrait_glow_{node['name'].lower()}').outputConnectors[0])
txf.par.tx = {tx:.0f}
txf.par.ty = {ty:.0f}

# Connect to Layer Mix
layer_mix = op('/project1/s02_pipeline/pipeline_comp')
layer_mix.inputConnectors[{i+1}].connect(txf.outputConnectors[0])

# Set layer to 'Over' composite
layer_mix.par.__setitem__('layer{i+2}composite', 'over')
layer_mix.par.__setitem__('layer{i+2}opacity', 0.9)

result = {{'{node['name']}_position': 'set'}}
"""})

    # ---------------------------------------------------------------
    # Final Post-FX
    # ---------------------------------------------------------------
    td_call("td_execute_python", {"script": """
scene = op('/project1/s02_pipeline')

# Chromatic aberration at edges via Displace TOP
# TD 2025: Displace TOP has Aspect Correct and 3D texture support

ca_noise = scene.create('noiseTOP', 'ca_noise')
ca_noise.par.type = 'random'
ca_noise.par.resolutionw = 64
ca_noise.par.resolutionh = 64

ca_displace = scene.create('displaceTOP', 'ca_displace')
ca_displace.inputConnectors[0].connect(op('/project1/s02_pipeline/pipeline_comp').outputConnectors[0])
ca_displace.inputConnectors[1].connect(ca_noise.outputConnectors[0])
ca_displace.par.uvweight = 0.005
ca_displace.par.aspectcorrect = 1  # TD 2025 feature

# Vignette
vig = scene.create('rampTOP', 'vignette')
vig.par.type = 'radial'
vig.par.colorr = 0
vig.par.colorg = 0
vig.par.colorb = 0
vig.par.colora = 0.6

vig_comp = scene.create('overTOP', 'vig_over')
vig_comp.inputConnectors[0].connect(ca_displace.outputConnectors[0])
vig_comp.inputConnectors[1].connect(vig.outputConnectors[0])
vig_comp.par.operation = 'multiply'

# Connect to scene output
scene_out = op('/project1/s02_pipeline/scene_render')
scene_out.inputConnectors[0].connect(vig_comp.outputConnectors[0])

result = {'post_fx': 'complete'}
"""})

    # ---------------------------------------------------------------
    # Animation
    # ---------------------------------------------------------------
    td_call("td_execute_python", {"script": """
scene = op('/project1/s02_pipeline')

# Timer
timer = scene.create('timerCHOP', 'scene_timer')
timer.par.length = 15.0
timer.par.unitmenu = 0

# Audio-reactive pulse on packet size
pulse = scene.create('lfoCHOP', 'pulse')
pulse.par.type = 'square'
pulse.par.freq = 2.0
pulse.par.amp = 0.5
pulse.par.offset = 0.5

result = {'animation': 'ready'}
"""})

    print("[s02] The Five Minds built.")


if __name__ == "__main__":
    build()
