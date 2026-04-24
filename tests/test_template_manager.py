import sys
from pathlib import Path

# Ensure the project root is in sys.path for imports to work correctly
project_root = "/Users/zgbot/Desktop/forge_nps_v01"
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from core.templates.template_manager import TemplateManager

def test_template_manager():
    print("--- Starting Test: Template Manager ---")
    
    try:
        # Initialize manager
        manager = TemplateManager()
        
        # Define overlays (shot data)
        overlays = {
            "camera_angle": "low-angle",
            "subject": "cyberpunk warrior",
            "lighting": "neon-drenched"
        }
        
        print(f"Testing template: 'test_template' with overlays: {overlays}")
        
        # Retrieve and process template
        result = manager.get_template("test_template", overlays=overlays)
        
        # Verify results
        expected_prompt = "A low-angle shot of a cyberpunk warrior in neon-drenched lighting."
        actual_prompt = result.get("prompt_base")
        
        print(f"Resulting prompt: {actual_prompt}")
        
        assert actual_prompt == expected_prompt, f"Expected '{expected_prompt}', but got '{actual_prompt}'"
        print("SUCCESS: Prompt injection matched expected value.")

        assert result.get("project_name") == "Test Project", "Static fields were corrupted"
        print("SUCCESS: Static fields preserved.")

        print("--- ALL TESTS PASSED ---")

    except Exception as e:
        print(f"ERROR during testing: {e}")
        import traceback
        traceback.print_exc()
        raise

if __name__ == "__main__":
    success = test_template_manager()
    if not success:
        sys.exit(1)
