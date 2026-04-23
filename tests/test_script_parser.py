import sys
import os
import json

# Add project root to path to ensure imports work
project_root = "~/Desktop/forge_nps"
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from core.script.script_parser import ScriptParser

def test_script_parser():
    print("--- Running J10 Verification Test ---")
    parser = ScriptParser()
    script_path = "~/Desktop/forge_nps_v01/scripts/demo/pilot_script.md"
    
    try:
        parsed = parser.parse(script_path)
        print("[PASS] Successfully parsed the script.")
        
        # Verify Title
        print(f"[CHECK] Title: {parsed['title']}")
        assert "NEON NOIR" in parsed['title']
        
        # Verify Character Registry (Requirement: Elara Vance is in registry)
        # The parser might extract 'Elara Vance' or 'ELARA VANCE'
        found_elara = any("Elara Vance" in c or "ELARA VANCE" in c for c in parsed['character_registry'])
        print(f"[CHECK] Character Registry: {parsed['character_registry']}")
        assert found_elara, "Elara Vance not found in character registry!"
        print("[PASS] Elara Vance verified in registry.")

        # Verify Audio Cues (Requirement: Audio cues are extracted)
        all_audio_cues = []
        for scene in parsed['scenes']:
            all_audio_cues.extend(scene['audio_cues'])
        
        print(f"[CHECK] Total Audio Cues Found: {len(all_audio_cues)}")
        print(f"First few cues: {all_audio_cues[:3]}")
        assert len(all_audio_cues) > 0, "No audio cues were extracted!"
        
        # Check a specific cue from the script
        found_cue = any("digital glitch sound" in cue.lower() for cue in all_audio_cues)
        assert found_cue, "Specific audio cue 'digital glitch sound' not found!"
        print("[PASS] Audio cues verified.")

        # Verify Continuity Requirements
        continuity = parser.extract_character_continuity_requirements(parsed)
        print(f"[CHECK] Continuity Requirements: {len(continuity)} generated.")
        assert len(continuity) > 0, "No continuity requirements generated!"
        print("[PASS] Continuity requirements verified.")

        print("\n--- ALL TESTS PASSED SUCCESSFULLY ---")

    except AssertionError as e:
        print(f"\n[FAIL] Assertion Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[FAIL] An unexpected error occurred: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    test_script_parser()
