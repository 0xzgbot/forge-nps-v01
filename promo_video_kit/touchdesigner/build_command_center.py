#!/usr/bin/env python3
"""
Cinesmith — TouchDesigner Command Center HUD
===============================================

A futuristic HUD visualization inspired by the Cinesmith dashboard:
- Floating data panels with scrolling text
- Waveform/audio spectrum visualization
- Circular progress rings for campaign stats
- Live event stream as falling characters/matrix rain
- Grid layout mimicking the dashboard UI
- Pulsing connection lines between panels

Output: /tmp/cinesmith_command_center.toe
Record: /tmp/cinesmith_command_center_output.mov
"""

import json
import subprocess
import sys
from pathlib import Path

TD_MCP_PORT = 40404
TD_MCP_URL = f"http://127.0.0.1:{TD_MCP_PORT}/mcp"
OUTPUT_TOE = Path("/tmp/cinesmith_command_center.toe")


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

    print("[1/10] Cleaning project...")
    td_call("td_execute_python", {
        "script": """
root = op('/project1')
for child in list(root.children):
    if child.valid: child.destroy()
result = {'cleaned': True}
"""
    })

    print("[2/10] Creating GLSL shader...")
    shader = generate_glsl()
    shader_path = Path("/tmp/cinesmith_command_center.glsl")
    shader_path.write_text(shader)

    td_call("td_execute_python", {
        "script": f"""
root = op('/project1')

glsl = root.create(glslTOP, 'command_center')
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

    print("[3/10] Creating HUD text overlays...")
    labels = [
        ("CINESMITH NPS", 48, 0.0, 0.8, 1.0, 640, 60),
        ("CAMPAIGN: EP15_HERO", 22, 0.74, 0.0, 1.0, 300, 40),
        ("SHOTS: 24", 20, 0.0, 1.0, 0.4, 150, 40),
        ("AUDIT: 87%", 20, 1.0, 0.9, 0.0, 150, 40),
        ("SPARK READY", 18, 0.0, 0.8, 1.0, 150, 40),
    ]
    for text, size, r, g, b, w, h in labels:
        safe_name = text.replace(" ", "_").replace(":", "").replace("%", "pct")
        td_call("td_execute_python", {
            "script": f"""
root = op('/project1')
txt = root.create(textTOP, 'hud_{safe_name.lower()[:20]}')
txt.par.text = '{text}'
txt.par.fontsizex = {size}
txt.par.fontsizey = {size}
txt.par.fontcolorr = {r:.3f}
txt.par.fontcolorg = {g:.3f}
txt.par.fontcolorb = {b:.3f}
txt.par.alignx = 'center'
txt.par.aligny = 'center'
txt.par.resolutionw = {w}
txt.par.resolutionh = {h}
txt.par.bgcolora = 0.0
txt.par.bordera = 0.0
result = {{'text': 'created'}}
"""
        })

    print("[4/10] Creating feedback trails...")
    td_call("td_execute_python", {
        "script": """
root = op('/project1')
level = root.create(levelTOP, 'trail_level')
level.par.opacity = 0.85
comp = root.create(compositeTOP, 'trail_comp')
comp.par.operation = 'over'
feedback = root.create(feedbackTOP, 'trail_feedback')
feedback.par.top = 'trail_comp'

glsl = op('/project1/command_center')
level.inputConnectors[0].connect(glsl.outputConnectors[0])
comp.inputConnectors[0].connect(level.outputConnectors[0])
comp.inputConnectors[1].connect(feedback.outputConnectors[0])
feedback.inputConnectors[0].connect(comp.outputConnectors[0])
result = {'feedback': 'wired'}
"""
    })

    print("[5/10] Creating bloom...")
    td_call("td_execute_python", {
        "script": """
root = op('/project1')
blur1 = root.create(blurTOP, 'bloom_blur')
blur1.par.size = 18
blur1.par.sigma = 2.5
bloom_level = root.create(levelTOP, 'bloom_level')
bloom_level.par.brightness1 = 2.0
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

    print("[6/10] Adding film grain...")
    td_call("td_execute_python", {
        "script": """
root = op('/project1')
noise = root.create(noiseTOP, 'film_grain')
noise.par.type = 'random'
noise.par.resolutionw = 1280
noise.par.resolutionh = 720
noise.par.monochrome = True
grain_level = root.create(levelTOP, 'grain_level')
grain_level.par.opacity = 0.035
grain_level.inputConnectors[0].connect(noise.outputConnectors[0])
grain_comp = root.create(compositeTOP, 'grain_comp')
grain_comp.par.operation = 'over'
grain_comp.inputConnectors[0].connect(op('/project1/final_output').outputConnectors[0])
grain_comp.inputConnectors[1].connect(grain_level.outputConnectors[0])
result = {'grain': 'wired'}
"""
    })

    print("[7/10] Creating output, window, recorder...")
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
recorder.par.file = '/tmp/cinesmith_command_center_output.mov'
recorder.par.videocodec = 'prores'
recorder.par.fps = 30
recorder.inputConnectors[0].connect(out_null.outputConnectors[0])

result = {'output_ready': True}
"""
    })

    print("[8/10] Saving project...")
    td_call("td_execute_python", {
        "script": f"""
project.save('{OUTPUT_TOE}')
result = {{'saved_to': '{OUTPUT_TOE}'}}
"""
    })

    print("[9/10] DONE")
    print(f"\nOpen: {OUTPUT_TOE}")
    print("Record: /tmp/cinesmith_command_center_output.mov")


def generate_glsl():
    return '''// Cinesmith Command Center — HUD Visualization
// Futuristic dashboard-inspired data visualization

uniform float uTime;
uniform vec2 uResolution;
uniform sampler2D sTD2DInputs[2];  // time, audio

#define PI 3.14159265359
#define TAU 6.28318530718

float hash(float n) { return fract(sin(n) * 43758.5453123); }
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

mat2 rotate(float a) {
    float s = sin(a), c = cos(a);
    return mat2(c, -s, s, c);
}

float sdRoundedBox(vec2 p, vec2 b, float r) {
    vec2 d = abs(p) - b + r;
    return min(max(d.x, d.y), 0.0) + length(max(d, 0.0)) - r;
}

float sdCircle(vec2 p, float r) {
    return length(p) - r;
}

float glow(float d, float radius) {
    return pow(radius / max(abs(d), 0.001), 1.6);
}

// Matrix rain characters
vec3 matrixRain(vec2 uv, float t, vec3 color) {
    vec3 col = vec3(0.0);
    float colX = floor(uv.x * 30.0);
    float speed = hash(colX) * 2.0 + 1.0;
    float yPos = fract(uv.y * 20.0 + t * speed);
    float charOn = step(0.3, hash(vec2(colX, floor(uv.y * 20.0 + t * speed))));
    float brightness = smoothstep(1.0, 0.0, yPos) * charOn;
    col += color * brightness * 0.3;
    return col;
}

// Progress ring
vec3 progressRing(vec2 uv, float progress, vec3 color, float radius, float t) {
    vec3 col = vec3(0.0);
    float dist = abs(sdCircle(uv, radius));
    float ringGlow = glow(dist, 0.003) * 0.12;
    col += color * ringGlow;
    
    // Progress arc
    float angle = atan(uv.y, uv.x);
    float arcEnd = -PI + progress * TAU;
    float inArc = step(angle, arcEnd) * step(-PI, angle);
    if (arcEnd > PI) inArc += step(angle, arcEnd - TAU);
    
    float arcGlow = glow(dist, 0.005) * 0.25 * inArc;
    col += color * arcGlow;
    
    // Tick marks
    for (int i = 0; i < 12; i++) {
        float fi = float(i);
        float tickAngle = fi * (TAU / 12.0);
        vec2 tickPos = vec2(cos(tickAngle), sin(tickAngle)) * radius;
        float tickDist = length(uv - tickPos);
        float tickGlow = glow(tickDist, 0.004) * 0.08;
        col += color * tickGlow;
    }
    
    return col;
}

// Waveform bar
vec3 waveform(vec2 uv, float t, vec3 color, float xCenter, float width) {
    vec3 col = vec3(0.0);
    float localX = (uv.x - xCenter) / width;
    if (abs(localX) < 0.5) {
        float freq = 4.0;
        float wave = sin(localX * freq * TAU + t * 3.0) * 0.3;
        wave += sin(localX * freq * 2.3 * TAU - t * 2.0) * 0.2;
        wave += noise(vec2(localX * 10.0, t)) * 0.15;
        float barDist = abs(uv.y - wave);
        float barGlow = glow(barDist, 0.008) * 0.2;
        col += color * barGlow;
    }
    return col;
}

void main() {
    vec2 uv = (gl_FragCoord.xy - uResolution * 0.5) / uResolution.y;
    float t = uTime;
    float audioBass = texture(sTD2DInputs[1], vec2(0.05, 0.25)).r * 2.0;
    float audioMid = texture(sTD2DInputs[1], vec2(0.3, 0.25)).r * 2.0;
    
    // Background
    vec3 bg = vec3(0.025, 0.03, 0.04);
    bg += noise(uv * 1.5 + t * 0.01) * 0.01;
    
    // Hexagonal grid pattern
    vec2 hexUV = uv * 8.0;
    vec2 r = vec2(1.0, 1.732);
    vec2 h = r * 0.5;
    vec2 a = mod(hexUV, r) - h;
    vec2 b = mod(hexUV - h, r) - h;
    float hexDist = min(dot(a, a), dot(b, b));
    float hexGrid = smoothstep(0.04, 0.0, abs(hexDist - 0.03)) * 0.03;
    bg += vec3(0.0, 0.15, 0.25) * hexGrid;
    
    vec3 col = bg;
    vec3 glowAccum = vec3(0.0);
    
    // Left panel — Matrix rain event stream
    vec2 leftPanel = uv - vec2(-0.55, 0.0);
    float leftBox = sdRoundedBox(leftPanel, vec2(0.22, 0.38), 0.01);
    float leftBorder = glow(abs(leftBox) - 0.002, 0.003) * 0.1;
    glowAccum += vec3(0.0, 0.5, 0.7) * leftBorder;
    if (leftBox < 0.0) {
        col += matrixRain(leftPanel * vec2(4.0, 2.5), t, vec3(0.0, 0.8, 1.0));
    }
    
    // Right panel — Audit stats
    vec2 rightPanel = uv - vec2(0.55, 0.0);
    float rightBox = sdRoundedBox(rightPanel, vec2(0.22, 0.38), 0.01);
    float rightBorder = glow(abs(rightBox) - 0.002, 0.003) * 0.1;
    glowAccum += vec3(0.74, 0.0, 1.0) * rightBorder;
    
    // Progress rings in right panel
    col += progressRing(rightPanel - vec2(-0.08, 0.15), 0.87, vec3(0.0, 1.0, 0.4), 0.06, t);
    col += progressRing(rightPanel - vec2(0.08, 0.15), 0.62, vec3(1.0, 0.9, 0.0), 0.06, t);
    col += progressRing(rightPanel - vec2(-0.08, -0.1), 0.95, vec3(0.0, 0.8, 1.0), 0.06, t);
    col += progressRing(rightPanel - vec2(0.08, -0.1), 0.43, vec3(1.0, 0.2, 0.2), 0.06, t);
    
    // Center bottom — Waveform
    col += waveform(uv, t, vec3(0.0, 0.8, 1.0), 0.0, 0.6);
    col += waveform(uv, t + 0.5, vec3(0.74, 0.0, 1.0), 0.0, 0.6);
    
    // Top status bar
    vec2 topBar = uv - vec2(0.0, 0.42);
    float barDist = sdRoundedBox(topBar, vec2(0.9, 0.02), 0.005);
    glowAccum += vec3(0.0, 0.8, 1.0) * glow(abs(barDist) - 0.001, 0.002) * 0.08;
    
    // Pulsing connection lines between panels and center
    for (int i = 0; i < 5; i++) {
        float fi = float(i);
        float y = (fi - 2.0) * 0.06;
        vec2 a = vec2(-0.33, y);
        vec2 b = vec2(0.33, y);
        float lineDist = sdSegment(uv, a, b);
        float dataPulse = smoothstep(0.0, 0.05, abs(fract(t * 0.4 + fi * 0.2) - 0.5));
        float lineGlow = glow(lineDist, 0.002) * 0.06 * (0.5 + dataPulse * 0.5);
        glowAccum += vec3(0.0, 0.6, 0.8) * lineGlow;
    }
    
    col += glowAccum;
    
    // Corner brackets
    float bracketSize = 0.04;
    vec2 corners[4];
    corners[0] = vec2(-0.9, 0.5);
    corners[1] = vec2(0.9, 0.5);
    corners[2] = vec2(-0.9, -0.5);
    corners[3] = vec2(0.9, -0.5);
    for (int i = 0; i < 4; i++) {
        vec2 c = corners[i];
        vec2 d = abs(uv - c);
        float hBracket = glow(min(abs(d.x - bracketSize), abs(d.y - bracketSize)) + 0.001, 0.002) * 0.06;
        float inCorner = step(d.x, bracketSize) * step(d.y, bracketSize);
        col += vec3(0.0, 0.8, 1.0) * hBracket * inCorner;
    }
    
    // Vignette
    float vig = 1.0 - dot(uv * 0.7, uv * 0.7);
    vig = smoothstep(0.0, 1.0, vig);
    col *= vig * 0.55 + 0.45;
    
    // Scanlines
    float scanline = sin(uv.y * uResolution.y * 0.65) * 0.01;
    col -= scanline;
    
    // Chromatic aberration
    float ca = length(uv) * 0.0025;
    col.r += ca;
    col.b -= ca;
    
    // Tone map
    col = col / (col + vec3(1.0)) * 1.2;
    
    fragColor = vec4(col, 1.0);
}
'''


if __name__ == "__main__":
    build()
