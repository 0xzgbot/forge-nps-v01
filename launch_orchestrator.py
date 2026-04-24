
import sys
import os
import asyncio

# Ensure project root is in path
PROJECT_ROOT = "/Users/zgbot/Desktop/forge_nps_v01"
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from core.orchestrator.forge_orchestrator import ForgeOrchestrator
from core.bridge.config_manager import ConfigManager

async def main():
    print("--- FORGE NPS LAUNCHER STARTING ---")
    cfg = ConfigManager()
    orch = ForgeOrchestrator(cfg, "hackathon_demo_001")
    
    # Using the paths identified in the plan
    script = "scripts/demo/pilot_script.md"
    lore = ["data/lore_bible/world_bible.md"]
    
    result = await orch.run(script, lore)
    print("\nFinal Session Summary:")
    import json
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    asyncio.run(main())
