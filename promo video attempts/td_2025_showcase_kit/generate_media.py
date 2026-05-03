#!/usr/bin/env python3
"""
Forge NPS — Media Asset Generator
==================================

Generates all social media assets, collages, diagrams, and UI mockups
from existing ComfyUI renders. No external dependencies beyond Pillow.

Usage:
    cd /Users/zgbot/Desktop/forge_nps_v01/td_2025_showcase_kit
    python3 generate_media.py

Output:
    assets/
        collage_4x4.png
        x_card.png
        youtube_thumbnail.png
        architecture_diagram.png
        ui_shot_provenance.png
        ui_retry_lineage.png
        ui_memory_health.png
        ui_event_stream.png
        ui_settings.png
"""

import json
import os
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

ASSETS_DIR = Path("/Users/zgbot/Desktop/forge_nps_v01/td_2025_showcase_kit/assets")
OUTPUT_DIR = ASSETS_DIR

# ------------------------------------------------------------------
# Font helpers
# ------------------------------------------------------------------
def get_font(size, bold=False):
    """Try to find a nice system font, fall back to default."""
    candidates = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/HelveticaNeue.ttc",
        "/System/Library/Fonts/SFProDisplay-Regular.otf",
        "/Library/Fonts/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def get_image_files():
    """Find all PNG/JPG assets excluding small ones (<100KB)."""
    files = []
    for ext in ("*.png", "*.jpg", "*.jpeg"):
        files.extend(ASSETS_DIR.glob(ext))
    files = [f for f in files if f.stat().st_size > 100_000]
    files.sort(key=lambda f: f.stat().st_size, reverse=True)
    return files


# ------------------------------------------------------------------
# 1. Image Collage (1200×1200)
# ------------------------------------------------------------------
def make_collage():
    files = get_image_files()[:9]
    if len(files) < 4:
        print("[collage] Not enough images, skipping")
        return

    # Use up to 9 images in a 3x3 grid
    n = min(9, len(files))
    cols = 3 if n >= 9 else 2
    rows = (n + cols - 1) // cols
    thumb_w = 1200 // cols
    thumb_h = 1200 // rows

    collage = Image.new("RGB", (1200, 1200), (10, 10, 15))

    for i, path in enumerate(files[:n]):
        img = Image.open(path).convert("RGB")
        img = img.resize((thumb_w, thumb_h), Image.LANCZOS)
        x = (i % cols) * thumb_w
        y = (i // cols) * thumb_h
        collage.paste(img, (x, y))

    out = OUTPUT_DIR / "collage_4x4.png"
    collage.save(out, quality=95)
    print(f"[collage] Saved {out}")


# ------------------------------------------------------------------
# 2. X Card (1200×675)
# ------------------------------------------------------------------
def make_x_card():
    files = get_image_files()
    if not files:
        print("[x_card] No images, skipping")
        return

    bg = Image.open(files[0]).convert("RGB")
    bg = bg.resize((1200, 675), Image.LANCZOS)

    # Dark gradient overlay
    overlay = Image.new("RGBA", (1200, 675), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for y in range(675):
        alpha = int(180 * (y / 675))  # darker at bottom
        draw.line([(0, y), (1200, y)], fill=(0, 0, 0, alpha))

    bg = Image.alpha_composite(bg.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(bg)

    title_font = get_font(72)
    sub_font = get_font(32)
    tag_font = get_font(20)

    draw.text((60, 400), "FORGE NPS", fill=(255, 255, 255), font=title_font)
    draw.text((60, 490), "Every shot, accounted for", fill=(200, 200, 220), font=sub_font)
    draw.text((60, 550), "Hermes Agent Creative Hackathon  ·  Nous Research", fill=(150, 150, 170), font=tag_font)

    out = OUTPUT_DIR / "x_card.png"
    bg.save(out, quality=95)
    print(f"[x_card] Saved {out}")


# ------------------------------------------------------------------
# 3. YouTube Thumbnail (1280×720)
# ------------------------------------------------------------------
def make_youtube_thumbnail():
    files = get_image_files()
    if not files:
        print("[youtube_thumb] No images, skipping")
        return

    bg = Image.open(files[0]).convert("RGB")
    bg = bg.resize((1280, 720), Image.LANCZOS)

    overlay = Image.new("RGBA", (1280, 720), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for y in range(720):
        alpha = int(160 * (y / 720))
        draw.line([(0, y), (1280, y)], fill=(0, 0, 0, alpha))

    bg = Image.alpha_composite(bg.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(bg)

    big_font = get_font(80)
    small_font = get_font(36)

    # Draw outline text effect
    text = "5 AI Models → 1 Pipeline"
    x, y = 60, 480
    for dx, dy in [(-2, -2), (-2, 2), (2, -2), (2, 2)]:
        draw.text((x+dx, y+dy), text, fill=(0, 0, 0), font=big_font)
    draw.text((x, y), text, fill=(0, 240, 255), font=big_font)

    draw.text((60, 580), "Forge NPS  ·  Hermes Agent Hackathon", fill=(255, 255, 255), font=small_font)

    out = OUTPUT_DIR / "youtube_thumbnail.png"
    bg.save(out, quality=95)
    print(f"[youtube_thumb] Saved {out}")


# ------------------------------------------------------------------
# 4. Architecture Diagram (1920×1080)
# ------------------------------------------------------------------
def make_architecture_diagram():
    W, H = 1920, 1080
    img = Image.new("RGB", (W, H), (8, 8, 14))
    draw = ImageDraw.Draw(img)

    title_font = get_font(42)
    node_font = get_font(24)
    label_font = get_font(18)
    flow_font = get_font(20)

    # Title
    draw.text((60, 40), "Forge NPS Architecture", fill=(255, 255, 255), font=title_font)
    draw.text((60, 95), "Five minds. One pipeline. Every shot accounted for.", fill=(150, 150, 170), font=label_font)

    # Nodes: [x, y, w, h, color, label, sublabel]
    nodes = [
        (120, 220, 280, 120, (0, 200, 255), "KIMI", "Director Planner"),
        (520, 220, 280, 120, (180, 0, 255), "HERMES", "Pipeline Brain"),
        (920, 220, 280, 120, (255, 140, 0), "SPARK", "Renderer"),
        (1320, 220, 280, 120, (0, 255, 100), "VISION", "Quality Audit"),
        (920, 520, 280, 120, (255, 220, 0), "MEMORY", "Historian"),
    ]

    for x, y, w, h, color, label, sub in nodes:
        # Glow
        for i in range(3):
            glow = Image.new("RGBA", (w + i*20, h + i*20), (*color, 40 - i*10))
            img.paste(glow, (x - i*10, y - i*10), glow)
        # Box
        draw.rounded_rectangle([x, y, x+w, y+h], radius=12, fill=(*color, 30), outline=color, width=2)
        draw.text((x + 20, y + 25), label, fill=color, font=node_font)
        draw.text((x + 20, y + 65), sub, fill=(180, 180, 200), font=label_font)

    # Arrows between nodes
    arrows = [
        (400, 280, 520, 280),   # Kimi → Hermes
        (800, 280, 920, 280),   # Hermes → Spark
        (1200, 280, 1320, 280), # Spark → Vision
        (1460, 340, 1060, 520), # Vision → Memory
        (1060, 520, 800, 340),  # Memory → Hermes (feedback)
    ]

    for x1, y1, x2, y2 in arrows:
        draw.line([(x1, y1), (x2, y2)], fill=(100, 100, 120), width=3)
        # Arrowhead
        draw.polygon([(x2, y2), (x2-10, y2-6), (x2-10, y2+6)], fill=(100, 100, 120))

    # Flow labels
    flows = [
        (430, 255, "shot plan"),
        (830, 255, "compile"),
        (1230, 255, "audit"),
        (1320, 450, "record"),
        (850, 460, "feedback"),
    ]
    for x, y, text in flows:
        draw.text((x, y), text, fill=(120, 120, 140), font=flow_font)

    # Bottom: data flow text
    draw.text((120, 750), "Data Flow:", fill=(255, 255, 255), font=node_font)
    draw.text((120, 800), "Brief → Kimi plans → Kimi self-checks → Hermes compiles → Spark renders → Vision audits → Pass or Remediate → Memory records",
              fill=(150, 150, 170), font=label_font)

    # Event types
    draw.text((120, 860), "Canonical Events:  profile  ·  kimi_raw  ·  kimi_plan  ·  kimi_review  ·  compiler  ·  spark  ·  memory  ·  done",
              fill=(100, 100, 130), font=label_font)

    out = OUTPUT_DIR / "architecture_diagram.png"
    img.save(out, quality=95)
    print(f"[arch_diagram] Saved {out}")


# ------------------------------------------------------------------
# 5. UI Mockup: Shot Provenance Detail
# ------------------------------------------------------------------
def make_ui_shot_provenance():
    W, H = 1920, 1080
    img = Image.new("RGB", (W, H), (15, 15, 22))
    draw = ImageDraw.Draw(img)

    header_font = get_font(28)
    section_font = get_font(22)
    body_font = get_font(16)
    code_font = get_font(14)
    tag_font = get_font(13)

    # Header bar
    draw.rectangle([0, 0, W, 60], fill=(25, 25, 35))
    draw.text((30, 18), "Forge NPS  ·  Shot Detail  ·  SHOT_004", fill=(255, 255, 255), font=header_font)
    draw.text((1650, 22), "AUDITED_PASS  ·  Score: 87", fill=(0, 255, 100), font=tag_font)

    # Left sidebar
    draw.rectangle([0, 60, 300, H], fill=(20, 20, 28))
    sidebar_items = ["Campaigns", "Shots", "Audit", "Memory", "Settings"]
    for i, item in enumerate(sidebar_items):
        y = 100 + i * 50
        color = (0, 200, 255) if item == "Shots" else (150, 150, 170)
        draw.text((30, y), item, fill=color, font=body_font)

    # Main content area
    x = 340
    y = 100
    sections = [
        ("KIMI PLAN", [
            "Visual Brief: Establishing shot of cyberpunk cityscape at blue hour",
            "Rationale: Sets tone for EP15 opening sequence",
            "Constraints: Must include neon signage, rain, single human figure",
            "Coverage: Wide → Medium → Close-up progression planned",
        ], (0, 200, 255)),
        ("HERMES COMPILATION", [
            "Compiled Prompt: cinematic wide shot, cyberpunk cityscape, blue hour...",
            "Negative Prompt: blurry, oversaturated, cartoon, watermark",
            "Skills Used: prompt_cyber_neon, prompt_cinematic_lighting",
            "Model Standard: flux2-turbo  ·  Workflow: 01_flux2_text_to_image",
        ], (180, 0, 255)),
        ("SPARK OUTPUT", [
            "Prompt ID: f2ac90_SHOT_004",
            "Seed: 42  ·  Steps: 4  ·  CFG: 1.0",
            "Image: /FORGE_NPS_MEDIA/images/.../SHOT_004_00001_.png",
            "Render Time: 1.2s",
        ], (255, 140, 0)),
        ("VISION AUDIT", [
            "Status: PASS  ·  Score: 87/100",
            "Issues: Minor chromatic aberration on left edge (acceptable)",
            "Model: qwen3.6-35b-a3b  ·  Timestamp: 2026-05-01T20:14:32Z",
        ], (0, 255, 100)),
    ]

    for title, lines, color in sections:
        draw.text((x, y), title, fill=color, font=section_font)
        y += 40
        for line in lines:
            draw.text((x + 20, y), line, fill=(200, 200, 220), font=code_font)
            y += 28
        y += 20

    out = OUTPUT_DIR / "ui_shot_provenance.png"
    img.save(out, quality=95)
    print(f"[ui_provenance] Saved {out}")


# ------------------------------------------------------------------
# 6. UI Mockup: Retry Lineage
# ------------------------------------------------------------------
def make_ui_retry_lineage():
    W, H = 1920, 1080
    img = Image.new("RGB", (W, H), (15, 15, 22))
    draw = ImageDraw.Draw(img)

    header_font = get_font(28)
    node_font = get_font(20)
    body_font = get_font(16)
    code_font = get_font(14)

    draw.rectangle([0, 0, W, 60], fill=(25, 25, 35))
    draw.text((30, 18), "Forge NPS  ·  Retry Lineage  ·  Family Tree", fill=(255, 255, 255), font=header_font)

    # Tree nodes
    nodes = [
        (200, 200, "ORIGINAL", "SHOT_004", "AUDITED_FAIL  ·  Score: 34", (255, 80, 80)),
        (700, 200, "REMEDIATION", "REM_004_a", "Prompt revised by Hermes", (255, 200, 0)),
        (1200, 200, "RETRY", "SHOT_004_RETRY_1", "AUDITED_PASS  ·  Score: 91", (0, 255, 100)),
    ]

    for x, y, title, id_str, status, color in nodes:
        w, h = 420, 140
        draw.rounded_rectangle([x, y, x+w, y+h], radius=10, outline=color, width=2)
        draw.text((x+20, y+15), title, fill=color, font=node_font)
        draw.text((x+20, y+50), id_str, fill=(255, 255, 255), font=body_font)
        draw.text((x+20, y+85), status, fill=(200, 200, 220), font=code_font)

    # Arrows with labels
    draw.line([(620, 270), (700, 270)], fill=(100, 100, 120), width=3)
    draw.polygon([(700, 270), (690, 264), (690, 276)], fill=(100, 100, 120))
    draw.text((640, 240), "retry_of", fill=(120, 120, 140), font=code_font)

    draw.line([(1120, 270), (1200, 270)], fill=(100, 100, 120), width=3)
    draw.polygon([(1200, 270), (1190, 264), (1190, 276)], fill=(100, 100, 120))
    draw.text((1140, 240), "retry_of", fill=(120, 120, 140), font=code_font)

    # Detail panel
    draw.rectangle([200, 450, 900, 950], fill=(20, 20, 30), outline=(50, 50, 70), width=1)
    draw.text((230, 470), "Original Failure Reason:", fill=(255, 80, 80), font=node_font)
    reasons = [
        "• Image contains visible watermark artifact",
        "• Subject composition violates rule of thirds constraint",
        "• Color temperature outside specified 3200K–5600K range",
    ]
    y = 510
    for r in reasons:
        draw.text((250, y), r, fill=(200, 200, 220), font=code_font)
        y += 30

    draw.text((230, 630), "Remediation Applied:", fill=(255, 200, 0), font=node_font)
    fixes = [
        "• Negative prompt strengthened: 'watermark, logo, text, signature'",
        "• Composition constraint added: 'subject at left third intersection'",
        "• Color temp locked: 'tungsten balanced, 4500K neutral'",
    ]
    y = 670
    for f in fixes:
        draw.text((250, y), f, fill=(200, 200, 220), font=code_font)
        y += 30

    draw.text((230, 790), "Retry Outcome:", fill=(0, 255, 100), font=node_font)
    draw.text((250, 830), "• All issues resolved  ·  Score improved 34 → 91", fill=(200, 200, 220), font=code_font)
    draw.text((250, 865), "• Lineage preserved: original → remediation → retry", fill=(200, 200, 220), font=code_font)

    out = OUTPUT_DIR / "ui_retry_lineage.png"
    img.save(out, quality=95)
    print(f"[ui_lineage] Saved {out}")


# ------------------------------------------------------------------
# 7. UI Mockup: Memory Health Endpoint
# ------------------------------------------------------------------
def make_ui_memory_health():
    W, H = 1920, 1080
    img = Image.new("RGB", (W, H), (15, 15, 22))
    draw = ImageDraw.Draw(img)

    header_font = get_font(28)
    title_font = get_font(24)
    code_font = get_font(16)
    label_font = get_font(14)

    draw.rectangle([0, 0, W, 60], fill=(25, 25, 35))
    draw.text((30, 18), "Forge NPS  ·  Memory Health  ·  GET /api/memory/health", fill=(255, 255, 255), font=header_font)

    # JSON mockup
    json_text = """{
  "total_events": 1847,
  "unknown_event_types": 0,
  "orphan_remediation_events": 0,
  "shots_missing_audit_after_render": 2,
  "fallback_events": 12,
  "event_breakdown": {
    "shot_planned": 312,
    "render_attempt": 298,
    "render_result": 298,
    "audit_started": 298,
    "audit_result": 298,
    "remediation_started": 47,
    "remediation_result": 47,
    "retry_linked": 47,
    "final_outcome": 298
  },
  "integrity_score": 0.989,
  "last_updated": "2026-05-01T20:58:05Z"
}"""

    draw.rectangle([100, 120, 1100, 900], fill=(18, 18, 28), outline=(40, 40, 60), width=1)
    y = 150
    for line in json_text.split("\n"):
        # Simple syntax highlighting
        if '"' in line and (":" in line or "{" in line):
            draw.text((130, y), line, fill=(100, 200, 255), font=code_font)
        elif line.strip().startswith(("0", "1", "2", "3", "4", "5", "6", "7", "8", "9")):
            draw.text((130, y), line, fill=(255, 180, 100), font=code_font)
        else:
            draw.text((130, y), line, fill=(200, 200, 220), font=code_font)
        y += 28

    # Explanation panel
    draw.rectangle([1200, 120, 1800, 900], fill=(18, 18, 28), outline=(40, 40, 60), width=1)
    draw.text((1230, 150), "What This Means", fill=(255, 255, 255), font=title_font)

    explanations = [
        ("total_events: 1847", "Every pipeline stage is recorded."),
        ("unknown_event_types: 0", "All events conform to canonical contract."),
        ("orphan_remediation_events: 0", "Every remediation has a parent shot."),
        ("shots_missing_audit: 2", "2 renders pending audit — normal backlog."),
        ("fallback_events: 12", "12 events from dev fallback — excluded from learning."),
        ("integrity_score: 0.989", "98.9% of events have complete provenance."),
    ]

    y = 210
    for key, val in explanations:
        draw.text((1230, y), key, fill=(0, 255, 150), font=code_font)
        draw.text((1230, y+28), val, fill=(150, 150, 170), font=label_font)
        y += 75

    out = OUTPUT_DIR / "ui_memory_health.png"
    img.save(out, quality=95)
    print(f"[ui_memory] Saved {out}")


# ------------------------------------------------------------------
# 8. UI Mockup: Live Event Stream
# ------------------------------------------------------------------
def make_ui_event_stream():
    W, H = 1920, 1080
    img = Image.new("RGB", (W, H), (15, 15, 22))
    draw = ImageDraw.Draw(img)

    header_font = get_font(28)
    event_font = get_font(15)
    status_font = get_font(14)

    draw.rectangle([0, 0, W, 60], fill=(25, 25, 35))
    draw.text((30, 18), "Forge NPS  ·  Campaign Stream  ·  Campaign #47", fill=(255, 255, 255), font=header_font)
    draw.text((1650, 24), "● LIVE", fill=(0, 255, 100), font=status_font)

    events = [
        ("14:32:01.442", "profile", "Hermes / Campaign Intake starting.", (200, 200, 220)),
        ("14:32:02.891", "profile", "Hermes / Campaign Intake complete. 6 shots planned.", (200, 200, 220)),
        ("14:32:03.105", "kimi", "Kimi: Generating shot list...", (0, 200, 255)),
        ("14:32:04.772", "kimi_raw", "Director plan JSON received. 6 shots, 3 workflows.", (0, 200, 255)),
        ("14:32:05.113", "kimi_plan", "SHOT_001 planned: wide establishing, golden hour...", (0, 200, 255)),
        ("14:32:05.445", "kimi_plan", "SHOT_002 planned: medium portrait, shallow DOF...", (0, 200, 255)),
        ("14:32:06.001", "kimi_review", "Self-check score: 78/100. Coverage adequate. Risks: low.", (0, 200, 255)),
        ("14:32:06.501", "warning", "Kimi review score < 80. Proceeding with caution.", (255, 200, 0)),
        ("14:32:07.112", "compiler", "Hermes compiled SHOT_001 prompt. Skills: prompt_cinematic_lighting", (180, 0, 255)),
        ("14:32:07.445", "compiler", "Hermes compiled SHOT_002 prompt. Skills: prompt_portrait_dof", (180, 0, 255)),
        ("14:32:08.001", "spark", "SHOT_001 render complete. Prompt ID: f2ac90. Time: 1.2s", (255, 140, 0)),
        ("14:32:08.334", "spark", "SHOT_002 render complete. Prompt ID: f2ac91. Time: 1.1s", (255, 140, 0)),
        ("14:32:09.001", "memory", "Recorded render_result for SHOT_001, SHOT_002", (255, 220, 0)),
        ("14:32:09.445", "audit", "VISION auditing SHOT_001...", (0, 255, 100)),
        ("14:32:10.112", "audit", "SHOT_001: PASS (87/100). Issues: minor CA on left edge.", (0, 255, 100)),
        ("14:32:10.445", "audit", "SHOT_002: PASS (91/100). No issues.", (0, 255, 100)),
        ("14:32:11.001", "memory", "Recorded audit_result for SHOT_001, SHOT_002", (255, 220, 0)),
        ("14:32:11.500", "done", "Campaign #47 complete. 6 shots. 6 passed. 0 failed. 0 remediated.", (255, 255, 255)),
    ]

    y = 100
    for ts, typ, msg, color in events:
        # Type badge
        badge_colors = {
            "profile": (100, 100, 120),
            "kimi": (0, 150, 200),
            "kimi_raw": (0, 150, 200),
            "kimi_plan": (0, 150, 200),
            "kimi_review": (0, 150, 200),
            "compiler": (140, 0, 200),
            "spark": (200, 100, 0),
            "audit": (0, 200, 80),
            "memory": (200, 180, 0),
            "warning": (200, 150, 0),
            "done": (255, 255, 255),
        }
        bc = badge_colors.get(typ, (100, 100, 120))
        draw.rounded_rectangle([40, y, 160, y+24], radius=4, fill=bc)
        draw.text((50, y+3), typ.upper(), fill=(255, 255, 255), font=status_font)
        draw.text((180, y+2), ts, fill=(100, 100, 130), font=status_font)
        draw.text((320, y+2), msg, fill=color, font=event_font)
        y += 34

    out = OUTPUT_DIR / "ui_event_stream.png"
    img.save(out, quality=95)
    print(f"[ui_stream] Saved {out}")


# ------------------------------------------------------------------
# 9. UI Mockup: Settings Page
# ------------------------------------------------------------------
def make_ui_settings():
    W, H = 1920, 1080
    img = Image.new("RGB", (W, H), (15, 15, 22))
    draw = ImageDraw.Draw(img)

    header_font = get_font(28)
    section_font = get_font(22)
    body_font = get_font(16)
    label_font = get_font(14)
    code_font = get_font(14)

    draw.rectangle([0, 0, W, 60], fill=(25, 25, 35))
    draw.text((30, 18), "Forge NPS  ·  Settings", fill=(255, 255, 255), font=header_font)

    # Sidebar
    draw.rectangle([0, 60, 300, H], fill=(20, 20, 28))
    items = ["Dashboard", "Campaigns", "Shots", "Audit", "Memory", "Settings"]
    for i, item in enumerate(items):
        y = 100 + i * 50
        color = (0, 200, 255) if item == "Settings" else (150, 150, 170)
        draw.text((30, y), item, fill=color, font=body_font)

    # Settings sections
    sections = [
        ("KIMI / NVIDIA", [
            ("Endpoint", "https://integrate.api.nvidia.com/v1/chat/completions", True),
            ("API Key", "nvapi-••••••••••••••••••••••••••", True),
            ("Instruct Model", "moonshotai/kimi-k2-instruct", True),
            ("Thinking Model", "moonshotai/kimi-k2.6", True),
            ("Test Connection", "✓ Success  ·  Latency: 142ms", True),
        ]),
        ("LM STUDIO", [
            ("Host", "http://100.74.164.1:1234", True),
            ("Chat Model", "qwen3.6-35b-a3b@q6_k", True),
            ("Vision Model", "qwen3.6-35b-a3b@q6_k", True),
            ("Test & Detect", "✓ 2 models available  ·  Vision: ready", True),
        ]),
        ("COMFYUI / SPARK", [
            ("Primary Host", "http://100.112.87.8:8188", True),
            ("Status", "● Online  ·  Queue: 0  ·  Last ping: 2s ago", True),
        ]),
        ("MEDIA", [
            ("Media Root", "/Users/zgbot/Desktop/FORGE_NPS_MEDIA", True),
            ("Disk Usage", "14.2 GB used  ·  1,847 images  ·  23 videos", True),
        ]),
    ]

    x = 340
    y = 100
    for title, items in sections:
        draw.text((x, y), title, fill=(0, 200, 255), font=section_font)
        y += 45
        for label, value, ok in items:
            draw.text((x + 20, y), label, fill=(150, 150, 170), font=label_font)
            status_color = (0, 255, 100) if ok else (255, 80, 80)
            draw.text((x + 250, y), value, fill=status_color, font=code_font)
            y += 32
        y += 20

    out = OUTPUT_DIR / "ui_settings.png"
    img.save(out, quality=95)
    print(f"[ui_settings] Saved {out}")


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------
def main():
    print("=" * 60)
    print("Forge NPS — Media Asset Generator")
    print("=" * 60)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    make_collage()
    make_x_card()
    make_youtube_thumbnail()
    make_architecture_diagram()
    make_ui_shot_provenance()
    make_ui_retry_lineage()
    make_ui_memory_health()
    make_ui_event_stream()
    make_ui_settings()

    print("\n" + "=" * 60)
    print("All assets generated in:")
    print(f"  {OUTPUT_DIR}")
    print("=" * 60)
    for f in sorted(OUTPUT_DIR.glob("*.png")):
        if f.name.startswith(("collage", "x_card", "youtube", "architecture", "ui_")):
            print(f"  ✓ {f.name:40s}  {f.stat().st_size/1024:>8.1f} KB")


if __name__ == "__main__":
    main()
