import asyncio
from core.dispatch.comfy_client import ComfyUIClient

async def test():
    # Test without live server:
    client = ComfyUIClient("http://localhost:8188")
    assert client.base_url == "http://localhost:8188"
    print("A4 PASS — class instantiates correctly")

if __name__ == "__main__":
    asyncio.run(test())
