#!/usr/bin/env python3
"""
Cinesmith — TouchDesigner Provenance Web Visualizer
=====================================================

A 3D visualization of shot retry lineage and audit provenance:
- Parent shots as larger nodes
- Retry children branching below with connecting threads
- Audit score displayed as node brightness
- Failed shots glow red, successful glow green
- Time axis flowing from left to right
- Floating text labels for shot IDs

Output: /tmp/cinesmith_provenance_web.toe
Record: /tmp/cinesmith_provenance_web_output.mov
"""

import json
import subprocess
import sys
from pathlib import Path

TD_MCP_PORT = 40404
TD_MCP_URL = f"http://127.0.0.1:{TD_MCP_PORT}/mcp"
OUTPUT_TOE = Path("/tmp/cinesmith_provenance_web.toe")


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
    shader_path = Path("/tmp/cinesmith_provenance_web.glsl")
    shader_path.write_text(shader)

    td_call("td_execute_python", {
        "script": f"""
root = op('/project1')

glsl = root.create(glslTOP, 'provenance_web')
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

glsl.inputConnectors[0].connect(time_const.outputConnectors[0])
glsl.inputConnectors[1].connect(audio_in.outputConnectors[0])

result = {{'glsl_created': True}}
"""
    })

    print("[3/9] Creating text overlays...")
    td_call("td_execute_python", {
        "script": """
root = op('/project1')

title = root.create(textTOP, 'title_text')
title.par.text = 'PROVENANCE\\nEvery shot, accounted for'
title.par.fontsizex = 32
title.par.fontsizey = 32
title.par.fontcolorr = 1.0
title.par.fontcolorg = 0.9
title.par.fontcolorb = 0.0
title.par.alignx = 'center'
title.par.aligny = 'center'
title.par.resolutionw = 500
title.par.resolutionh = 100
title.par.bgcolora = 0.0
title.par.bordera = 0.0

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

glsl = op('/project1/provenance_web')
level.inputConnectors[0].connect(glsl.outputConnectors[0])
comp.inputConnectors[0].connect(level.outputConnectors[0])
comp.inputConnectors[1].connect(feedback.outputConnectors[0])
feedback.inputConnectors[0].connect(comp.outputConnectors[0])
result = {'feedback': 'wired'}
"""
    })

    print("[5/9] Creating bloom...")
    td_call("td_execute_python", {
        "script": """
root = op('/project1')
blur1 = root.create(blurTOP, 'bloom_blur')
blur1.par.size = 22
blur1.par.sigma = 3.5
bloom_level = root.create(levelTOP, 'bloom_level')
bloom_level.par.brightness1 = 2.5
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

    print("[6/9] Adding grain...")
    td_call("td_execute_python", {
        "script": """
root = op('/project1')
noise = root.create(noiseTOP, 'film_grain')
noise.par.type = 'random'
noise.par.resolutionw = 1280
noise.par.resolutionh = 720
noise.par.monochrome = True
grain_level = root.create(levelTOP, 'grain_level')
grain_level.par.opacity = 0.03
grain_level.inputConnectors[0].connect(noise.outputConnectors[0])
grain_comp = root.create(compositeTOP, 'grain_comp')
grain_comp.par.operation = 'over'
grain_comp.inputConnectors[0].connect(op('/project1/final_output').outputConnectors[0])
grain_comp.inputConnectors[1].connect(grain_level.outputConnectors[0])
result = {'grain': 'wired'}
"""
    })

    print("[7/9] Creating output, window, recorder...")
    td_call("td_execute_python", {
        "script": f"""
root = op('/project1')

out_null = root.create(nullTOP, 'out')
out_null.inputConnectors[0].connect(op('/project1/grain_comp').outputConnectors[0])

win = root.create(windowCOMP, 'perform_window')
win.par.winop = out_null.path
win.par.winw = 1280
win.par.winh = 720
win.par.winopen = False

recorder = root.create(moviefileoutTOP, 'recorder')
recorder.par.type = 'movie'
recorder.par.file = '/tmp/cinesmith_provenance_web_output.mov'
recorder.par.videocodec = 'prores'
recorder.par.fps = 30
recorder.inputConnectors[0].connect(out_null.outputConnectors[0])

result = {{'output_ready': True}}
"""
    })

    print("[8/9] Saving project...")
    td_call("td_execute_python", {
        "script": f"""
project.save('{OUTPUT_TOE}')
result = {{'saved_to': '{OUTPUT_TOE}'}}
"""
    })

    print("[9/9] DONE")
    print(f"\nOpen: {OUTPUT_TOE}")
    print("Record: /tmp/cinesmith_provenance_web_output.mov")


def generate_glsl():
    return '''// Cinesmith Provenance Web — GLSL Visualization
// 3D retry lineage and audit trail

uniform float uTime;
uniform vec2 uResolution;
uniform sampler2D sTD2DInputs[2];

#define PI 3.14159265359
#define TAU 6.28318530718
#define MAX_SHOTS 16

float hash(float n) { return fract(sin(n) * 43758.5453123); }
float hash(vec2 p) {
    vec3 p3 = fract(vec3(p.xyx) * 0.1031);
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.x + p3.y) * p3.z);
}

float sdCircle(vec2 p, float r) {
    return length(p) - r;
}

float glow(float d, float radius) {
    return pow(radius / max(abs(d), 0.001), 1.5);
}

// Bezier curve distance approximation
float bezierDist(vec2 p, vec2 a, vec2 b, vec2 c) {
    vec2 ab = b - a;
    vec2 bc = c - b;
    float t = clamp(dot(p - a, ab) / dot(ab, ab), 0.0, 1.0);
    float t2 = clamp(dot(p - b, bc) / dot(bc, bc), 0.0, 1.0);
    vec2 p1 = mix(a, b, t);
    vec2 p2 = mix(b, c, t2);
    return min(length(p - p1), length(p - p2));
}

struct Shot {
    vec2 pos;
    float radius;
    float score;
    bool failed;
    bool hasRetry;
    float pulse;
};

Shot shots[MAX_SHOTS];

void initShots(float t) {
    // Parent shots along time axis
    shots[0] = Shot(vec2(-0.5, 0.15), 0.035, 0.92, false, true, 0.5);
    shots[1] = Shot(vec2(-0.15, -0.05), 0.035, 0.87, false, true, 0.5);
    shots[2] = Shot(vec2(0.2, 0.1), 0.035, 0.45, true, true, 0.5);
    shots[3] = Shot(vec2(0.55, -0.1), 0.035, 0.78, false, false, 0.5);
    shots[4] = Shot(vec2(-0.35, -0.25), 0.03, 0.95, false, false, 0.5);
    shots[5] = Shot(vec2(0.05, 0.25), 0.03, 0.63, true, false, 0.5);
    
    // Retry children
    shots[6] = Shot(vec2(0.2, -0.25), 0.03, 0.91, false, false, 0.5);
    shots[7] = Shot(vec2(0.05, -0.35), 0.028, 0.88, false, false, 0.5);
    
    // Animate with subtle drift
    for (int i = 0; i < 8; i++) {
        float fi = float(i);
        float drift = sin(t * 0.3 + fi * 1.7) * 0.008;
        shots[i].pos += vec2(drift, sin(t * 0.2 + fi * 2.3) * 0.005);
        shots[i].pulse = 0.5 + 0.5 * sin(t * 1.5 + fi);
    }
}

void main() {
    vec2 uv = (gl_FragCoord.xy - uResolution * 0.5) / uResolution.y;
    float t = uTime;
    float audioBass = texture(sTD2DInputs[1], vec2(0.05, 0.25)).r * 2.0;
    
    initShots(t);
    
    // Background
    vec3 bg = vec3(0.02, 0.025, 0.035);
    bg += hash(uv * 100.0 + t) * 0.008;
    
    // Time axis grid
    float gridX = smoothstep(0.008, 0.0, abs(fract(uv.x * 10.0) - 0.5) * 2.0 / 10.0);
    float gridY = smoothstep(0.008, 0.0, abs(fract(uv.y * 10.0) - 0.5) * 2.0 / 10.0);
    bg += vec3(0.0, 0.1, 0.15) * (gridX + gridY) * 0.03;
    
    vec3 col = bg;
    vec3 glowAccum = vec3(0.0);
    
    // Connection lines (parent -> child / retry)
    // shot 2 -> shot 6 (retry)
    vec2 cp1 = mix(shots[2].pos, shots[6].pos, 0.5) + vec2(0.0, -0.08);
    float lineDist1 = bezierDist(uv, shots[2].pos, cp1, shots[6].pos);
    float lineGlow1 = glow(lineDist1, 0.002) * 0.08;
    glowAccum += vec3(1.0, 0.9, 0.0) * lineGlow1;
    
    // shot 5 -> shot 7 (retry)
    vec2 cp2 = mix(shots[5].pos, shots[7].pos, 0.5) + vec2(0.0, -0.06);
    float lineDist2 = bezierDist(uv, shots[5].pos, cp2, shots[7].pos);
    float lineGlow2 = glow(lineDist2, 0.002) * 0.08;
    glowAccum += vec3(1.0, 0.9, 0.0) * lineGlow2;
    
    // Sequential connections
    for (int i = 0; i < 5; i++) {
        int j = i + 1;
        vec2 mid = mix(shots[i].pos, shots[j].pos, 0.5);
        float ld = bezierDist(uv, shots[i].pos, mid, shots[j].pos);
        float lg = glow(ld, 0.0015) * 0.06;
        glowAccum += vec3(0.0, 0.5, 0.7) * lg;
        
        // Data packet traveling
        float packetT = fract(t * 0.2 + float(i) * 0.15);
        vec2 packetPos = mix(shots[i].pos, shots[j].pos, packetT);
        float pd = length(uv - packetPos);
        float pg = glow(pd, 0.006) * 0.12;
        glowAccum += vec3(0.0, 0.8, 1.0) * pg;
    }
    
    // Render shot nodes
    for (int i = 0; i < 8; i++) {
        Shot s = shots[i];
        float dist = length(uv - s.pos);
        
        vec3 nodeColor;
        if (s.failed) nodeColor = vec3(1.0, 0.2, 0.2);
        else if (s.score > 0.85) nodeColor = vec3(0.0, 1.0, 0.4);
        else if (s.score > 0.6) nodeColor = vec3(1.0, 0.9, 0.0);
        else nodeColor = vec3(1.0, 0.6, 0.0);
        
        // Core
        float core = smoothstep(s.radius, s.radius * 0.2, dist);
        col += nodeColor * core * 0.8;
        
        // Glow
        float ng = glow(dist, s.radius * 2.5) * 0.1;
        glowAccum += nodeColor * ng;
        
        // Score ring
        float ringDist = abs(dist - s.radius * 1.5);
        float ring = glow(ringDist, 0.002) * 0.12 * s.pulse;
        col += nodeColor * ring;
        
        // Retry indicator (small orbiting dot)
        if (s.hasRetry) {
            float orbitAngle = t * 1.5 + float(i);
            vec2 orbitPos = s.pos + vec2(cos(orbitAngle), sin(orbitAngle)) * s.radius * 2.0;
            float od = length(uv - orbitPos);
            float og = glow(od, 0.005) * 0.08;
            glowAccum += vec3(1.0, 0.9, 0.0) * og;
        }
    }
    
    col += glowAccum;
    
    // Provenance label area
    vec2 labelPos = vec2(0.0, -0.42);
    float labelDist = length(uv - labelPos);
    col += vec3(1.0, 0.9, 0.0) * glow(labelDist, 0.04) * 0.05;
    
    // Vignette
    float vig = 1.0 - dot(uv * 0.75, uv * 0.75);
    vig = smoothstep(0.0, 1.0, vig);
    col *= vig * 0.6 + 0.4;
    
    // Scanlines
    float scanline = sin(uv.y * uResolution.y * 0.5) * 0.012;
    col -= scanline;
    
    // Chromatic aberration
    float ca = length(uv) * 0.003;
    col.r += ca;
    col.b -= ca;
    
    // Tone map
    col = col / (col + vec3(1.0)) * 1.2;
    
    fragColor = vec4(col, 1.0);
}
'''


if __name__ == "__main__":
    build()
