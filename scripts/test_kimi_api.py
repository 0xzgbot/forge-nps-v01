#!/usr/bin/env python3
"""Quick test to verify Kimi K2.5 API works end-to-end."""
import asyncio
import sys
sys.path.insert(0, '~/Desktop/forge_nps_v01')

from core.bridge.config_manager import ConfigManager
from core.bridge.kimi_bridge import KimiBridge

async def main():
    cm = ConfigManager('~/Desktop/forge_nps_v01/.env')
    missing = cm.validate()
    if missing:
        print(f"Missing config: {missing}")
        return

    bridge = KimiBridge(
        endpoint_url=cm.get_nim_endpoint(),
        api_key=cm.get_kimi_api_key(),
        config_manager=cm
    )

    result = await bridge.direct(
        system_prompt="You are a creative assistant. Write a one-sentence tagline.",
        user_input="Luxury coffee brand called Summit Coffee. Output ONLY the tagline.",
        schema=None
    )
    print(f"Result type: {type(result)}")
    print(f"Result: {result}")

if __name__ == "__main__":
    asyncio.run(main())
