import os
from typing import Any, Dict, Optional

class ConfigManager:
    """
    Centralized configuration for Cinesmith.
    Handles loading from .env and provides typed access to API credentials.
    """
    def __init__(self, env_path: str = ".env"):
        self.env_path = os.path.abspath(env_path)
        from dotenv import load_dotenv
        load_dotenv(self.env_path)

    def get_nous_endpoint(self) -> str:
        return os.getenv("NOUS_ENDPOINT", "")

    def get_nous_api_key(self) -> str:
        return os.getenv("NOUS_API_KEY", "")

    def get_nim_endpoint(self) -> str:
        return os.getenv("NIM_ENDPOINT", "")

    def get_kimi_api_key(self) -> str:
        return os.getenv("KIMI_API_KEY", "")

    def get_openrouter_api_key(self) -> str:
        return os.getenv("OPENROUTER_API_KEY", "")

    def get_openrouter_endpoint(self) -> str:
        return os.getenv("OPENROUTER_ENDPOINT", "")

    def get_comfyui_primary(self) -> str:
        return os.getenv("COMFYUI_PRIMARY", "")

    def get(self, key: str, default: Any = None) -> Any:
        """Generic accessor for configuration values (used by Orchestrator)."""
        # For the purpose of demo/orchestration compatibility
        if key == "DIRECTOR_SCHEMA":
            return None # In a real app this might return a Pydantic class or schema dict
        return os.getenv(key, default)

    def validate(self) -> list[str]:
        """Check for missing critical configurations."""
        missing = []
        if not self.get_nous_api_key() and not self.get_kimi_api_key():
            missing.append("NOUS_API_KEY or KIMI_API_KEY")
        if not self.get_comfyui_primary():
            missing.append("COMFYUI_PRIMARY")
        return missing

if __name__ == "__main__":
    cm = ConfigManager()
    missing = cm.validate()
    if missing:
        print(f"Missing configurations: {missing}")
    else:
        print("All critical configurations present.")
