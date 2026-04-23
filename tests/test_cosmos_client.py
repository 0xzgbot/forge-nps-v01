import unittest
from unittest.mock import AsyncMock, patch, MagicMock
import json
import httpx
import asyncio
from core.bridge.cosmos_client import (
    CosmosClient, 
    CosmosClientError, 
    CosmosClientTimeoutError, 
    CosmosClientConnectionError
)

class TestCosmosClient(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.endpoint = "http://fake-cosmos-nim.com/v1/chat/completions"
        self.api_key = "fake-api-key"
        self.client = CosmosClient(self.endpoint, self.api_key)

    async def test_reason_success_json(self):
        """Test successful response when model returns JSON."""
        mock_response_data = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps({
                            "reasoning_trace": "The character is in the wrong location.",
                            "conclusion": "Action: Move character to Forest."
                        })
                    }
                }
            ]
        }

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = MagicMock(
                spec=httpx.Response,
                status_code=200
            )
            mock_post.return_value.json.return_value = mock_response_data
            mock_post.return_value.raise_for_status = MagicMock()

            result = await self.client.reason("System", "User")

            self.assertEqual(result["reasoning_trace"], "The character is in the wrong location.")
            self.assertEqual(result["conclusion"], "Action: Move character to Forest.")

    async def test_reason_success_text_markers(self):
        """Test successful response when model returns text with REASONING/CONCLUSION markers."""
        mock_content = "REASONING:\nI think this is right.\nCONCLUSION:\nConfirmed."
        mock_response_data = {
            "choices": [
                {
                    "message": {
                        "content": mock_content
                    }
                }
            ]
        }

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = MagicMock(
                spec=httpx.Response,
                status_code=200
            )
            mock_post.return_value.json.return_value = mock_response_data
            mock_post.return_value.raise_for_status = MagicMock()

            result = await self.client.reason("System", "User")

            self.assertEqual(result["reasoning_trace"], "I think this is right.")
            self.assertEqual(result["conclusion"], "Confirmed.")

    async def test_timeout_retry_and_fail(self):
        """Test that timeout triggers retries and eventually raises CosmosClientTimeoutError."""
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = httpx.TimeoutException("Timed out")

            # Set max_retries to 1 for faster testing
            self.client.max_retries = 1
            self.client.base_delay = 0.01 # Don't wait much in tests

            with self.assertRaises(CosmosClientTimeoutError):
                await self.client.reason("System", "User")
            
            # Check if it was called max_retries + 1 times (initial + retry)
            self.assertEqual(mock_post.call_count, 2)

    async def test_connection_error(self):
        """Test connection error handling."""
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = httpx.ConnectError("Failed to connect")

            self.client.max_retries = 0 # No retries for this test case speed

            with self.assertRaises(CosmosClientConnectionError):
                await self.client.reason("System", "User")

    async def test_http_status_error_400(self):
        """Test that 4xx errors (except 429) do not retry."""
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_response = MagicMock(spec=httpx.Response)
            mock_response.status_code = 400
            mock_response.text = "Bad Request"
            mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "Client error", request=MagicMock(), response=mock_response
            )
            mock_post.return_value = mock_response

            self.client.max_retries = 3

            with self.assertRaises(CosmosClientError):
                await self.client.reason("System", "User")
            
            # Should NOT retry on 400
            self.assertEqual(mock_post.call_count, 1)

if __name__ == "__main__":
    unittest.main()
