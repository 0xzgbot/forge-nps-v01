import json
import os
from typing import Dict, Any, List

import requests

class KimiSemanticAudit:
    """
    Kimi-Driven Semantic Audit module for brand consistency checking.
    Uses the Kimi LLM API to validate marketing assets against brand guidelines.
    """

    def __init__(self, api_url: str = ""):
        api_url = api_url or os.getenv("KIMI_SEMANTIC_AUDIT_URL", "http://localhost:1244/v1")
        self.api_url = api_url
        self.chat_endpoint = f"{self.api_url}/chat/completions"
        self.model_name = os.getenv("KIMI_SEMANTIC_AUDIT_MODEL", "kimi-model")

    def audit(self, asset_content: str, brand_guidelines: str) -> Dict[str, Any]:
        """
        Performs a semantic audit of the asset content against provided brand guidelines.
        """
        prompt = f"""
        You are an expert Brand Auditor. 
        Your task is to perform a rigorous semantic audit of a marketing asset to ensure it aligns perfectly with the provided Brand Guidelines.

        BRAND GUIDELINES:
        {brand_guidelines}

        ASSET CONTENT TO AUDIT:
        {asset_content}

        AUDIT REQUIREMENTS:
        1. Check for tone and voice consistency (e.g., is it too informal? Too aggressive?).
        2. Check for vocabulary alignment (does it use forbidden words or preferred terminology?).
        3. Check for semantic meaning (does the message accurately reflect the brand's core values and positioning?).
        4. Identify any contradictions between the asset and the guidelines.

        OUTPUT FORMAT:
        You must return your response in valid JSON format with the following structure:
        {{
            "consistency_score": <integer 0-100>,
            "audit_results": {{
                "tone_voice": {{
                    "status": "pass/fail",
                    "feedback": "<detailed feedback>"
                }},
                "vocabulary": {{
                    "status": "pass/fail",
                    "feedback": "<detailed feedback>"
                }},
                "brand_positioning": {{
                    "status": "pass/fail",
                    "feedback": "<detailed feedback>"
                }}
            }},
            "critical_violations": [<list of strings>],
            "improvement_suggestions": [<list of strings>]
        }}
        """

        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": "You are a precise Brand Consistency Auditor. You output only JSON."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"}
        }

        try:
            response = requests.post(self.chat_endpoint, json=payload, timeout=30)
            response.raise_for_status()
            result = response.json()
            
            # Extract the content from the LLM response
            content_str = result['choices'][0]['message']['content']
            return json.loads(content_str)

        except requests.exceptions.RequestException as e:
            return {
                "error": f"API request failed: {str(e)}",
                "consistency_score": 0,
                "audit_results": {},
                "critical_violations": ["API Connection Error"],
                "improvement_suggestions": []
            }
        except json.JSONDecodeError as e:
            return {
                "error": f"Failed to parse LLM JSON response: {str(e)}",
                "consistency_score": 0,
                "audit_results": {},
                "critical_violations": ["Parsing Error"],
                "improvement_suggestions": []
            }
        except Exception as e:
            return {
                "error": f"An unexpected error occurred: {str(e)}",
                "consistency_score": 0,
                "audit_results": {},
                "critical_violations": ["Unexpected Error"],
                "improvement_suggestions": []
            }

if __name__ == "__main__":
    # Quick test/demo
    auditor = KimiSemanticAudit()
    
    guidelines = "Tone: Professional, inspiring, and minimalist. Target Audience: High-net-worth individuals. Keywords: Excellence, Timeless, Precision."
    asset = "Hey guys! Check out our super cool new watch that's totally awesome and cheap!"
    
    print("Running Semantic Audit...")
    report = auditor.audit(asset, guidelines)
    print(json.dumps(report, indent=4))
