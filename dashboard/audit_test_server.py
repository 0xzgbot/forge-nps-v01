import base64
import json
import os
import requests
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_from_directory, Response

# --- EXISTING IMPORTS (Simulated for the purpose of this draft) ---
# In production, these would be actual imports from the project.
# try:
#     from core.hermes.hermes_agent import HermesAgent
#     from core.bridge.nous_hermes_bridge import NousHermesBridge
#     from core.bridge.kimi_bridge import KimiBridge
#     from agents.visual.visual_agent import VisualAgent
# except ImportError as e:
#     pass

app = Flask(__name__, static_folder='static', template_folder='templates')

# --- CONFIGURATION (Simulated) ---
LM_STUDIO_URL = "http://100.74.164.1:1234/v1/chat/completions"
RENDER_DIR = Path("/Users/zgbot/Desktop/forge_nps_v01/dashboard/static/renders/sienna")
ANCHOR_PATH = Path("/Users/zgbot/Desktop/forge_nps_v01/data/character_banks/anchors/elara_vance.jpg")

# Elara Vance Visual Profile for Prompting
ELARA_PROFILE = (
    "Character: Elara Vance. Key visual markers: "
    "platinum crop hair, amber/gold eyes, charcoal flight jacket, "
    "copper piping on seams, ember-glow forearm tattoo."
)

def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def run_audit_for_single_image(image_path, anchor_base64):
    render_base64 = encode_image(image_path)
    
    payload = {
        "model": "gemma-4-26b-a4b-it",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"{ELARA_PROFILE}\n\nCompare Image 1 (the render) against Image 2 (the character reference). "
                                             f"Does the person in the render match Elara's specific features? "
                                             f"Respond ONLY with a valid JSON object: "
                                             f"{{\"is_consistent\": boolean, \"confidence\": float(0.0-1.0), \"issues\": [string]}}"},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{render_base64}"}},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{anchor_base64}"}}
                ]
            }
        ],
        "temperature": 0.1,
        "response_format": {"type": "json_object"}
    }

    try:
        response = requests.post(LM_STUDIO_URL, json=payload, timeout=60)
        response.raise_for_status()
        result = response.json()
        
        # Extract content string and parse JSON
        content_str = result['choices'][0]['message']['content']
        audit_data = json.loads(content_str)
        
        confidence = audit_data.get("confidence", 0.0)
        is_consistent = audit_data.get("is_consistent", False)
        issues = audit_data.get("issues", [])
        
        # Scoring logic
        score = int(confidence * 100)
        status = "PASS" if confidence >= 0.75 and is_consistent else "FAIL"
        
        return {
            "score": score,
            "status": status,
            "issues": issues,
            "is_consistent": is_consistent,
            "confidence": confidence,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {"error": str(e), "status": "ERROR", "score": 0}

@app.route('/api/renders/audit-batch', methods=['POST'])
def audit_batch():
    def generate():
        # 1. Pre-load anchor
        if not ANCHOR_PATH.exists():
            yield json.dumps({"error": "Anchor image not found"})
            return
        anchor_base64 = encode_image(ANCHOR_PATH)

        # 2. Find images
        images = sorted(list(RENDER_DIR.glob("*.png")))
        if not images:
            yield json.dumps({"error": "No PNG renders found in directory"})
            return

        for img_path in images:
            # Perform Audit
            audit_result = run_audit_for_single_image(img_path, anchor_base64)
            
            if "error" in audit_result:
                yield json.dumps({"filename": img_path.name, "error": audit_result["error"]}) + "\n"
                continue

            # 3. Persist Sidecar
            sidecar_path = img_path.with_suffix(".png.json")
            with open(sidecar_path, 'w') as f:
                json.dump(audit_result, f)

            # 4. Stream Result
            yield json.dumps({"filename": img_path.name, **audit_result}) + "\n"

    return Response(generate(), mimetype='application/json')

if __name__ == '__main__':
    print("Mock Audit Server Running...")
    app.run(port=5001)
