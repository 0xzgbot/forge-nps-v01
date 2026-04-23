import unittest
from pathlib import Path
from core.prompts.cinematic_engine import CinematicEngine
from core.prompts.library_loader import LibraryLoader

class TestCinematicEngine(unittest.TestCase):
    def setUp(self):
        # Use the actual lighting bank for testing
        self.lighting_bank = "/Users/zgbot/Desktop/forge_nps/data/character_banks/lighting_bank.txt"
        self.engine = CinematicEngine(self.lighting_bank)
        self.loader = LibraryLoader("/Users/zgbot/Desktop/forge_nps/data/prompt_libraries/")

    def test_enhancement_logic(self):
        base_prompt = "a cat"
        params = {
            "lens": "85mm lens, f/1.4",
            "lighting": "golden hour",
            "camera_motion": "low angle shot",
            "color_grade": "teal and orange"
        }
        enhanced = self.engine.enhance(base_prompt, params)
        
        # Check if it contains the core components
        self.assertIn("a cat", enhanced)
        self.assertIn("85mm lens, f/1.4", enhanced)
        self.assertIn("golden hour", enhanced)
        self.assertIn("low angle shot", enhanced)
        self.assertIn("teal and orange color grading", enhanced)
        # Check for the "A detailed shot of" prefix added for short prompts
        self.assertTrue(enhanced.startswith("A detailed shot of"))

    def test_library_integration(self):
        # We need a known prompt in the library for this to work.
        # Based on Golden_Hour.json, title is "Golden_Hour Prompt Pack"
        params = {
            "lens": "35mm lens, f/1.8",
            "lighting": "moonlight"
        }
        
        try:
            # Try to get prompt by title
            result = self.loader.get_prompt("Golden_Hour Prompt Pack", cinematic_params=params, cinematic_engine=self.engine)
            self.assertIn("enhanced_prompt", result)
            self.assertIn("35mm lens, f/1.8", result["enhanced_prompt"])
            print(f"DEBUG: Enhanced prompt from library: {result['enhanced_prompt']}")
        except ValueError as e:
            self.fail(f"Prompt 'Golden_Hour Prompt Pack' not found in library: {e}")

if __name__ == "__main__":
    unittest.main()
