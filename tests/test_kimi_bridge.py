import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pydantic import BaseModel, Field
import json
import sys
from pathlib import Path

# Add the project root to sys.path so we can import modules correctly
sys.path.append(str(Path(__file__).resolve().parents[1]))

from core.bridge.kimi_bridge import KimiBridge, StrictSchemaGuard

class DummySchema(BaseModel):
    name: str
    age: int
    tags: list[str] = Field(default_factory=list)

@pytest.mark.asyncio
async def test_strict_schema_guard_validation():
    valid_data = {"name": "Alice", "age": 30, "tags": ["engineer"]}
    validated = StrictSchemaGuard.validate(valid_data, DummySchema)
    assert validated.name == "Alice"
    assert validated.age == 30
    assert "engineer" in validated.tags

@pytest.mark.asyncio
async def test_strict_schema_guard_json_string():
    valid_json = '{"name": "Bob", "age": 25, "tags": ["designer"]}'
    validated = StrictSchemaGuard.validate(valid_json, DummySchema)
    assert validated.name == "Bob"

@pytest.mark.asyncio
async def test_strict_schema_guard_invalid_json():
    # Pydantic will raise a ValidationError if the type is wrong after parsing JSON
    invalid_json = '{"name": "Charlie", "age": "not_an_int"}'
    with pytest.raises(Exception):
        StrictSchemaGuard.validate(invalid_json, DummySchema)

@pytest.mark.asyncio
async def test_kimi_bridge_direct_success():
    # Mock httpx response
    mock_response_content = json.dumps({"name": "Success", "age": 10, "tags": []})
    mock_response_data = {
        "choices": [
            {
                "message": {
                    "content": mock_response_content
                }
            }
        ]
    }

    mock_config = MagicMock()
    bridge = KimiBridge(endpoint_url="http://fake-api.com", api_key="fake-key", config_manager=mock_config)
    
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        result = await bridge.direct(
            system_prompt="You are a helpful assistant.",
            user_input="Respond in JSON.",
            schema=DummySchema
        )

        assert result["name"] == "Success"
        assert result["age"] == 10

@pytest.mark.asyncio
async def test_kimi_bridge_retry_on_error():
    # First response is invalid, second is valid
    invalid_content = '{"name": "Fail", "age": "wrong_type"}'
    valid_content = '{"name": "Fixed", "age": 20, "tags": ["repaired"]}'

    responses = [
        {
            "choices": [{"message": {"content": invalid_content}}]
        },
        {
            "choices": [{"message": {"content": valid_content}}]
        }
    ]

    mock_config = MagicMock()
    bridge = KimiBridge(endpoint_url="http://fake-api.com", api_key="fake-key", config_manager=mock_config)

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_responses = []
        for resp_data in responses:
            m = MagicMock()
            m.status_code = 200
            m.json.return_value = resp_data
            m.raise_for_status = MagicMock()
            mock_responses.append(m)
        
        mock_post.side_effect = mock_responses

        result = await bridge.direct(
            system_prompt="You are a helpful assistant.",
            user_input="Respond in JSON.",
            schema=DummySchema
        )

        assert result["name"] == "Fixed"
        assert len(mock_responses) == 2 # Verified it retried
