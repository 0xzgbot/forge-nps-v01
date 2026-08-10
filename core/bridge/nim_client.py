import logging
import time
from typing import List

import httpx

logger = logging.getLogger(__name__)

class NIMClient:
    """
    Client for interacting with NVIDIA NIM (NVIDIA Inference Microservices) endpoints.
    Provides health checks, model listing, and token estimation capabilities.
    """

    def __init__(self, endpoint: str, timeout: float = 10.0):
        """
        Initialize the NIM client.

        Args:
            endpoint: The base URL of the NIM service (e.g., 'http://localhost:8000').
            timeout: Request timeout in seconds.
        """
        self.endpoint = endpoint.rstrip('/')
        self.timeout = timeout
        self._is_available_cached = False
        self._last_health_check = 0.0
        self._cache_ttl = 30.0  # Cache availability status for 30 seconds

    @property
    def is_available(self) -> bool:
        """
        Returns the cached availability status of the NIM service.
        """
        return self._is_available_cached

    async def check_health(self) -> bool:
        """
        Performs a health check via the /health endpoint.
        Updates the cached availability status.

        Returns:
            True if the service is healthy, False otherwise.
        """
        url = f"{self.endpoint}/health"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url)
                is_healthy = response.status_code == 200
                
                self._is_available_cached = is_healthy
                self._last_health_check = time.time()
                return is_healthy
        except Exception as e:
            logger.error(f"NIM health check failed at {url}: {e}")
            self._is_available_cached = False
            self._last_health_check = time.time()
            return False

    async def list_models(self) -> List[str]:
        """
        Retrieves the list of available models via the /v1/models endpoint.

        Returns:
            A list of model IDs. Returns an empty list if the request fails.
        """
        url = f"{self.endpoint}/v1/models"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url)
                response.raise_for_status()
                data = response.json()
                # NIM typically follows OpenAI model listing format: {"data": [{"id": "model-name"}, ...]}
                return [model["id"] for model in data.get("data", [])]
        except Exception as e:
            logger.error(f"Failed to list NIM models at {url}: {e}")
            return []

    async def estimate_tokens(self, text: str) -> int:
        """
        Estimates the number of tokens in a given text string.
        Since exact tokenization depends on the specific model loaded in NIM, 
        this uses a heuristic approach (approx 4 characters per token).

        Args:
            text: The input text to estimate.

        Returns:
            Estimated token count.
        """
        if not text:
            return 0
        # Heuristic: ~4 chars per token for English text
        return max(1, len(text) // 4)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass
