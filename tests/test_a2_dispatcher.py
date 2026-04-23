import pytest
import asyncio
from core.dispatch.dispatcher import ComfyDispatcher

@pytest.mark.asyncio
async def test():
    # Test with a mock host as specified in the INTEGRATION_PLAN.md requirements
    d = ComfyDispatcher(["http://localhost:8188"])
    
    # Without a live server, verify round-robin logic:
    # First call should return the first host
    host1 = d._round_robin_host()
    assert host1 == "http://localhost:8188"
    
    # Second call (if there was another) would rotate, 
    # but since we only have one in the list passed to constructor, it wraps around.
    host2 = d._round_robin_host()
    assert host2 == "http://localhost:8188"
    
    print("A2 PASS")

if __name__ == "__main__":
    asyncio.run(test())
