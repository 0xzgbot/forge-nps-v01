import unittest
import os
import json
import tempfile
from core.skills.skill_registry import SkillRegistry

class TestSkillRegistry(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory for the registry file
        self.test_dir = tempfile.TemporaryDirectory()
        self.registry_path = os.path.join(self.test_dir.name, "test_registry.json")
        self.registry = SkillRegistry(self.registry_path)

    def tearDown(self):
        # Cleanup the temporary directory
        self.test_dir.cleanup()

    def test_initialization(self):
        """Test that registry initializes correctly and creates default file."""
        self.assertTrue(os.path.exists(self.registry_path))
        with open(self.registry_path, 'r') as f:
            data = json.load(f)
        self.assertEqual(data["version"], "1.0")
        self.assertIn("model_best_practices", data)

    def test_lookup_nonexistent(self):
        """Test lookup returns None for non-existent keys."""
        result = self.registry.lookup("NonExistent", "Category")
        self.assertIsNone(result)

    def test_register_and_lookup(self):
        """Test registration and subsequent lookup."""
        error_cat = "Photometric"
        shot_type = "neon_interior"
        original_prompt = "a dark room with neon lights"
        fix_applied = "strict color grading, #FF00FF neon accents only, no warm bleed"
        kimi_reasoning = "Model defaults to warm ambient in dark scenes..."

        # First registration
        self.registry.register_fix(error_cat, shot_type, original_prompt, fix_applied, True, kimi_reasoning)
        
        result = self.registry.lookup(error_cat, shot_type)
        self.assertIsNotNone(result)
        self.assertEqual(result["confirmations"], 1)
        self.assertEqual(result["prompt_modifier"], fix_applied)

        # Second registration (incrementing confirmations)
        self.registry.register_fix(error_cat, shot_type, original_prompt, fix_applied, True, kimi_reasoning)
        result = self.registry.lookup(error_cat, shot_type)
        self.assertEqual(result["confirmations"], 2)

    def test_registration_failure_case(self):
        """Test that unsuccessful fixes are not registered."""
        error_cat = "Failure"
        shot_type = "test"
        self.registry.register_fix(error_cat, shot_type, "p", "f", False, "r")
        result = self.registry.lookup(error_cat, shot_type)
        self.assertIsNone(result)

    def test_get_best_practices(self):
        """Test retrieving model best practices."""
        # The default registry has FLUX, LTX, Wan_2.1
        flux_practices = self.registry.get_best_practices("FLUX")
        self.assertIn("cinematic color grading", flux_practices)
        
        unknown_practices = self.registry.get_best_practices("UnknownModel")
        self.assertEqual(unknown_practices, [])

    def test_export_session_learnings(self):
        """Test exporting session learnings."""
        error_cat = "StableFix"
        shot_type = "TypeA"
        fix = "Good fix"
        reasoning = "Reason"
        
        # Register 3 times to exceed the stability threshold (>2)
        for _ in range(3):
            self.registry.register_fix(error_cat, shot_type, "p", fix, True, reasoning)
        
        learnings = self.registry.export_session_learnings("session_123")
        self.assertEqual(learnings["session_id"], "session_123")
        self.assertEqual(learnings["total_stable_fixes"], 1)

if __name__ == "__main__":
    unittest.main()
