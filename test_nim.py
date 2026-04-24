import asyncio
import pytest
from core.bridge.nim_client import NIMClient

@pytest.mark.asyncio
async def test():
    client = NIMClient('http://localhost:8000')
    print(f"Initial available: {client.is_available}")
    health = await client.check_health()
    print(f"Health check result (expected False if no server): {health}")
    models = await client.list_models()
    print(f"Models: {models}")
    tokens = await client.estimate_tokens('Hello world, this is a test.')
    print(f"Estimated tokens: {tokens}")

if __name__ == "__main__":
    asyncio.run(test())
