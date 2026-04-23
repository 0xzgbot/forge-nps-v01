import time
import random
import logging
from typing import Callable, Any, TypeVar, List

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ResilienceLayer")

T = TypeVar('T')

class ForgeNPSException(Exception):
    """Base exception for all Forge NPS system errors."""
    pass

class TransientError(ForgeNPSException):
    """Errors that are likely temporary (e.g., API timeout, rate limit). 
    These should trigger a retry logic."""
    pass

class FatalError(ForgeNPSException):
    """Errors that represent unrecoverable failures (e.g., invalid credentials, file not found).
    These should terminate the current process/loop immediately."""
    pass

class ErrorHandler:
    """
    The Resilience Specialist component of Forge NPS.
    Provides robust error handling with exponential backoff and retry logic 
    to ensure high-uptime for long-running production pipelines.
    """

    def __init__(self, max_retries: int = 3, base_delay: float = 2.0, max_delay: float = 30.0):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay

    def execute_with_retry(self, func: Callable[..., T], *args, **kwargs) -> T:
        """
        Executes a function with exponential backoff for TransientErrors.
        If a FatalError is encountered, it raises immediately.
        """
        retries = 0
        while retries <= self.max_retries:
            try:
                return func(*args, **kwargs)
            except TransientError as e:
                retries += 1
                if retries > self.max_retries:
                    logger.error(f"Max retries ({self.max_retries}) reached. Abandoning operation.")
                    raise FatalError(f"Operation failed after {self.max_retries} retries due to: {e}") from e

                # Calculate exponential backoff with jitter
                delay = min(self.max_delay, self.base_delay * (2 ** (retries - 1)))
                jitter = delay * random.uniform(0, 0.1)
                total_delay = delay + jitter

                logger.warning(f"Transient error detected: {e}. Retrying in {total_delay:.2f}s... (Attempt {retries}/{self.max_retries})")
                time.sleep(total_delay)

            except FatalError as e:
                logger.error(f"Fatal error encountered: {e}. Terminating execution.")
                raise
            except Exception as e:
                # Wrap unknown exceptions as Fatal unless they are specifically identified
                logger.error(f"Unexpected system failure: {type(e).__name__} - {e}")
                raise FatalError(f"Uncaught exception in resilience layer: {e}") from e

        raise FatalError("Retry loop exhausted unexpectedly.")

if __name__ == "__main__":
    import asyncio

    async def test_logic():
        print("--- Running Internal Module Test ---")
        handler = ErrorHandler(max_retries=2, base_delay=0.1)

        # 1. Success case
        def success_func(): return "Success!"
        assert handler.execute_with_retry(success_func) == "Success!"
        print("✅ Success function passed.")

        # 2. Transient error recovery
        class Counter:
            def __init__(self): self.count = 0
        
        counter = Counter()
        def transient_fail_func():
            counter.count += 1
            if counter.count < 3:
                raise TransientError(f"Simulated Failure {counter.count}")
            return "Recovered!"
        
        result = handler.execute_with_retry(transient_fail_func)
        assert result == "Recovered!"
        print(f"✅ Recovered after {counter.count} attempts.")

        # 3. Max retries exhaustion
        def permanent_fail_func():
            raise TransientError("Permanent Connectivity Loss")
        
        try:
            handler.execute_with_retry(permanent_fail_func)
        except FatalError as e:
            print(f"✅ Caught expected FatalError after exhaustion: {e}")

        # 4. Immediate Fatal Error
        def fatal_fail_func():
            raise FatalError("Invalid API Key")
        
        try:
            handler.execute_with_retry(fatal_fail_func)
        except FatalError as e:
            print(f"✅ Caught expected immediate FatalError: {e}")

        print("--- ALL INTERNAL TESTS PASSED ---")

    asyncio.run(test_logic())
