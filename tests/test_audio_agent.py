import json
from pathlib import Path
import sys

# Add the project root to sys.path so we can import core modules if needed
project_root = str(Path(__file__).resolve().parents[1])
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from agents.audio.audio_agent import AudioAgent

def test_audio_agent_parsing():
    print("--- STARTING AUDIO AGENT TEST ---")
    
    # 1. Define the expected audio directive for SCENE 1 based on pilot_script.md
    # Scene 1 Audio:
    # - Heavy, rhythmic rain hitting metal surfaces.
    # - Distant, muffled electronic synth music from a nearby club.
    # - The high-pitched, electric hum of the data reader activating.
    # - A sudden, sharp digital glitch sound as the connection is made.
    
    shot_id = "SCENE_1_SHOT_001"
    audio_directive = {
        "music_style": "distant, muffled electronic synth",
        "tempo": "rhythmic",
        "sfx_elements": [
            "heavy rain hitting metal surfaces",
            "high-pitched electric hum of data reader",
            "sudden sharp digital glitch"
        ],
        "ambient_soundscape": "heavy rhythmic rain in a narrow alleyway"
    }

    # 2. Initialize Audio Agent (No API key for fallback mode)
    agent = AudioAgent(api_key=None)

    # 3. Generate manifest for the shot
    print(f"Testing shot: {shot_id}")
    manifest = agent.generate_for_shot(shot_id, audio_directive)
    
    print("Generated Manifest:")
    print(json.dumps(manifest, indent=2))

    # 4. Verifications
    # Verify status is manifest_fallback
    assert manifest["status"] == "manifest_fallback", f"Expected status 'manifest_fallback', got {manifest['status']}"
    
    # Verify SFX elements are present and correct
    sfx = manifest["instructions"]["sfx"]
    print(f"Extracted SFX: {sfx}")
    
    expected_sfx_count = 3
    assert len(sfx) == expected_sfx_count, f"Expected {expected_sfx_count} SFX elements, got {len(sfx)}"
    
    # Check if one of the key phrases is in the extracted SFX (partial match for robustness)
    found_rain = any("rain" in s.lower() for s in sfx)
    assert found_rain, "Could not find 'rain' in SFX elements"

    print("\nSUCCESS: Audio Agent correctly parsed and generated manifest.")
    print("--- TEST COMPLETE ---")

if __name__ == "__main__":
    try:
        test_audio_agent_parsing()
    except Exception as e:
        print(f"\nTEST FAILED: {str(e)}")
        sys.exit(1)
