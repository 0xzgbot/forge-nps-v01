#!/usr/bin/env python3
"""
Cinesmith — TouchDesigner Audit Gate Visualizer
=================================================

A dramatic sci-fi visualization of the Cinesmith visual truth audit gate:
- Central scanning portal with rotating hexagon
- Data packets entering from left
- Green PASS burst with particle explosion
- Red FAIL burst with glitch/distortion
- Score readout as glowing numbers
- Scan-line sweep effect

Output: /tmp/cinesmith_audit_gate.toe
Record: /tmp/cinesmith_audit_gate_output.mov
"""

import json
import subprocess
import sys
from pathlib import Path

TD_MCP_PORT = 40404
TD_MCP_URL = f"http://127.0.0.1:{TD_MCP_PORT}/mcp"
OUTPUT_TOE = Path("/tmp/cinesmith_audit_gate.toe")


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

    print("[1/9] Cleaning project...")
    td_call("td_execute_python", {
        "script": """
root = op('/project1')
for child in list(root.children):
    if child.valid: child.destroy()
result = {'cleaned': True}
"""
    })

    print("[2/9] Creating GLSL shader...")
    shader = generate_glsl()
    shader_path = Path("/tmp/cinesmith_audit_gate.glsl")
    shader_path.write_text(shader)

    td_call("td_execute_python", {
        "script": f"""
root = op('/project1')

glsl = root.create(glslTOP, 'audit_gate')
glsl.par.resolutionw = 1280
glsl.par.resolutionh = 720

with open('{shader_path}', 'r') as f:
    glsl.text = f.read()

time_const = root.create(constantTOP, 'time_input')
time_const.par.format = 'rgba32float'
time_const.par.resolutionw = 1
time_const.par.resolutionh = 1
time_const.par.value0.expr = 'absTime.seconds'

audio_in = root.create(constantTOP, 'audio_input')
audio_in.par.format = 'rgba32float'
audio_in.par.resolutionw = 256
audio_in.par.resolutionh = 2

# Gate state CHOP (alternates between pass/fail cycles)
gate_chop = root.create(constantCHOP, 'gate_state')
gate_chop.par.value0 = 1.0

glsl.inputConnectors[0].connect(time_const.outputConnectors[0])
glsl.inputConnectors[1].connect(audio_in.outputConnectors[0])
glsl.inputConnectors[2].connect(gate_chop.outputConnectors[0])

result = {{'glsl_created': True}}
"""
    })

    print("[3/9] Creating text overlays...")
    td_call("td_execute_python", {
        "script": """
root = op('/project1')

# Title
title = root.create(textTOP, 'title_text')
title.par.text = 'VISUAL TRUTH AUDIT'
title.par.fontsizex = 42
title.par.fontsizey = 42
title.par.fontcolorr = 0.0
title.par.fontcolorg = 0.8
title.par.fontcolorb = 1.0
title.par.alignx = 'center'
title.par.aligny = 'center'
title.par.resolutionw = 600
title.par.resolutionh = 80
title.par.bgcolora = 0.0
title.par.bordera = 0.0

# Score label
score = root.create(textTOP, 'score_text')
score.par.text = 'SCORE: 87'
score.par.fontsizex = 36
score.par.fontsizey = 36
score.par.fontcolorr = 0.0
score.par.fontcolorg = 1.0
score.par.fontcolorb = 0.4
score.par.alignx = 'center'
score.par.aligny = 'center'
score.par.resolutionw = 300
score.par.resolutionh = 60
score.par.bgcolora = 0.0
score.par.bordera = 0.0

result = {'text': 'created'}
"""
    })

    print("[4/9] Creating feedback trails...")
    td_call("td_execute_python", {
        "script": """
root = op('/project1')
level = root.create(levelTOP, 'trail_level')
level.par.opacity = 0.9
comp = root.create(compositeTOP, 'trail_comp')
comp.par.operation = 'over'
feedback = root.create(feedbackTOP, 'trail_feedback')
feedback.par.top = 'trail_comp'

glsl = op('/project1/audit_gate')
level.inputConnectors[0].connect(glsl.outputConnectors[0])
comp.inputConnectors[0].connect(level.outputConnectors[0])
comp.inputConnectors[1].connect(feedback.outputConnectors[0])
feedback.inputConnectors[0].connect(comp.outputConnectors[0])
result = {'feedback': 'wired'}
"""
    })

    print("[5/9] Creating heavy bloom...")
    td_call("td_execute_python", {
        "script": """
root = op('/project1')

blur1 = root.create(blurTOP, 'bloom_blur')
blur1.par.size = 25
blur1.par.sigma = 4.0

bloom_level = root.create(levelTOP, 'bloom_level')
bloom_level.par.brightness1 = 3.0

final_comp = root.create(compositeTOP, 'final_output')
final_comp.par.operation = 'add'

trail_out = op('/project1/trail_comp')
blur1.inputConnectors[0].connect(trail_out.outputConnectors[0])
bloom_level.inputConnectors[0].connect(blur1.outputConnectors[0])
final_comp.inputConnectors[0].connect(trail_out.outputConnectors[0])
final_comp.inputConnectors[1].connect(bloom_level.outputConnectors[0])
result = {'bloom': 'wired'}
"""
    })

    print("[6/9] Creating glitch distortion overlay...")
    td_call("td_execute_python", {
        "script": """
root = op('/project1')

# Noise for glitch blocks
noise = root.create(noiseTOP, 'glitch_noise')
noise.par.type = 'random'
noise.par.resolutionw = 64
noise.par.resolutionh = 64

# Displace TOP for glitch effect
displace = root.create(displaceTOP, 'glitch_displace')
displace.inputConnectors[0].connect(op('/project1/final_output').outputConnectors[0])
displace.inputConnectors[1].connect(noise.outputConnectors[0])
displace.par.uvweight = 0.02
displace.par.uvoffsetweight1 = 0.5

result = {'glitch': 'wired'}
"""
    })

    print("[7/9] Adding scan-line sweep...")
    td_call("td_execute_python", {
        "script": """
root = op('/project1')

# Ramp for scan line position
ramp = root.create(rampTOP, 'scan_ramp')
ramp.par.type = 'horizontal'
ramp.par.phase = 'absTime.frame % 720 / 720.0'

# Level to make thin line
scan_level = root.create(levelTOP, 'scan_level')
scan_level.par.blacklevel = 0.98
scan_level.par.brightness1 = 5.0
scan_level.inputConnectors[0].connect(ramp.outputConnectors[0])

# Multiply with scene
scan_mult = root.create(compositeTOP, 'scan_mult')
scan_mult.par.operation = 'over'
scan_mult.inputConnectors[0].connect(op('/project1/glitch_displace').outputConnectors[0])
scan_mult.inputConnectors[1].connect(scan_level.outputConnectors[0])

result = {'scan': 'wired'}
"""
    })

    print("[8/9] Creating output, window, recorder...")
    td_call("td_execute_python", {
        "script": f"""
root = op('/project1')

out_null = root.create(nullTOP, 'out')
out_null.inputConnectors[0].connect(op('/project1/scan_mult').outputConnectors[0])

win = root.create(windowCOMP, 'perform_window')
win.par.winop = out_null.path
win.par.winw = 1280
win.par.winh = 720
win.par.winopen = False

recorder = root.create(moviefileoutTOP, 'recorder')
recorder.par.type = 'movie'
recorder.par.file = '/tmp/cinesmith_audit_gate_output.mov'
recorder.par.videocodec = 'prores'
recorder.par.fps = 30
recorder.inputConnectors[0].connect(out_null.outputConnectors[0])

result = {{'output_ready': True}}
"""
    })

    print("[9/9] Saving project...")
    td_call("td_execute_python", {
        "script": f"""
project.save('{OUTPUT_TOE}')
result = {{'saved_to': '{OUTPUT_TOE}'}}
"""
    })

    print("[9/9] DONE")
    print(f"\nOpen: {OUTPUT_TOE}")
    print("Record: /tmp/cinesmith_audit_gate_output.mov")


def generate_glsl():
    return '''// Cinesmith Audit Gate — GLSL Visualization
// Dramatic sci-fi portal with PASS/FAIL particle explosions

uniform float uTime;
uniform vec2 uResolution;
uniform sampler2D sTD2DInputs[3];  // time, audio, gate_state

#define PI 3.14159265359
#define TAU 6.28318530718

float hash(vec2 p) {
    vec3 p3 = fract(vec3(p.xyx) * 0.1031);
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.x + p3.y) * p3.z);
}

float noise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), f.x),
               mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), f.x), f.y);
}

float sdHexagon(vec2 p, float r) {
    vec2 q = abs(p);
    return max(q.x * 0.866025 + q.y * 0.5, q.y) - r;
}

float sdSegment(vec2 p, vec2 a, vec2 b) {
    vec2 pa = p - a, ba = b - a;
    float h = clamp(dot(pa, ba) / dot(ba, ba), 0.0, 1.0);
    return length(pa - ba * h);
}

float glow(float d, float radius) {
    return pow(radius / max(abs(d), 0.001), 1.5);
}

mat2 rotate(float a) {
    float s = sin(a), c = cos(a);
    return mat2(c, -s, s, c);
}

// Particle explosion
vec3 particleBurst(vec2 uv, vec2 center, float t, vec3 color, float seed) {
    vec3 col = vec3(0.0);
    for (int i = 0; i < 24; i++) {
        float fi = float(i);
        float angle = fi * (TAU / 24.0) + seed * 3.7;
        float speed = 0.3 + hash(vec2(fi, seed)) * 0.4;
        float dist = t * speed;
        float size = 0.008 * (1.0 - smoothstep(0.0, 1.0, t));
        
        vec2 pPos = center + vec2(cos(angle), sin(angle)) * dist;
        float d = length(uv - pPos);
        float g = glow(d, size * 2.0) * 0.2 * (1.0 - smoothstep(0.0, 0.8, t));
        
        float hueShift = fi / 24.0;
        vec3 pCol = color * (0.7 + 0.3 * sin(hueShift * TAU));
        col += pCol * g;
    }
    return col;
}

void main() {
    vec2 uv = (gl_FragCoord.xy - uResolution * 0.5) / uResolution.y;
    float t = uTime;
    float gateState = texture(sTD2DInputs[2], vec2(0.5, 0.5)).r;
    
    // Cycle between pass and fail phases
    float cycle = fract(t * 0.15);
    float isPass = cycle < 0.5 ? 1.0 : 0.0;
    float phaseTime = fract(cycle * 2.0);  // 0-1 within each phase
    
    // Colors
    vec3 passColor = vec3(0.0, 1.0, 0.4);
    vec3 failColor = vec3(1.0, 0.15, 0.15);
    vec3 scanColor = vec3(0.0, 0.8, 1.0);
    vec3 gateColor = mix(failColor, passColor, isPass);
    
    // Background
    vec3 bg = vec3(0.015, 0.02, 0.03);
    float bgNoise = noise(uv * 2.0 + t * 0.02) * 0.02;
    bg += bgNoise;
    
    // Grid
    vec2 grid = abs(fract(uv * 15.0) - 0.5);
    float gridLine = smoothstep(0.015, 0.0, min(grid.x, grid.y));
    bg += vec3(0.0, 0.2, 0.3) * gridLine * 0.04;
    
    vec3 col = bg;
    vec3 glowAccum = vec3(0.0);
    
    // Central hexagon gate
    vec2 hexUV = rotate(t * 0.3) * uv;
    float hex = sdHexagon(hexUV, 0.18);
    float hexRing = abs(hex) - 0.005;
    
    // Hex glow
    float hexGlow = glow(hex, 0.04) * 0.2;
    glowAccum += gateColor * hexGlow;
    
    // Inner hex spinning counter
    vec2 hexUV2 = rotate(-t * 0.5) * uv;
    float hex2 = sdHexagon(hexUV2, 0.14);
    float hex2Glow = glow(abs(hex2) - 0.003, 0.02) * 0.15;
    glowAccum += scanColor * hex2Glow;
    
    // Data packets entering from left
    for (int i = 0; i < 6; i++) {
        float fi = float(i);
        float yOffset = (fi - 2.5) * 0.08;
        float xPos = -0.6 + mod(t * 0.25 + fi * 0.15, 1.2);
        vec2 pPos = vec2(xPos, yOffset);
        float d = length(uv - pPos);
        float pSize = 0.012;
        
        float packet = smoothstep(pSize, pSize * 0.3, d);
        col += scanColor * packet * 0.6;
        glowAccum += scanColor * glow(d, pSize * 2.0) * 0.1;
        
        // Packet trail
        vec2 trailDir = vec2(-0.08, 0.0);
        for (int j = 1; j <= 4; j++) {
            vec2 tPos = pPos + trailDir * float(j);
            float td = length(uv - tPos);
            float tGlow = glow(td, pSize * 0.8) * 0.04 * (1.0 - float(j) / 5.0);
            glowAccum += scanColor * tGlow;
        }
    }
    
    // Scan line sweep
    float scanY = sin(t * 1.2) * 0.4;
    float scanDist = abs(uv.y - scanY);
    float scanGlow = glow(scanDist, 0.005) * 0.15;
    col += scanColor * scanGlow;
    
    // PASS/FAIL particle burst at transition
    float burstTime = smoothstep(0.0, 0.1, phaseTime) * (1.0 - smoothstep(0.3, 0.5, phaseTime));
    if (isPass > 0.5) {
        col += particleBurst(uv, vec2(0.0), phaseTime * 2.0, passColor, 1.0) * burstTime;
    } else {
        col += particleBurst(uv, vec2(0.0), phaseTime * 2.0, failColor, 2.0) * burstTime;
    }
    
    // Score ring animation
    float scoreAngle = atan(uv.y, uv.x);
    float scoreRadius = length(uv);
    float ringDist = abs(scoreRadius - 0.28);
    float arcGlow = glow(ringDist, 0.003) * 0.1;
    float arcFill = smoothstep(0.0, TAU * 0.7, mod(scoreAngle + t * 0.2 + PI, TAU));
    glowAccum += gateColor * arcGlow * arcFill;
    
    // Add glow accum
    col += glowAccum;
    
    // Central bright core
    float coreDist = length(uv);
    col += gateColor * glow(coreDist, 0.03) * 0.15 * (0.5 + 0.5 * sin(t * 3.0));
    
    // Vignette
    float vig = 1.0 - dot(uv * 0.8, uv * 0.8);
    vig = smoothstep(0.0, 1.0, vig);
    col *= vig * 0.65 + 0.35;
    
    // Scanlines
    float scanline = sin(uv.y * uResolution.y * 0.6) * 0.012;
    col -= scanline;
    
    // Chromatic aberration
    float ca = length(uv) * 0.003;
    col.r += ca;
    col.b -= ca;
    
    // Tone map
    col = col / (col + vec3(1.0)) * 1.25;
    
    fragColor = vec4(col, 1.0);
}
'''


if __name__ == "__main__":
    build()
