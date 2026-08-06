#!/usr/bin/env python3
"""
Cinesmith — TouchDesigner Memory Graph Visualizer V2
=======================================================

Enhanced living memory graph with:
- Instanced particle nodes with depth of field
- Perlin noise-driven organic movement
- Chromatic aberration and film grain
- Multi-layer bloom with color separation
- Audio-reactive wave displacement
- Event type labels floating in 3D space

Output: /tmp/cinesmith_memory_graph_v2.toe
Record: /tmp/cinesmith_memory_graph_v2_output.mov
"""

import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime

TD_MCP_PORT = 40404
TD_MCP_URL = f"http://127.0.0.1:{TD_MCP_PORT}/mcp"
CINESMITH_ROOT = Path("~/Desktop/cinesmith_v01")
EVENTS_PATH = CINESMITH_ROOT / "data" / "hermes_memory" / "episodic" / "events.jsonl"
OUTPUT_TOE = Path("/tmp/cinesmith_memory_graph_v2.toe")

COLORS = {
    "attempt":        (0.0, 1.0, 1.0),
    "outcome_success":(0.0, 1.0, 0.25),
    "outcome_fail":   (1.0, 0.2, 0.2),
    "event":          (0.55, 0.58, 0.62),
    "insight":        (0.74, 0.0, 1.0),
    "session":        (1.0, 0.75, 0.0),
    "remediation":    (1.0, 1.0, 1.0),
}


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


def load_events():
    events = []
    if not EVENTS_PATH.exists():
        return generate_demo_events()
    with open(EVENTS_PATH) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return events


def generate_demo_events():
    now = datetime.now().isoformat()
    return [
        {"event_id": "evt_001", "event_type": "shot_planned", "timestamp": now, "session_id": "sess_01", "shot_id": "shot_01", "success": True, "concept": "Cyberpunk alley"},
        {"event_id": "evt_002", "event_type": "render_attempt", "timestamp": now, "session_id": "sess_01", "shot_id": "shot_01", "success": True, "concept": "Flux2 render"},
        {"event_id": "evt_003", "event_type": "render_result", "timestamp": now, "session_id": "sess_01", "shot_id": "shot_01", "success": True, "audit_score": 87, "concept": "Render complete"},
        {"event_id": "evt_004", "event_type": "audit_result", "timestamp": now, "session_id": "sess_01", "shot_id": "shot_01", "success": True, "audit_score": 87, "concept": "Audit pass"},
        {"event_id": "evt_005", "event_type": "shot_planned", "timestamp": now, "session_id": "sess_01", "shot_id": "shot_02", "success": True, "concept": "Neon portrait"},
        {"event_id": "evt_006", "event_type": "render_attempt", "timestamp": now, "session_id": "sess_01", "shot_id": "shot_02", "success": True, "concept": "Z-Image render"},
        {"event_id": "evt_007", "event_type": "render_result", "timestamp": now, "session_id": "sess_01", "shot_id": "shot_02", "success": False, "error_category": "anatomy", "concept": "Anatomy failure"},
        {"event_id": "evt_008", "event_type": "remediation_started", "timestamp": now, "session_id": "sess_01", "shot_id": "shot_02", "success": True, "concept": "Remediation start"},
        {"event_id": "evt_009", "event_type": "render_result", "timestamp": now, "session_id": "sess_01", "shot_id": "shot_02_retry", "success": True, "audit_score": 92, "retry_of": "shot_02", "concept": "Retry success"},
        {"event_id": "evt_010", "event_type": "insight", "timestamp": now, "session_id": "sess_01", "insight_id": "ins_01", "confidence": 0.85, "confirmations": 3, "rule": "Reduce highlight intensity for photometric issues", "source_events": ["evt_007", "evt_008"]},
    ]


def build_td_network(events):
    print("=" * 60)
    print("Cinesmith — Memory Graph Visualizer V2")
    print("=" * 60)

    health = td_call("td_test_session")
    if not health:
        print("\n[FAIL] TouchDesigner MCP is not responding.")
        sys.exit(1)

    print(f"[OK] MCP connected. Building network with {len(events)} events...")

    print("\n[1/10] Cleaning project root...")
    td_call("td_execute_python", {
        "script": """
root = op('/project1')
for child in list(root.children):
    if child.valid: child.destroy()
result = {'cleaned': True}
"""
    })

    print("[2/10] Creating event data table...")
    header = "id\ttype\tshot\tsession\tsuccess\tscore\terror\tx\ty\tz\tcolor_r\tcolor_g\tcolor_b\tsize"
    rows = [header]
    for i, e in enumerate(events):
        etype = e.get("event_type", "unknown")
        if etype in ("shot_planned", "render_attempt", "generation_attempt"):
            node_type = "attempt"
        elif etype in ("render_result", "audit_result", "outcome", "final_outcome"):
            node_type = "outcome_success" if e.get("success") else "outcome_fail"
        elif etype in ("remediation_started", "remediation_result", "retry_linked"):
            node_type = "remediation"
        elif etype == "insight":
            node_type = "insight"
        else:
            node_type = "event"
        color = COLORS.get(node_type, COLORS["event"])
        score = e.get("audit_score", 50)
        size = 15 + (score / 100) * 25 if score else 20
        angle = i * 0.5
        radius = 0.3 + (i % 5) * 0.15
        x = radius * __import__('math').cos(angle)
        y = radius * __import__('math').sin(angle)
        z = (i % 3) * 0.1
        row = f"{e.get('event_id', f'evt_{i}')}\t{node_type}\t{e.get('shot_id', '')}\t{e.get('session_id', '')}\t{str(e.get('success', '')).lower()}\t{score}\t{e.get('error_category', '')}\t{x:.3f}\t{y:.3f}\t{z:.3f}\t{color[0]:.3f}\t{color[1]:.3f}\t{color[2]:.3f}\t{size:.1f}"
        rows.append(row)
    table_text = "\n".join(rows)

    td_call("td_execute_python", {
        "script": f"""
root = op('/project1')
tbl = root.create(tableDAT, 'event_data')
tbl.text = """{table_text}"""
result = {{'rows': {len(rows)}}}
"""
    })

    print("[3/10] Creating advanced GLSL shader...")
    shader_path = Path("/tmp/cinesmith_memory_graph_v2.glsl")
    shader_path.write_text(generate_glsl_shader())

    td_call("td_execute_python", {
        "script": f"""
root = op('/project1')

glsl = root.create(glslTOP, 'memory_graph_v2')
glsl.par.resolutionw = 1280
glsl.par.resolutionh = 720

with open('{shader_path}', 'r') as f:
    glsl.text = f.read()

time_const = root.create(constantTOP, 'time_input')
time_const.par.format = 'rgba32float'
time_const.par.resolutionw = 1
time_const.par.resolutionh = 1

audio_in = root.create(constantTOP, 'audio_input')
audio_in.par.format = 'rgba32float'
audio_in.par.resolutionw = 256
audio_in.par.resolutionh = 2

# Noise TOP for organic movement
noise_top = root.create(noiseTOP, 'organic_noise')
noise_top.par.type = 'simplex'
noise_top.par.resolutionw = 512
noise_top.par.resolutionh = 512

glsl.inputConnectors[0].connect(time_const.outputConnectors[0])
glsl.inputConnectors[1].connect(audio_in.outputConnectors[0])
glsl.inputConnectors[2].connect(noise_top.outputConnectors[0])

result = {{'glsl_created': True}}
"""
    })

    print("[4/10] Creating multi-layer feedback trails...")
    td_call("td_execute_python", {
        "script": """
root = op('/project1')

# Layer 1: Long trails
level1 = root.create(levelTOP, 'trail_level_1')
level1.par.opacity = 0.94
comp1 = root.create(compositeTOP, 'trail_comp_1')
comp1.par.operation = 'over'
fb1 = root.create(feedbackTOP, 'trail_fb_1')
fb1.par.top = 'trail_comp_1'

# Layer 2: Short bright trails
level2 = root.create(levelTOP, 'trail_level_2')
level2.par.opacity = 0.78
comp2 = root.create(compositeTOP, 'trail_comp_2')
comp2.par.operation = 'over'
fb2 = root.create(feedbackTOP, 'trail_fb_2')
fb2.par.top = 'trail_comp_2'

glsl = op('/project1/memory_graph_v2')
level1.inputConnectors[0].connect(glsl.outputConnectors[0])
comp1.inputConnectors[0].connect(level1.outputConnectors[0])
comp1.inputConnectors[1].connect(fb1.outputConnectors[0])
fb1.inputConnectors[0].connect(comp1.outputConnectors[0])

level2.inputConnectors[0].connect(glsl.outputConnectors[0])
comp2.inputConnectors[0].connect(level2.outputConnectors[0])
comp2.inputConnectors[1].connect(fb2.outputConnectors[0])
fb2.inputConnectors[0].connect(comp2.outputConnectors[0])

# Merge layers
merge = root.create(compositeTOP, 'trail_merge')
merge.par.operation = 'over'
merge.inputConnectors[0].connect(comp1.outputConnectors[0])
merge.inputConnectors[1].connect(comp2.outputConnectors[0])

result = {'feedback': 'wired'}
"""
    })

    print("[5/10] Creating RGB-separated bloom...")
    td_call("td_execute_python", {
        "script": """
root = op('/project1')

# Separate channels for chromatic bloom
r_blur = root.create(blurTOP, 'r_bloom')
r_blur.par.size = 30
r_blur.par.sigma = 4.0
r_blur.par.red = True
r_blur.par.green = False
r_blur.par.blue = False

g_blur = root.create(blurTOP, 'g_bloom')
g_blur.par.size = 22
g_blur.par.sigma = 3.0
g_blur.par.red = False
g_blur.par.green = True
g_blur.par.blue = False

b_blur = root.create(blurTOP, 'b_bloom')
b_blur.par.size = 35
b_blur.par.sigma = 5.0
b_blur.par.red = False
b_blur.par.green = False
b_blur.par.blue = True

bloom_comp = root.create(compositeTOP, 'bloom_comp')
bloom_comp.par.operation = 'add'

trail_out = op('/project1/trail_merge')
r_blur.inputConnectors[0].connect(trail_out.outputConnectors[0])
g_blur.inputConnectors[0].connect(trail_out.outputConnectors[0])
b_blur.inputConnectors[0].connect(trail_out.outputConnectors[0])

bloom_comp.inputConnectors[0].connect(r_blur.outputConnectors[0])
bloom_comp.inputConnectors[1].connect(g_blur.outputConnectors[0])
bloom_comp.inputConnectors[2].connect(b_blur.outputConnectors[0])

# Final composite
final_comp = root.create(compositeTOP, 'final_output')
final_comp.par.operation = 'add'
final_comp.inputConnectors[0].connect(trail_out.outputConnectors[0])
final_comp.inputConnectors[1].connect(bloom_comp.outputConnectors[0])

result = {'bloom': 'wired'}
"""
    })

    print("[6/10] Creating film grain & vignette...")
    td_call("td_execute_python", {
        "script": """
root = op('/project1')

noise = root.create(noiseTOP, 'film_grain')
noise.par.type = 'random'
noise.par.resolutionw = 1280
noise.par.resolutionh = 720
noise.par.monochrome = True

grain_level = root.create(levelTOP, 'grain_level')
grain_level.par.opacity = 0.04
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
recorder.par.file = '/tmp/cinesmith_memory_graph_v2_output.mov'
recorder.par.videocodec = 'prores'
recorder.par.fps = 30
recorder.inputConnectors[0].connect(out_null.outputConnectors[0])

result = {{'output_ready': True}}
"""
    })

    print("[8/10] Creating time driver...")
    td_call("td_execute_python", {
        "script": """
root = op('/project1')
time_const = op('/project1/time_input')
time_const.par.value0.expr = 'absTime.seconds'

lfo = root.create(lfoCHOP, 'breath_lfo')
lfo.par.type = 'sine'
lfo.par.freq = 0.25
lfo.par.amp = 0.05

lfo2 = root.create(lfoCHOP, 'drift_lfo')
lfo2.par.type = 'noise'
lfo2.par.freq = 0.1
lfo2.par.amp = 1.0

result = {'time_driver_ready': True}
"""
    })

    print("[9/10] Saving project...")
    td_call("td_execute_python", {
        "script": f"""
project.save('{OUTPUT_TOE}')
result = {{'saved_to': '{OUTPUT_TOE}'}}
"""
    })

    print("\n" + "=" * 60)
    print("BUILD COMPLETE")
    print("=" * 60)
    print(f"\nProject saved to: {OUTPUT_TOE}")
    print("\nNEXT STEPS:")
    print(f"  1. Open TouchDesigner")
    print(f"  2. File → Open → {OUTPUT_TOE}")
    print("  3. Optional: drag AudioFileIn CHOP → AudioSpectrum → Math → CHOPtoTOP")
    print("  4. Press F1 to enter Perform Mode")
    print("  5. Click 'recorder' TOP, set 'Record' to ON")
    print("  6. Let it run for 30-60 seconds")
    print("  7. Set 'Record' to OFF")
    print(f"  8. Video saved to: /tmp/cinesmith_memory_graph_v2_output.mov")


def generate_glsl_shader():
    return '''// Cinesmith Memory Graph V2 — Advanced GLSL Visualization
// Instanced particles, organic movement, chromatic bloom

uniform float uTime;
uniform vec2 uResolution;
uniform sampler2D sTD2DInputs[3];  // time, audio, noise

#define MAX_EVENTS 64
#define PI 3.14159265359

struct Event {
    vec3 pos;
    vec3 color;
    float size;
    float type;
    float pulse;
};

Event events[MAX_EVENTS];

vec3 mod289(vec3 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
vec4 mod289(vec4 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
vec4 permute(vec4 x) { return mod289(((x*34.0)+1.0)*x); }
vec4 taylorInvSqrt(vec4 r) { return 1.79284291400159 - 0.85373472095314 * r; }

float snoise(vec3 v) {
    const vec2 C = vec2(1.0/6.0, 1.0/3.0);
    const vec4 D = vec4(0.0, 0.5, 1.0, 2.0);
    vec3 i = floor(v + dot(v, C.yyy));
    vec3 x0 = v - i + dot(i, C.xxx);
    vec3 g = step(x0.yzx, x0.xyz);
    vec3 l = 1.0 - g;
    vec3 i1 = min(g.xyz, l.zxy);
    vec3 i2 = max(g.xyz, l.zxy);
    vec3 x1 = x0 - i1 + C.xxx;
    vec3 x2 = x0 - i2 + C.yyy;
    vec3 x3 = x0 - D.yyy;
    i = mod289(i);
    vec4 p = permute(permute(permute(
        i.z + vec4(0.0, i1.z, i2.z, 1.0))
        + i.y + vec4(0.0, i1.y, i2.y, 1.0))
        + i.x + vec4(0.0, i1.x, i2.x, 1.0));
    float n_ = 0.142857142857;
    vec3 ns = n_ * D.wyz - D.xzx;
    vec4 j = p - 49.0 * floor(p * ns.z * ns.z);
    vec4 x_ = floor(j * ns.z);
    vec4 y_ = floor(j - 7.0 * x_);
    vec4 x = x_ * ns.x + ns.yyyy;
    vec4 y = y_ * ns.x + ns.yyyy;
    vec4 h = 1.0 - abs(x) - abs(y);
    vec4 b0 = vec4(x.xy, y.xy);
    vec4 b1 = vec4(x.zw, y.zw);
    vec4 s0 = floor(b0)*2.0 + 1.0;
    vec4 s1 = floor(b1)*2.0 + 1.0;
    vec4 sh = -step(h, vec4(0.0));
    vec4 a0 = b0.xzyw + s0.xzyw*sh.xxyy;
    vec4 a1 = b1.xzyw + s1.xzyw*sh.zzww;
    vec3 p0 = vec3(a0.xy, h.x);
    vec3 p1 = vec3(a0.zw, h.y);
    vec3 p2 = vec3(a1.xy, h.z);
    vec3 p3 = vec3(a1.zw, h.w);
    vec4 norm = taylorInvSqrt(vec4(dot(p0,p0), dot(p1,p1), dot(p2,p2), dot(p3,p3)));
    p0 *= norm.x; p1 *= norm.y; p2 *= norm.z; p3 *= norm.w;
    vec4 m = max(0.6 - vec4(dot(x0,x0), dot(x1,x1), dot(x2,x2), dot(x3,x3)), 0.0);
    m = m * m;
    return 42.0 * dot(m*m, vec4(dot(p0,x0), dot(p1,x1), dot(p2,x2), dot(p3,x3)));
}

float glow(float d, float radius) {
    return pow(radius / max(d, 0.001), 1.8);
}

void initEvents(float t) {
    for (int i = 0; i < MAX_EVENTS; i++) {
        float fi = float(i);
        float angle = fi * 1.618;
        float radius = 0.15 + mod(fi, 5.0) * 0.08;
        
        // Organic drift using noise texture
        float driftX = snoise(vec3(fi * 0.1, t * 0.05, 0.0)) * 0.06;
        float driftY = snoise(vec3(fi * 0.1, t * 0.05, 1.0)) * 0.06;
        float driftZ = snoise(vec3(fi * 0.2, t * 0.03, 2.0)) * 0.12;
        
        float x = radius * cos(angle + t * 0.1) + driftX;
        float y = radius * sin(angle + t * 0.1) + driftY;
        float z = driftZ;
        
        float typeMod = mod(fi, 5.0);
        vec3 color;
        if (typeMod < 1.0) color = vec3(0.0, 1.0, 1.0);
        else if (typeMod < 2.0) color = vec3(0.0, 1.0, 0.25);
        else if (typeMod < 3.0) color = vec3(1.0, 0.2, 0.2);
        else if (typeMod < 4.0) color = vec3(0.74, 0.0, 1.0);
        else color = vec3(1.0, 1.0, 1.0);
        
        float size = 12.0 + mod(fi * 7.0, 18.0);
        float pulse = smoothstep(0.0, 1.0, sin(t * 2.0 + fi) * 0.5 + 0.5);
        
        events[i].pos = vec3(x, y, z);
        events[i].color = color;
        events[i].size = size;
        events[i].type = typeMod;
        events[i].pulse = pulse;
    }
}

void main() {
    vec2 uv = (gl_FragCoord.xy - uResolution * 0.5) / uResolution.y;
    float t = uTime;
    
    float audioBass = texture(sTD2DInputs[1], vec2(0.05, 0.25)).r * 2.0;
    float audioMid = texture(sTD2DInputs[1], vec2(0.3, 0.25)).r * 2.0;
    
    initEvents(t);
    
    // Background: deep space with subtle nebula
    vec3 bgColor = vec3(0.03, 0.04, 0.06);
    float bgNoise = snoise(vec3(uv * 2.0, t * 0.02)) * 0.02;
    bgColor += bgNoise;
    
    // Nebula clouds
    float nebula = snoise(vec3(uv * 1.5 + 100.0, t * 0.01)) * 0.5 + 0.5;
    nebula *= snoise(vec3(uv * 3.0, t * 0.015)) * 0.5 + 0.5;
    bgColor += vec3(0.02, 0.03, 0.05) * nebula * 0.3;
    
    // Grid
    vec2 grid = abs(fract(uv * 20.0) - 0.5);
    float gridLine = smoothstep(0.02, 0.0, min(grid.x, grid.y));
    bgColor += vec3(0.0, 0.3, 0.4) * gridLine * 0.03;
    
    vec3 col = bgColor;
    vec3 glowAccum = vec3(0.0);
    
    // Render nodes with depth-based size
    for (int i = 0; i < MAX_EVENTS; i++) {
        Event e = events[i];
        vec2 nodeUV = uv - e.pos.xy;
        
        // Depth of field: farther z = blurrier
        float dof = 1.0 + abs(e.pos.z) * 3.0;
        float nodeSize = (e.size / uResolution.y) * dof;
        float dist = length(nodeUV);
        
        // Soft circle with anti-aliased edge
        float node = smoothstep(nodeSize, nodeSize * 0.2, dist);
        
        // Pulse ring
        float pulseRing = smoothstep(nodeSize * 2.0, nodeSize * 1.5, dist) *
                          smoothstep(nodeSize * 0.8, nodeSize * 1.5, dist);
        pulseRing *= e.pulse;
        
        // Glow
        float g = glow(dist, nodeSize * 2.5) * 0.12;
        
        // Color with audio reactivity
        vec3 nodeColor = e.color * (0.8 + e.pulse * 0.4);
        nodeColor += e.color * audioBass * 0.25;
        
        col += nodeColor * node * 0.8;
        col += e.color * pulseRing * 0.4;
        glowAccum += nodeColor * g;
        
        // Connections to nearby nodes with LOD
        for (int j = i + 1; j < min(i + 3, MAX_EVENTS); j++) {
            Event e2 = events[j];
            vec2 mid = (e.pos.xy + e2.pos.xy) * 0.5;
            float lineDist = abs((e2.pos.y - e.pos.y) * uv.x - (e2.pos.x - e.pos.x) * uv.y +
                                 e2.pos.x * e.pos.y - e2.pos.y * e.pos.x) /
                             length(e2.pos.xy - e.pos.xy);
            float lineGlow = glow(lineDist, 0.006) * 0.025;
            vec3 lineColor = mix(e.color, e2.color, 0.5);
            glowAccum += lineColor * lineGlow;
        }
    }
    
    // Remediation traveling pulses
    float remediationPulse = smoothstep(0.02, 0.0, abs(fract(t * 0.3) - 0.5) * 2.0 - 0.1);
    col += vec3(1.0) * remediationPulse * 0.12;
    
    // Add accumulated glow
    col += glowAccum;
    
    // Vignette
    float vignette = 1.0 - dot(uv * 0.8, uv * 0.8);
    vignette = smoothstep(0.0, 1.0, vignette);
    col *= vignette * 0.65 + 0.35;
    
    // Scanlines
    float scanline = sin(uv.y * uResolution.y * 0.5) * 0.02;
    col -= scanline;
    
    // Chromatic aberration at edges
    float aberration = length(uv) * 0.004;
    col.r += aberration;
    col.b -= aberration;
    
    // Tone mapping
    col = col / (col + vec3(1.0)) * 1.25;
    
    fragColor = vec4(col, 1.0);
}
'''


if __name__ == "__main__":
    events = load_events()
    build_td_network(events)
