from core.prompts.director_system_prompt import DIRECTOR_SYSTEM_PROMPT, PREDICTION_ADDENDUM

def test_prompts():
    print("--- Testing Kimi Director Prompt v2 ---")
    
    # Test DIRECTOR_SYSTEM_PROMPT
    if isinstance(DIRECTOR_SYSTEM_PROMPT, str) and len(DIRECTOR_SYSTEM_PROMPT.strip()) > 0:
        print("[PASS] DIRECTOR_SYSTEM_PROMPT is a non-empty string.")
    else:
        print("[FAIL] DIRECTOR_SYSTEM_PROMPT is empty or not a string.")
        exit(1)

    # Test PREDICTION_ADDENDUM
    if isinstance(PREDICTION_ADDENDUM, str) and len(PREDICTION_ADDENDUM.strip()) > 0:
        print("[PASS] PREDICTION_ADDENDUM is a non-empty string.")
    else:
        print("[FAIL] PREDICTION_ADDENDUM is empty or not a string.")
        exit(1)

    print("\n--- Prompt Content Preview ---")
    print(f"DIRECTOR_SYSTEM_PROMPT (first 50 chars): {DIRECTOR_SYSTEM_PROMPT[:50]}...")
    print(f"PREDICTION_ADDENDUM (first 50 chars): {PREDICTION_ADDENDUM[:50]}...")
    print("\nAll tests passed successfully.")

if __name__ == "__main__":
    test_prompts()
