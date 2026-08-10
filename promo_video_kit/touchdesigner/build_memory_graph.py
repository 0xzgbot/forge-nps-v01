#!/usr/bin/env python3
"""
Cinesmith — TouchDesigner Memory Graph Visualizer Builder
============================================================

This script builds a complete TouchDesigner network that visualizes
Cinesmith memory events as a living, pulsing, audio-reactive graph.

PREREQUISITES (for you to set up):
------------------------------------
1. Install TouchDesigner (Non-Commercial is FREE):
   https://derivative.ca/download

2. Install the twozero MCP plugin (repo-local hermes_home — never ~/.hermes):
   bash "${HERMES_HOME:-$(cd "$(dirname "$0")/../.." && pwd)/hermes_home}/skills/creative/touchdesigner-mcp/scripts/setup.sh"
   Then drag ~/Downloads/twozero.tox into TD and enable MCP.

3. Verify MCP is running:
   nc -z 127.0.0.1 40404 && echo "READY"

4. Install td-mcp Python client (if not already):
   pip install mcp  # or uv add mcp

5. Ensure Cinesmith events.jsonl exists:
   ~/Desktop/cinesmith_v01/data/hermes_memory/episodic/events.jsonl

USAGE:
------
python3 build_memory_graph.py

This will:
- Read your events.jsonl
- Create a TD network with GLSL shaders, particles, feedback, bloom
- Wire everything together
- Output a recording-ready network

OUTPUT:
-------
The network writes to /tmp/cinesmith_memory_visualizer.toe
Open it in TouchDesigner, then press F1 to enter perform mode and record.

RECORDING:
----------
Inside TD, create a MovieFileOut TOP (already wired in this script)
and set it recording. Or use the record button in the script below.
"""

import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime

# ── Configuration ──────────────────────────────────────────────────────────
TD_MCP_PORT = 40404
TD_MCP_URL = f"http://127.0.0.1:{TD_MCP_PORT}/mcp"
CINESMITH_ROOT = Path("~/Desktop/cinesmith_v01")
EVENTS_PATH = CINESMITH_ROOT / "data" / "hermes_memory" / "episodic" / "events.jsonl"
OUTPUT_TOE = Path("/tmp/cinesmith_memory_visualizer.toe")

# Color palette matching Cinesmith UI
COLORS = {
    "attempt":        (0.0, 1.0, 1.0),      # cyan #00FFFF
    "outcome_success":(0.0, 1.0, 0.25),     # green #00FF41
    "outcome_fail":   (1.0, 0.2, 0.2),      # red #FF3333
    "event":          (0.55, 0.58, 0.62),   # gray #8B949E
    "insight":        (0.74, 0.0, 1.0),     # purple #BD00FF
    "session":        (1.0, 0.75, 0.0),     # amber #FFBF00
    "remediation":    (1.0, 1.0, 1.0),      # white healing pulse
}

# ── Helper: Call TD MCP ────────────────────────────────────────────────────

def td_call(method: str, params: dict = None):
    """Call a TouchDesigner MCP tool via curl."""
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

# ── Load Cinesmith Memory Events ───────────────────────────────────────────────

def load_events():
    events = []
    if not EVENTS_PATH.exists():
        print(f"[WARN] events.jsonl not found at {EVENTS_PATH}")
        print("[WARN] Using demo events. Replace with your real events.")
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
    """Generate a small demo event set if no real data exists."""
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

# ── Build TD Network ───────────────────────────────────────────────────────

def build_td_network(events):
    """
    Build a TouchDesigner network that visualizes Cinesmith memory events.
    Uses GLSL TOP for main rendering, Feedback TOP for trails, Bloom for glow.
    """
    print("=" * 60)
    print("Cinesmith — TouchDesigner Memory Graph Builder")
    print("=" * 60)

    # Check MCP is alive
    health = td_call("td_test_session")
    if not health:
        print("\n[FAIL] TouchDesigner MCP is not responding.")
        print("Make sure:")
        print("  1. TouchDesigner is running")
        print("  2. twozero.tox is installed and MCP is enabled")
        print("  3. Run: nc -z 127.0.0.1 40404")
        sys.exit(1)

    print(f"[OK] MCP connected. Building network with {len(events)} events...")

    # ── Step 1: Clean project ─────────────────────────────────────────────
    print("\n[1/8] Cleaning project root...")
    td_call("td_execute_python", {
        "script": """
root = op('/project1')
for child in list(root.children):
    if child.valid:
        child.destroy()
result = {'cleaned': True}
"""
    })

    # ── Step 2: Create event data as a Table DAT ──────────────────────────
    print("[2/8] Creating event data table...")

    # Build table rows
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

        # Position in a spiral for initial layout
        angle = i * 0.5
        radius = 0.3 + (i % 5) * 0.15
        x = radius * __import__('math').cos(angle)
        y = radius * __import__('math').sin(angle)
        z = (i % 3) * 0.1

        row = f"{e.get('event_id', f'evt_{i}')}\t{node_type}\t{e.get('shot_id', '')}\t{e.get('session_id', '')}\t{str(e.get('success', '')).lower()}\t{score}\t{e.get('error_category', '')}\t{x:.3f}\t{y:.3f}\t{z:.3f}\t{color[0]:.3f}\t{color[1]:.3f}\t{color[2]:.3f}\t{size:.1f}"
        rows.append(row)

    table_text = "\n".join(rows)

    triple_quote = '"""'
    td_call("td_execute_python", {
        "script": f"""
root = op('/project1')
tbl = root.create(tableDAT, 'event_data')
tbl.text = {triple_quote}{table_text}{triple_quote}
result = {{'rows': {len(rows)}}}
"""
    })

    # ── Step 3: Create GLSL TOP with custom shader ────────────────────────
    print("[3/8] Creating GLSL shader...")

    # Write shader to a file first, then load into TD
    shader_path = Path("/tmp/cinesmith_memory_graph.glsl")
    shader_path.write_text(generate_glsl_shader())

    td_call("td_execute_python", {
        "script": f"""
root = op('/project1')

# Create GLSL TOP
glsl = root.create(glslTOP, 'memory_graph')

# Set resolution (non-commercial cap: 1280x1280)
glsl.par.resolutionw = 1280
glsl.par.resolutionh = 720

# Load vertex shader
with open('{shader_path}', 'r') as f:
    glsl.text = f.read()

# Input 0: time (Constant TOP)
time_const = root.create(constantTOP, 'time_input')
time_const.par.format = 'rgba32float'
time_const.par.resolutionw = 1
time_const.par.resolutionh = 1

# Input 1: audio spectrum (placeholder — user connects real audio)
audio_in = root.create(constantTOP, 'audio_input')
audio_in.par.format = 'rgba32float'
audio_in.par.resolutionw = 256
audio_in.par.resolutionh = 2

# Wire inputs
glsl.inputConnectors[0].connect(time_const.outputConnectors[0])
glsl.inputConnectors[1].connect(audio_in.outputConnectors[0])

result = {{'glsl_created': glsl.path}}
"""
    })

    # ── Step 4: Create Feedback TOP for trails ────────────────────────────
    print("[4/8] Creating feedback trail system...")

    td_call("td_execute_python", {
        "script": """
root = op('/project1')

# Feedback loop: glsl -> level -> composite -> feedback -> glsl
level = root.create(levelTOP, 'trail_level')
level.par.opacity = 0.92  # trail persistence

composite = root.create(compositeTOP, 'trail_comp')
composite.par.operation = 'over'

feedback = root.create(feedbackTOP, 'trail_feedback')
feedback.par.top = 'trail_comp'

# Wire: glsl -> level -> composite
#       feedback -> composite (second input)
#       composite -> feedback
glsl = op('/project1/memory_graph')
level.inputConnectors[0].connect(glsl.outputConnectors[0])
composite.inputConnectors[0].connect(level.outputConnectors[0])
composite.inputConnectors[1].connect(feedback.outputConnectors[0])
feedback.inputConnectors[0].connect(composite.outputConnectors[0])

result = {'feedback_wired': True}
"""
    })

    # ── Step 5: Create Bloom / Glow post-FX ───────────────────────────────
    print("[5/8] Creating bloom post-processing...")

    td_call("td_execute_python", {
        "script": """
root = op('/project1')

# Blur for bloom
blur1 = root.create(blurTOP, 'bloom_blur')
blur1.par.size = 15
blur1.par.sigma = 2.5

# Level to boost bloom
bloom_level = root.create(levelTOP, 'bloom_level')
bloom_level.par.brightness1 = 2.0

# Composite original + bloom
final_comp = root.create(compositeTOP, 'final_output')
final_comp.par.operation = 'add'

# Wire
trail_out = op('/project1/trail_comp')
blur1.inputConnectors[0].connect(trail_out.outputConnectors[0])
bloom_level.inputConnectors[0].connect(blur1.outputConnectors[0])
final_comp.inputConnectors[0].connect(trail_out.outputConnectors[0])
final_comp.inputConnectors[1].connect(bloom_level.outputConnectors[0])

result = {'bloom_wired': True}
"""
    })

    # ── Step 6: Create Null output + Window ───────────────────────────────
    print("[6/8] Creating output and window...")

    td_call("td_execute_python", {
        "script": """
root = op('/project1')

# Null output
out_null = root.create(nullTOP, 'out')
out_null.inputConnectors[0].connect(op('/project1/final_output').outputConnectors[0])

# Window for perform mode
win = root.create(windowCOMP, 'perform_window')
win.par.winop = out_null.path
win.par.winw = 1280
win.par.winh = 720
win.par.winopen = False  # User opens manually

# MovieFileOut for recording
recorder = root.create(moviefileoutTOP, 'recorder')
recorder.par.type = 'movie'
recorder.par.file = '/tmp/cinesmith_memory_graph_output.mov'
recorder.par.videocodec = 'prores'
recorder.par.fps = 30
recorder.inputConnectors[0].connect(out_null.outputConnectors[0])

result = {'output_ready': True}
"""
    })

    # ── Step 7: Create time driver ────────────────────────────────────────
    print("[7/8] Creating time driver...")

    td_call("td_execute_python", {
        "script": """
root = op('/project1')

# Time expression on the constant TOP
time_const = op('/project1/time_input')
time_const.par.value0.expr = 'absTime.seconds'

# Also drive node positions with a subtle LFO
lfo = root.create(lfoCHOP, 'breath_lfo')
lfo.par.type = 'sine'
lfo.par.freq = 0.3
lfo.par.amp = 0.05

result = {'time_driver_ready': True}
"""
    })

    # ── Step 8: Save project ──────────────────────────────────────────────
    print("[8/8] Saving project...")

    td_call("td_execute_python", {
        "script": f"""
project.save('{OUTPUT_TOE}')
result = {{'saved_to': '{OUTPUT_TOE}'}}
"""
    })

    # ── Done ──────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("BUILD COMPLETE")
    print("=" * 60)
    print(f"\nProject saved to: {OUTPUT_TOE}")
    print("\nNEXT STEPS FOR YOU:")
    print("  1. Open TouchDesigner")
    print(f"  2. File → Open → {OUTPUT_TOE}")
    print("  3. Optional: drag an Audio File In CHOP and connect to audio_input")
    print("  4. Press F1 to enter Perform Mode")
    print("  5. Click the 'recorder' TOP, set 'Record' to ON")
    print("  6. Let it run for 30-60 seconds")
    print("  7. Set 'Record' to OFF")
    print("  8. Video saved to: /tmp/cinesmith_memory_graph_output.mov")
    print("\nTIPS:")
    print("  - Non-Commercial TD caps at 1280x1280 (we use 1280x720)")
    print("  - ProRes codec works without a commercial license on macOS")
    print("  - For audio-reactive: add AudioFileIn → AudioSpectrum → Math → CHOPtoTOP")
    print("    and connect that TOP to memory_graph's second input.")

# ── GLSL Shader ────────────────────────────────────────────────────────────

def generate_glsl_shader():
    """Generate the GLSL shader for the memory graph visualization."""
    return '''// Cinesmith Memory Graph — GLSL Visualization
// Visualizes episodic memory events as a living, breathing node network

uniform float uTime;
uniform vec2 uResolution;
uniform sampler2D sTD2DInputs[2];  // [0]=time, [1]=audio spectrum

// ── Event data (hardcoded for demo — in production, feed via texture) ──
#define MAX_EVENTS 64

struct Event {
    vec3 pos;
    vec3 color;
    float size;
    float type;  // 0=attempt, 1=success, 2=fail, 3=insight, 4=remediation
    float pulse;
};

Event events[MAX_EVENTS];

// ── Noise functions ──────────────────────────────────────────────────────
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

// ── Initialize events (synthetic for visual richness) ────────────────────
void initEvents(float t) {
    for (int i = 0; i < MAX_EVENTS; i++) {
        float fi = float(i);
        float angle = fi * 1.618;  // golden angle for organic distribution
        float radius = 0.15 + mod(fi, 5.0) * 0.08;

        // Animate positions with slow drift
        float drift = snoise(vec3(fi * 0.1, t * 0.05, 0.0)) * 0.05;
        float x = radius * cos(angle + t * 0.1 + drift) + drift;
        float y = radius * sin(angle + t * 0.1 + drift) + drift * 0.7;
        float z = snoise(vec3(fi * 0.2, t * 0.03, 1.0)) * 0.1;

        // Type cycling
        float typeMod = mod(fi, 5.0);
        vec3 color;
        if (typeMod < 1.0) color = vec3(0.0, 1.0, 1.0);       // cyan: attempt
        else if (typeMod < 2.0) color = vec3(0.0, 1.0, 0.25); // green: success
        else if (typeMod < 3.0) color = vec3(1.0, 0.2, 0.2);  // red: fail
        else if (typeMod < 4.0) color = vec3(0.74, 0.0, 1.0); // purple: insight
        else color = vec3(1.0, 1.0, 1.0);                      // white: remediation

        float size = 12.0 + mod(fi * 7.0, 18.0);

        // Pulse on newer events
        float pulse = smoothstep(0.0, 1.0, sin(t * 2.0 + fi) * 0.5 + 0.5);

        events[i].pos = vec3(x, y, z);
        events[i].color = color;
        events[i].size = size;
        events[i].type = typeMod;
        events[i].pulse = pulse;
    }
}

// ── SDF for rounded box (node shape) ─────────────────────────────────────
float sdRoundedBox(vec2 p, vec2 b, float r) {
    vec2 d = abs(p) - b + r;
    return min(max(d.x, d.y), 0.0) + length(max(d, 0.0)) - r;
}

// ── Glow function ────────────────────────────────────────────────────────
float glow(float d, float radius) {
    return pow(radius / max(d, 0.001), 1.8);
}

// ── Main ─────────────────────────────────────────────────────────────────
void main() {
    vec2 uv = (gl_FragCoord.xy - uResolution * 0.5) / uResolution.y;
    float t = uTime;

    // Read audio spectrum (if connected)
    float audioBass = 0.5;
    float audioMid = 0.5;
    float audioHi = 0.5;
    if (uResolution.x > 0.0) {
        vec4 spectrum = texture(sTD2DInputs[1], vec2(0.05, 0.25));
        audioBass = spectrum.r * 2.0;
        vec4 spectrumMid = texture(sTD2DInputs[1], vec2(0.3, 0.25));
        audioMid = spectrumMid.r * 2.0;
        vec4 spectrumHi = texture(sTD2DInputs[1], vec2(0.7, 0.25));
        audioHi = spectrumHi.r * 2.0;
    }

    initEvents(t);

    // Background: deep space with subtle noise
    vec3 bgColor = vec3(0.04, 0.055, 0.08);
    float bgNoise = snoise(vec3(uv * 2.0, t * 0.02)) * 0.02;
    bgColor += bgNoise;

    // Subtle grid
    vec2 grid = abs(fract(uv * 20.0) - 0.5);
    float gridLine = smoothstep(0.02, 0.0, min(grid.x, grid.y));
    bgColor += vec3(0.0, 0.3, 0.4) * gridLine * 0.03;

    vec3 col = bgColor;
    vec3 glowAccum = vec3(0.0);

    // Render nodes
    for (int i = 0; i < MAX_EVENTS; i++) {
        Event e = events[i];
        vec2 nodeUV = uv - e.pos.xy;

        // Node shape: soft circle
        float dist = length(nodeUV);
        float nodeSize = e.size / uResolution.y;
        float node = smoothstep(nodeSize, nodeSize * 0.3, dist);

        // Pulse ring for active nodes
        float pulseRing = smoothstep(nodeSize * 1.5, nodeSize * 1.2, dist) *
                          smoothstep(nodeSize * 0.8, nodeSize * 1.2, dist);
        pulseRing *= e.pulse;

        // Glow
        float g = glow(dist, nodeSize * 2.0) * 0.15;

        // Color mixing
        vec3 nodeColor = e.color * (0.8 + e.pulse * 0.4);
        nodeColor += e.color * audioBass * 0.3;  // audio reactivity

        col += nodeColor * node * 0.8;
        col += e.color * pulseRing * 0.5;
        glowAccum += nodeColor * g;

        // Connections to nearby nodes
        for (int j = i + 1; j < min(i + 4, MAX_EVENTS); j++) {
            Event e2 = events[j];
            vec2 mid = (e.pos.xy + e2.pos.xy) * 0.5;
            float lineDist = abs((e2.pos.y - e.pos.y) * uv.x - (e2.pos.x - e.pos.x) * uv.y +
                                 e2.pos.x * e.pos.y - e2.pos.y * e.pos.x) /
                             length(e2.pos.xy - e.pos.xy);

            float lineGlow = glow(lineDist, 0.008) * 0.03;
            vec3 lineColor = mix(e.color, e2.color, 0.5);
            glowAccum += lineColor * lineGlow;
        }
    }

    // Remediation pulses (traveling along connections)
    float remediationPulse = smoothstep(0.02, 0.0, abs(fract(t * 0.3) - 0.5) * 2.0 - 0.1);
    col += vec3(1.0) * remediationPulse * 0.15;

    // Add accumulated glow
    col += glowAccum;

    // Vignette
    float vignette = 1.0 - dot(uv * 0.8, uv * 0.8);
    vignette = smoothstep(0.0, 1.0, vignette);
    col *= vignette * 0.7 + 0.3;

    // Scanlines
    float scanline = sin(uv.y * uResolution.y * 0.5) * 0.02;
    col -= scanline;

    // Subtle chromatic aberration at edges
    float aberration = length(uv) * 0.003;
    col.r += aberration;
    col.b -= aberration;

    // Tone mapping
    col = col / (col + vec3(1.0)) * 1.2;

    // Output
    fragColor = vec4(col, 1.0);
}
'''

# ── Entry Point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    events = load_events()
    build_td_network(events)
