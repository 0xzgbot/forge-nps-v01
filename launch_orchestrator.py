
import sys
import asyncio
from pathlib import Path

# Ensure project root is in path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from core.orchestrator.cinesmith_orchestrator import CinesmithOrchestrator
from core.bridge.config_manager import ConfigManager

async def main():
    print("--- CINESMITH NPS LAUNCHER STARTING ---")
    cfg = ConfigManager()
    orch = CinesmithOrchestrator(config_manager=cfg, session_id="hackathon_demo_001")
    
    # Using the paths identified in the plan
    script = "scripts/demo/pilot_script.md"
    lore = ["data/lore_bible/world_bible.md"]
    
    result = await orch.run(script, lore)
    print("\nFinal Session Summary:")
    import json
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    asyncio.run(main())
