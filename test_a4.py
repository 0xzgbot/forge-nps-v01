import asyncio
from core.dispatch.comfy_client import ComfyUIClient

async def test():
    # Test without live server:
    client = ComfyUIClient("http://100.74.164.1:8188")
    assert client.base_url == "http://100.74.164.1:8188"
    print("A4 PASS — class instantiates correctly")

if __name__ == "__main__":
    asyncio.run(test())
