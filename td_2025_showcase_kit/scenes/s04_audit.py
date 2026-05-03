#!/usr/bin/env python3
"""
Scene 4: The Audit Gate — Force POP Portal
=============================================

TD 2025 Features:
- forcePOP: radial forces for portal effect, planar for rejection
- convertPOP: edge conversion for line rendering
- renderSimpleTOP: direct line/point rendering
- Feedback TOP: particle trail persistence

Visual: Particles approach from left toward a massive hexagonal portal.
        As they pass through, they flash green (PASS) or red (FAIL).
        Failed particles are caught in a rejection force field and loop back.
        Successful particles surge forward in a brilliant green stream.
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

    print("[s04] Building The Audit Gate...")

    # ---------------------------------------------------------------
    # Approaching Particles — Flow from left to portal
    # ---------------------------------------------------------------
    td_call("td_execute_python", {"script": """
scene = op('/project1/s04_audit')

# noisePOP: particles born on left side
source_pop = scene.create('noisePOP', 'approach_pop')
source_pop.par.type = 'grid'
source_pop.par.period = 1.0
source_pop.par.amplitude = 1.0
source_pop.par.seed = 88

# forcePOP: directional push toward portal (rightward)
push = scene.create('forcePOP', 'push_force')
push.par.type = 'directional'
push.par.strength = 1.5
push.par.dirx = 1
push.par.diry = 0
push.par.dirz = 0
push.inputConnectors[0].connect(source_pop.outputConnectors[0])

# forcePOP: slight spread so they don't all converge on same point
spread = scene.create('forcePOP', 'spread_force')
spread.par.type = 'noise'
spread.par.strength = 0.4
spread.inputConnectors[0].connect(push.outputConnectors[0])

result = {'approach': 'built'}
"""})

    # ---------------------------------------------------------------
    # Portal Ring — Radial force at center
    # ---------------------------------------------------------------
    td_call("td_execute_python", {"script": """
scene = op('/project1/s04_audit')

# Attractor at portal center to pull particles through
portal_pull = scene.create('forcePOP', 'portal_pull')
portal_pull.par.type = 'attract'
portal_pull.par.strength = 3.0
portal_pull.par.falloff = 0.5
portal_pull.par.fallofftype = 'gaussian'
portal_pull.inputConnectors[0].connect(op('/project1/s04_audit/spread_force').outputConnectors[0])

# Radial spin once inside portal
portal_spin = scene.create('forcePOP', 'portal_spin')
portal_spin.par.type = 'spiral'
portal_spin.par.strength = 2.0
portal_spin.par.axisx = 0
portal_spin.par.axisy = 0
portal_spin.par.axisz = 1
portal_spin.inputConnectors[0].connect(portal_pull.outputConnectors[0])

result = {'portal': 'built'}
"""})

    # ---------------------------------------------------------------
    # Convert to Lines + Render
    # TD 2025: convertPOP has 'To Unique Lines' mode
    # ---------------------------------------------------------------
    td_call("td_execute_python", {"script": """
scene = op('/project1/s04_audit')

# convertPOP: convert point connections to unique lines
line_pop = scene.create('convertPOP', 'lines')
line_pop.par.type = 'touniquelines'
line_pop.inputConnectors[0].connect(op('/project1/s04_audit/portal_spin').outputConnectors[0])

# Color by velocity/position for pass/fail effect
color_pop = scene.create('noisePOP', 'audit_color')
color_pop.par.type = 'rgb'
color_pop.par.period = 1.0
color_pop.par.attrib = 'color'
color_pop.inputConnectors[0].connect(line_pop.outputConnectors[0])

# renderSimpleTOP with line rendering
render = scene.create('renderSimpleTOP', 'audit_render')
render.par.pop = color_pop.path
render.par.resolutionw = 1920
render.par.resolutionh = 1080
render.par.bgcolorr = 0.01
render.par.bgcolorg = 0.01
render.par.bgcolorb = 0.02
render.par.cameratx = 0
render.par.cameraty = 0
render.par.cameratz = 6
render.par.pointsize = 0.02
# Wireframe mode for line aesthetic

result = {'lines': 'rendered'}
"""})

    # ---------------------------------------------------------------
    # PASS / FAIL Typography
    # ---------------------------------------------------------------
    td_call("td_execute_python", {"script": f"""
scene = op('/project1/s04_audit')

# PASS image
pass_img = scene.create('moviefileinTOP', 'pass_text')
pass_img.par.file = '{ASSETS / "audit_pass.png"}'
pass_img.par.reload.pulse()

pass_fit = scene.create('fitTOP', 'pass_fit')
pass_fit.par.resolutionw = 400
pass_fit.par.resolutionh = 200
pass_fit.inputConnectors[0].connect(pass_img.outputConnectors[0])

pass_glow = scene.create('blurTOP', 'pass_glow')
pass_glow.par.size = 25
pass_glow.inputConnectors[0].connect(pass_fit.outputConnectors[0])

pass_level = scene.create('levelTOP', 'pass_level')
pass_level.par.brightness1 = 2.0
pass_level.par.opacity = 0.6
pass_level.inputConnectors[0].connect(pass_glow.outputConnectors[0])

pass_over = scene.create('overTOP', 'pass_comp')
pass_over.inputConnectors[0].connect(pass_fit.outputConnectors[0])
pass_over.inputConnectors[1].connect(pass_level.outputConnectors[0])

# FAIL image
fail_img = scene.create('moviefileinTOP', 'fail_text')
fail_img.par.file = '{ASSETS / "audit_fail.png"}'
fail_img.par.reload.pulse()

fail_fit = scene.create('fitTOP', 'fail_fit')
fail_fit.par.resolutionw = 400
fail_fit.par.resolutionh = 200
fail_fit.inputConnectors[0].connect(fail_img.outputConnectors[0])

fail_glow = scene.create('blurTOP', 'fail_glow')
fail_glow.par.size = 25
fail_glow.inputConnectors[0].connect(fail_fit.outputConnectors[0])

fail_level = scene.create('levelTOP', 'fail_level')
fail_level.par.brightness1 = 2.0
fail_level.par.opacity = 0.6
fail_level.inputConnectors[0].connect(fail_glow.outputConnectors[0])

fail_over = scene.create('overTOP', 'fail_comp')
fail_over.inputConnectors[0].connect(fail_fit.outputConnectors[0])
fail_over.inputConnectors[1].connect(fail_level.outputConnectors[0])

result = {{'typography': 'loaded'}}
"""})

    # ---------------------------------------------------------------
    # Feedback Trails — Particles leave persistent trails
    # ---------------------------------------------------------------
    td_call("td_execute_python", {"script": """
scene = op('/project1/s04_audit')

# Feedback loop for trails
feedback = scene.create('feedbackTOP', 'trail_feedback')
feedback.par.top = 'trail_comp'

trail_level = scene.create('levelTOP', 'trail_fade')
trail_level.par.opacity = 0.82

trail_comp = scene.create('compositeTOP', 'trail_merge')
trail_comp.par.operation = 'over'
trail_comp.inputConnectors[0].connect(op('/project1/s04_audit/audit_render').outputConnectors[0])
trail_comp.inputConnectors[1].connect(trail_level.outputConnectors[0])

feedback.inputConnectors[0].connect(trail_comp.outputConnectors[0])
trail_level.inputConnectors[0].connect(feedback.outputConnectors[0])

result = {'trails': 'wired'}
"""})

    # ---------------------------------------------------------------
    # Layer Mix: Trails + Pass/Fail + Scan Line
    # ---------------------------------------------------------------
    td_call("td_execute_python", {"script": """
scene = op('/project1/s04_audit')

layer_mix = scene.create('layerMixTOP', 'audit_comp')
layer_mix.par.resolutionw = 1920
layer_mix.par.resolutionh = 1080

# Layer 0: particle trails
trails = op('/project1/s04_audit/trail_merge')
layer_mix.inputConnectors[0].connect(trails.outputConnectors[0])
layer_mix.par.layer1opacity = 1.0
layer_mix.par.layer1composite = 'over'

# Layer 1: PASS (positioned upper right)
pass_tx = scene.create('transformTOP', 'pass_position')
pass_tx.inputConnectors[0].connect(op('/project1/s04_audit/pass_comp').outputConnectors[0])
pass_tx.par.tx = 300
pass_tx.par.ty = 200

layer_mix.inputConnectors[1].connect(pass_tx.outputConnectors[0])
layer_mix.par.layer2opacity = 0.0  # animate via CHOP
layer_mix.par.layer2composite = 'over'

# Layer 2: FAIL (positioned lower left)
fail_tx = scene.create('transformTOP', 'fail_position')
fail_tx.inputConnectors[0].connect(op('/project1/s04_audit/fail_comp').outputConnectors[0])
fail_tx.par.tx = -300
fail_tx.par.ty = -200

layer_mix.inputConnectors[2].connect(fail_tx.outputConnectors[0])
layer_mix.par.layer3opacity = 0.0  # animate via CHOP
layer_mix.par.layer3composite = 'over'

# Scan line sweep
scan = scene.create('rampTOP', 'scan_line')
scan.par.type = 'vertical'
scan.par.colorr = 0
scan.par.colorg = 0.8
scan.par.colorb = 1.0
scan.par.colora = 0.3

scan_blur = scene.create('blurTOP', 'scan_blur')
scan_blur.par.size = 5
scan_blur.inputConnectors[0].connect(scan.outputConnectors[0])

layer_mix.inputConnectors[3].connect(scan_blur.outputConnectors[0])
layer_mix.par.layer4opacity = 0.4
layer_mix.par.layer4composite = 'add'

result = {'layer_mix': 'configured'}
"""})

    # ---------------------------------------------------------------
    # Final Output
    # ---------------------------------------------------------------
    td_call("td_execute_python", {"script": """
scene = op('/project1/s04_audit')

# Chromatic aberration + vignette
vig = scene.create('rampTOP', 'vignette')
vig.par.type = 'radial'

vig_comp = scene.create('multiplyTOP', 'vig_mult')
vig_comp.inputConnectors[0].connect(op('/project1/s04_audit/audit_comp').outputConnectors[0])
vig_comp.inputConnectors[1].connect(vig.outputConnectors[0])

# Connect to scene output
scene_out = op('/project1/s04_audit/scene_render')
scene_out.inputConnectors[0].connect(vig_comp.outputConnectors[0])

result = {'post_fx': 'complete'}
"""})

    # ---------------------------------------------------------------
    # Gate State Animation — Alternates pass/fail cycles
    # ---------------------------------------------------------------
    td_call("td_execute_python", {"script": """
scene = op('/project1/s04_audit')

timer = scene.create('timerCHOP', 'scene_timer')
timer.par.length = 15.0
timer.par.unitmenu = 0

# Square wave for pass/fail toggle
gate_state = scene.create('lfoCHOP', 'gate_state')
gate_state.par.type = 'square'
gate_state.par.freq = 0.2  # toggles every 5s
gate_state.par.amp = 0.5
gate_state.par.offset = 0.5

result = {'animation': 'ready'}
"""})

    print("[s04] The Audit Gate built.")


if __name__ == "__main__":
    build()
