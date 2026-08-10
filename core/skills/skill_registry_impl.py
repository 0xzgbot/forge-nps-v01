
from typing import Dict, Any, Optional

class InMemorySkillRegistry:
    def __init__(self):
        self.registry = {}

    async def register_fix(self, error_category: str, shot_type: str, original_prompt: str, fix_applied: str, success: bool, kimi_reasoning: str):
        key = f"{error_category}:{shot_type}"
        if key not in self.registry:
            self.registry[key] = []
        self.registry[key].append({
            "original_prompt": original_prompt,
            "fix_applied": fix_applied,
            "success": success,
            "kimi_reasoning": kimi_reasoning
        })

    def lookup(self, error_category: str, shot_type: str) -> Optional[Dict[str, Any]]:
        key = f"{error_category}:{shot_type}"
        if key in self.registry and len(self.registry[key]) > 0:
            return self.registry[key][-1]
        return None
