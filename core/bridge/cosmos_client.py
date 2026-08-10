import os
import json
import time
import logging
import asyncio
import httpx
from typing import Dict, Any, Optional, List

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("CosmosClient")

class CosmosClientError(Exception):
    """Base exception for CosmosClient errors."""
    pass

class CosmosClientTimeoutError(CosmosClientError):
    """Raised when the request to the Cosmos endpoint times out."""
    pass

class CosmosClientConnectionError(CosmosClientError):
    """Raised when there is a connection error with the Cosmos endpoint."""
    pass

class CosmosClient:
    """
    Asynchronous client for communicating with Cosmos reasoning models via NVIDIA NIM endpoints.
    Designed for high-context 'Physical Audits' and complex reasoning tasks.
    """

    def __init__(
        self, 
        endpoint_url: str, 
        api_key: str, 
        model_name: str = "nvidia/cosmos-reasoning",
        max_retries: int = 3,
        base_delay: float = 1.0
    ):
        self.endpoint_url = endpoint_url.rstrip("/")
        self.api_key = api_key
        self.model_name = model_name
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

    async def reason(
        self, 
        system_prompt: str, 
        user_input: str, 
        context_files: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Performs a reasoning task with the Cosmos model.
        
        Args:
            system_prompt: The system instruction defining the persona/task.
            user_input: The core question or instruction from the user.
            context_files: Optional list of file paths to include in the context.

        Returns:
            A dictionary containing 'reasoning_trace' and 'conclusion'.
        """
        context_text = ""
        if context_files:
            for file_path in context_files:
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        context_text += f"\n--- FILE: {os.path.basename(file_path)} ---\n{f.read()}\n"
                except Exception as e:
                    logger.error(f"CosmosClient: Failed to read context file {file_path}: {e}")

        full_user_input = f"{context_text}\n\n{user_input}" if context_text else user_input
        
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": full_user_input}
            ],
            "temperature": 0.1, # Low temperature for reasoning consistency
            "stream": False
        }

        return await self._execute_with_retry(payload)

    async def _execute_with_retry(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Executes the HTTP request with exponential backoff."""
        last_exception = None
        
        for attempt in range(self.max_retries + 1):
            start_time = time.perf_counter()
            try:
                async with httpx.AsyncClient(timeout=300.0) as client:
                    logger.info(f"CosmosClient: Sending request (Attempt {attempt + 1}/{self.max_retries + 1})...")
                    response = await client.post(
                        self.endpoint_url, 
                        headers=self.headers, 
                        json=payload
                    )
                    latency = time.perf_counter() - start_time
                    
                    # Log latency and approximate token usage (placeholder for actual API response field if available)
                    logger.info(f"CosmosClient: Request completed in {latency:.2f}s")

                    response.raise_for_status()
                    data = response.json()

                    # Extract content - assuming standard OpenAI/NIM format
                    content_str = data['choices'][0]['message']['content']
                    
                    # The requirement states we return a dictionary containing 'reasoning_trace' and 'conclusion'.
                    # Since Cosmos models often output reasoning as part of the text or in specific fields, 
                    # we attempt to parse it. If it's raw text, we split/format it.
                    return self._parse_cosmos_response(content_str)

            except httpx.TimeoutException as e:
                last_exception = CosmosClientTimeoutError(f"Request timed out: {e}")
                logger.warning(f"CosmosClient: Timeout on attempt {attempt + 1}")
            except httpx.ConnectError as e:
                last_exception = CosmosClientConnectionError(f"Connection failed: {e}")
                logger.warning(f"CosmosClient: Connection error on attempt {attempt + 1}")
            except httpx.HTTPStatusError as e:
                # Don't retry on 4xx client errors, only 5xx or certain rate limits
                if 400 <= e.response.status_code < 500 and e.response.status_code not in [429]:
                    logger.error(f"CosmosClient: Client error {e.response.status_code}: {e.response.text}")
                    raise CosmosClientError(f"Client Error: {e.response.text}") from e
                last_exception = CosmosClientError(f"HTTP Error {e.response.status_code}: {e.response.text}")
                logger.warning(f"CosmosClient: Server error {e.response.status_code} on attempt {attempt + 1}")
            except Exception as e:
                last_exception = CosmosClientError(f"Unexpected error: {str(e)}")
                logger.error(f"CosmosClient: Unexpected error: {e}")
                raise

            if attempt < self.max_retries:
                delay = self.base_delay * (2 ** attempt)
                logger.info(f"CosmosClient: Retrying in {delay:.2f}s...")
                await asyncio.sleep(delay)

        raise last_exception

    def _parse_cosmos_response(self, content: str) -> Dict[str, Any]:
        """
        Parses the raw model output into structured reasoning and conclusion.
        Expects a format like:
        REASONING:
        ...trace...
        CONCLUSION:
        ...conclusion...
        Or it might be valid JSON.
        """
        # 1. Try parsing as JSON first (highly recommended for structured outputs)
        try:
            data = json.loads(content)
            if "reasoning_trace" in data and "conclusion" in data:
                return data
            # If it's a dict but missing keys, try to find them or wrap it
            return {
                "reasoning_trace": data.get("reasoning", ""),
                "conclusion": data.get("conclusion", ""),
                "raw": data
            }
        except json.JSONDecodeError:
            pass

        # 2. Fallback to parsing text-based markers
        # This is common for "Chain of Thought" models that don't use JSON mode.
        reasoning_marker = "REASONING:"
        conclusion_marker = "CONCLUSION:"
        
        content_upper = content.upper()
        
        if reasoning_marker in content_upper and conclusion_marker in content_upper:
            try:
                r_idx = content_upper.find(reasoning_marker) + len(reasoning_marker)
                c_idx = content_upper.find(conclusion_marker)
                
                trace = content[r_idx:c_idx].strip()
                conclusion = content[c_idx + len(conclusion_marker):].strip()
                
                return {
                    "reasoning_trace": trace,
                    "conclusion": conclusion
                }
            except Exception as e:
                logger.warning(f"CosmosClient: Failed to parse markers: {e}")

        # 3. Final fallback: treat whole content as conclusion if no structure found
        return {
            "reasoning_trace": "No explicit reasoning trace detected.",
            "conclusion": content.strip()
        }
