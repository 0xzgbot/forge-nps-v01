#!/usr/bin/env python3
"""
Cinesmith — TouchDesigner Pipeline Flow Visualizer
====================================================

A cinematic visualization of the Cinesmith 5-model pipeline:
  KIMI (Director) → HERMES (Engineer) → SPARK (Renderer) → VISION (Audit) → MEMORY

Features:
- 5 glowing orbital nodes with distinct color identities
- Particle streams flowing between nodes (data packets)
- Audio-reactive pulse on each connection
- Holographic ring effects around active nodes
- Scan-line post-processing
- Text overlays for each role

Output: /tmp/cinesmith_pipeline_flow.toe
Record: /tmp/cinesmith_pipeline_flow_output.mov
"""

import json
import subprocess
import sys
from pathlib import Path

TD_MCP_PORT = 40404
TD_MCP_URL = f"http://127.0.0.1:{TD_MCP_PORT}/mcp"
OUTPUT_TOE = Path("/tmp/cinesmith_pipeline_flow.toe")

NODES = [
    {"name": "KIMI", "role": "DIRECTOR", "color": (0.0, 0.8, 1.0), "angle": 0.0},
    {"name": "HERMES", "role": "ENGINEER", "color": (0.74, 0.0, 1.0), "angle": 1.256},
    {"name": "SPARK", "role": "RENDERER", "color": (1.0, 0.6, 0.0), "angle": 2.513},
    {"name": "VISION", "role": "AUDIT", "color": (0.0, 1.0, 0.4), "angle": 3.770},
    {"name": "MEMORY", "role": "RECALL", "color": (1.0, 0.9, 0.0), "angle": 5.027},
]


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
    shader_path = Path("/tmp/cinesmith_pipeline_flow.glsl")
    shader_path.write_text(shader)

    td_call("td_execute_python", {
        "script": f"""
root = op('/project1')

# Main GLSL TOP
glsl = root.create(glslTOP, 'pipeline_flow')
glsl.par.resolutionw = 1280
glsl.par.resolutionh = 720

with open('{shader_path}', 'r') as f:
    glsl.text = f.read()

# Time input
time_const = root.create(constantTOP, 'time_input')
time_const.par.format = 'rgba32float'
time_const.par.resolutionw = 1
time_const.par.resolutionh = 1
time_const.par.value0.expr = 'absTime.seconds'

# Audio spectrum input (placeholder)
audio_in = root.create(constantTOP, 'audio_input')
audio_in.par.format = 'rgba32float'
audio_in.par.resolutionw = 256
audio_in.par.resolutionh = 2

# LFO for breathing animation
lfo = root.create(lfoCHOP, 'breath_lfo')
lfo.par.type = 'sine'
lfo.par.freq = 0.25
lfo.par.amp = 1.0

lfo2 = root.create(lfoCHOP, 'pulse_lfo')
lfo2.par.type = 'sine'
lfo2.par.freq = 0.8
lfo2.par.amp = 1.0

# CHOP to TOP for LFO values
chop_to_top = root.create(choptoTOP, 'lfo_top')
chop_to_top.par.chop = lfo.path
chop_to_top.par.format = 'rgba32float'

chop_to_top2 = root.create(choptoTOP, 'pulse_top')
chop_to_top2.par.chop = lfo2.path
chop_to_top2.par.format = 'rgba32float'

# Wire inputs
glsl.inputConnectors[0].connect(time_const.outputConnectors[0])
glsl.inputConnectors[1].connect(audio_in.outputConnectors[0])
glsl.inputConnectors[2].connect(chop_to_top.outputConnectors[0])
glsl.inputConnectors[3].connect(chop_to_top2.outputConnectors[0])

result = {{'glsl_created': True}}
"""
    })

    print("[3/9] Adding text overlays...")
    for i, node in enumerate(NODES):
        td_call("td_execute_python", {
            "script": f"""
root = op('/project1')
txt = root.create(textTOP, 'text_{node['name'].lower()}')
txt.par.text = '{node['name']}\\n{node['role']}'
txt.par.fontsizex = 28
txt.par.fontsizey = 28
txt.par.fontcolorr = {node['color'][0]:.3f}
txt.par.fontcolorg = {node['color'][1]:.3f}
txt.par.fontcolorb = {node['color'][2]:.3f}
txt.par.alignx = 'center'
txt.par.aligny = 'center'
txt.par.resolutionw = 300
txt.par.resolutionh = 120
txt.par.bgcolora = 0.0
txt.par.bordera = 0.0
result = {{'text_{node['name']}': 'created'}}
"""
        })

    print("[4/9] Creating feedback trails...")
    td_call("td_execute_python", {
        "script": """
root = op('/project1')

level = root.create(levelTOP, 'trail_level')
level.par.opacity = 0.88

comp = root.create(compositeTOP, 'trail_comp')
comp.par.operation = 'over'

feedback = root.create(feedbackTOP, 'trail_feedback')
feedback.par.top = 'trail_comp'

glsl = op('/project1/pipeline_flow')
level.inputConnectors[0].connect(glsl.outputConnectors[0])
comp.inputConnectors[0].connect(level.outputConnectors[0])
comp.inputConnectors[1].connect(feedback.outputConnectors[0])
feedback.inputConnectors[0].connect(comp.outputConnectors[0])

result = {'feedback': 'wired'}
"""
    })

    print("[5/9] Creating bloom post-FX...")
    td_call("td_execute_python", {
        "script": """
root = op('/project1')

blur1 = root.create(blurTOP, 'bloom_blur')
blur1.par.size = 20
blur1.par.sigma = 3.0

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

    print("[6/9] Creating film grain & chromatic aberration...")
    td_call("td_execute_python", {
        "script": """
root = op('/project1')

# Noise for grain
noise = root.create(noiseTOP, 'film_grain')
noise.par.type = 'random'
noise.par.resolutionw = 1280
noise.par.resolutionh = 720
noise.par.monochrome = True

# Level to dim grain
grain_level = root.create(levelTOP, 'grain_level')
grain_level.par.opacity = 0.04
grain_level.inputConnectors[0].connect(noise.outputConnectors[0])

# Composite grain on top
grain_comp = root.create(compositeTOP, 'grain_comp')
grain_comp.par.operation = 'over'
grain_comp.inputConnectors[0].connect(op('/project1/final_output').outputConnectors[0])
grain_comp.inputConnectors[1].connect(grain_level.outputConnectors[0])

result = {'grain': 'wired'}
"""
    })

    print("[7/9] Creating output, window, recorder...")
    td_call("td_execute_python", {
        "script": """
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
recorder.par.file = '/tmp/cinesmith_pipeline_flow_output.mov'
recorder.par.videocodec = 'prores'
recorder.par.fps = 30
recorder.inputConnectors[0].connect(out_null.outputConnectors[0])

result = {'output_ready': True}
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
    print("Record output: /tmp/cinesmith_pipeline_flow_output.mov")
    print("\nPro tip: Add AudioFileIn CHOP → AudioSpectrum → Math (gain=10) → CHOPtoTOP")
    print("         and connect to audio_input for audio-reactive particles.")


def generate_glsl():
    return '''// Cinesmith Pipeline Flow — GLSL Visualization
// 5-model orbital pipeline with particle streams

uniform float uTime;
uniform vec2 uResolution;
uniform sampler2D sTD2DInputs[4];  // time, audio, lfo, pulse

#define NODES 5
#define PI 3.14159265359

struct Node {
    vec2 pos;
    vec3 color;
    float radius;
    float pulse;
};

Node nodes[NODES];

vec3 palette(float t) {
    vec3 a = vec3(0.5, 0.5, 0.5);
    vec3 b = vec3(0.5, 0.5, 0.5);
    vec3 c = vec3(1.0, 1.0, 1.0);
    vec3 d = vec3(0.263, 0.416, 0.557);
    return a + b * cos(6.28318 * (c * t + d));
}

float hash(float n) { return fract(sin(n) * 43758.5453123); }

float noise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    float n = i.x + i.y * 57.0;
    return mix(mix(hash(n), hash(n + 1.0), f.x),
               mix(hash(n + 57.0), hash(n + 58.0), f.x), f.y);
}

// Rotate point p around origin by angle a
vec2 rotate(vec2 p, float a) {
    float s = sin(a), c = cos(a);
    return vec2(p.x * c - p.y * s, p.x * s + p.y * c);
}

float sdCircle(vec2 p, float r) {
    return length(p) - r;
}

float sdRing(vec2 p, float r, float w) {
    return abs(length(p) - r) - w;
}

float glow(float d, float radius) {
    return pow(radius / max(abs(d), 0.001), 1.6);
}

void initNodes(float t, float audioBass, float lfoVal) {
    float baseRadius = 0.35 + audioBass * 0.05;
    float orbitSpeed = 0.08;
    
    vec3 colors[NODES];
    colors[0] = vec3(0.0, 0.8, 1.0);   // KIMI cyan
    colors[1] = vec3(0.74, 0.0, 1.0);  // HERMES purple
    colors[2] = vec3(1.0, 0.6, 0.0);   // SPARK orange
    colors[3] = vec3(0.0, 1.0, 0.4);   // VISION green
    colors[4] = vec3(1.0, 0.9, 0.0);   // MEMORY gold
    
    for (int i = 0; i < NODES; i++) {
        float fi = float(i);
        float angle = fi * (2.0 * PI / float(NODES)) + t * orbitSpeed;
        float breathe = 1.0 + sin(t * 0.5 + fi) * 0.03;
        nodes[i].pos = vec2(cos(angle), sin(angle)) * baseRadius * breathe;
        nodes[i].color = colors[i];
        nodes[i].radius = 0.035 + audioBass * 0.008;
        nodes[i].pulse = 0.5 + 0.5 * sin(t * 2.0 + fi * 1.5);
    }
}

// Particle on line from a to b, animated by time
vec3 particleStream(vec2 uv, vec2 a, vec2 b, float t, vec3 colA, vec3 colB, float streamIndex) {
    vec3 accum = vec3(0.0);
    vec2 dir = b - a;
    float len = length(dir);
    vec2 ndir = dir / len;
    vec2 perp = vec2(-ndir.y, ndir.x);
    
    float speed = 0.4 + hash(streamIndex) * 0.3;
    float offset = hash(streamIndex * 7.31) * len;
    float pos = mod(t * speed + offset, len);
    
    vec2 pPos = a + ndir * pos;
    float wobble = sin(t * 3.0 + streamIndex * 2.0) * 0.012;
    pPos += perp * wobble;
    
    float dist = length(uv - pPos);
    float pSize = 0.006 + hash(streamIndex * 3.7) * 0.004;
    float pGlow = glow(dist, pSize * 2.5) * 0.12;
    
    vec3 pCol = mix(colA, colB, pos / len);
    accum += pCol * pGlow;
    
    // Trail behind particle
    for (int k = 1; k <= 3; k++) {
        float trailPos = mod(pos - float(k) * 0.03, len);
        vec2 tPos = a + ndir * trailPos;
        tPos += perp * sin(t * 3.0 + streamIndex * 2.0 + float(k)) * 0.008;
        float tDist = length(uv - tPos);
        float tGlow = glow(tDist, pSize * 1.5) * 0.04 * (1.0 - float(k) / 4.0);
        accum += pCol * tGlow;
    }
    
    return accum;
}

void main() {
    vec2 uv = (gl_FragCoord.xy - uResolution * 0.5) / uResolution.y;
    float t = uTime;
    
    // Read inputs
    float audioBass = texture(sTD2DInputs[1], vec2(0.05, 0.25)).r * 2.5;
    float audioMid = texture(sTD2DInputs[1], vec2(0.3, 0.25)).r * 2.0;
    float lfoVal = texture(sTD2DInputs[2], vec2(0.5, 0.5)).r;
    float pulseVal = texture(sTD2DInputs[3], vec2(0.5, 0.5)).r;
    
    initNodes(t, audioBass, lfoVal);
    
    // Background
    vec3 bg = vec3(0.02, 0.025, 0.04);
    float bgNoise = noise(uv * 3.0 + t * 0.01) * 0.015;
    bg += bgNoise;
    
    // Subtle orbital rings
    float orbitRing = abs(sdRing(uv, 0.35, 0.001));
    bg += vec3(0.0, 0.15, 0.2) * glow(orbitRing, 0.02) * 0.08;
    
    vec3 col = bg;
    vec3 glowAccum = vec3(0.0);
    
    // Connection lines and particle streams
    for (int i = 0; i < NODES; i++) {
        int j = (i + 1) % NODES;
        Node a = nodes[i];
        Node b = nodes[j];
        
        // Distance to line segment
        vec2 ap = uv - a.pos;
        vec2 ab = b.pos - a.pos;
        float h = clamp(dot(ap, ab) / dot(ab, ab), 0.0, 1.0);
        float lineDist = length(ap - ab * h);
        
        // Connection glow
        float lineGlow = glow(lineDist, 0.004) * 0.06;
        vec3 lineCol = mix(a.color, b.color, 0.5);
        glowAccum += lineCol * lineGlow;
        
        // Multiple particle streams per connection
        for (int s = 0; s < 4; s++) {
            col += particleStream(uv, a.pos, b.pos, t + float(s) * 0.7, a.color, b.color, float(i * 4 + s));
        }
    }
    
    // Render nodes
    for (int i = 0; i < NODES; i++) {
        Node n = nodes[i];
        vec2 nuv = uv - n.pos;
        float dist = length(nuv);
        
        // Core
        float core = smoothstep(n.radius, n.radius * 0.2, dist);
        col += n.color * core * 0.9;
        
        // Holographic ring
        float ringDist = abs(dist - n.radius * 1.6);
        float ring = glow(ringDist, 0.003) * 0.15 * n.pulse;
        col += n.color * ring;
        
        // Outer glow
        float outerGlow = glow(dist, n.radius * 3.0) * 0.12;
        glowAccum += n.color * outerGlow;
        
        // Rotating arc
        vec2 ruv = rotate(nuv, t * 0.5 + float(i));
        float arc = smoothstep(n.radius * 2.0, n.radius * 1.8, abs(length(ruv) - n.radius * 1.9));
        arc *= smoothstep(0.0, 0.3, atan(ruv.y, ruv.x) + 1.0);
        arc *= smoothstep(0.0, 0.3, 1.5 - atan(ruv.y, ruv.x));
        col += n.color * arc * 0.3 * n.pulse;
    }
    
    col += glowAccum;
    
    // Center hub glow
    float hubDist = length(uv);
    col += vec3(0.1, 0.3, 0.4) * glow(hubDist, 0.08) * 0.1;
    
    // Vignette
    float vig = 1.0 - dot(uv * 0.75, uv * 0.75);
    vig = smoothstep(0.0, 1.0, vig);
    col *= vig * 0.6 + 0.4;
    
    // Scanlines
    float scan = sin(uv.y * uResolution.y * 0.7) * 0.015;
    col -= scan;
    
    // Chromatic aberration at edges
    float ca = length(uv) * 0.004;
    col.r += ca;
    col.b -= ca;
    
    // Tone mapping
    col = col / (col + vec3(1.0)) * 1.3;
    
    fragColor = vec4(col, 1.0);
}
'''


if __name__ == "__main__":
    build()
