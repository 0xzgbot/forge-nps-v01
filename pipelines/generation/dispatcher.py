import asyncio
import logging
import aiohttp
from typing import Dict, Any

logger = logging.getLogger("Dispatcher")

class Dispatcher:
    """
    Handles the distribution of payloads to ComfyUI instances.
    Supports dual-host round-robin load balancing with real API integration.
    """
    def __init__(self):
        # The user's established ComfyUI cluster configuration
        self.hosts = [
            "http://localhost:8188", 
            "http://localhost:8189"
        ]
        self.current_host_index = 0
        logger.info(f"Dispatcher initialized with hosts: {self.hosts}")

    async def check_connectivity(self) -> bool:
        """
        Performs a pre-flight connectivity check for all configured ports.
        Returns True if at least one host is reachable, False otherwise.
        """
        logger.info("Performing pre-flight connectivity check...")
        reachable_hosts = []
        
        async with aiohttp.ClientSession() as session:
            for host in self.hosts:
                try:
                    # Using /health or just attempting to connect to the root
                    async with session.get(host, timeout=2) as response:
                        if response.status < 500:
                            logger.info(f"Host {host} is REACHABLE (Status: {response.status})")
                            reachable_hosts.append(host)
                        else:
                            logger.warning(f"Host {host} returned error status: {response.status}")
                except Exception as e:
                    logger.warning(f"Host {host} is UNREACHABLE: {e}")

        if not reachable_hosts:
            logger.error("Pre-flight check FAILED: No hosts are reachable.")
            return False
        
        logger.info(f"Pre-flight check PASSED: {len(reachable_hosts)}/{len(self.hosts)} hosts online.")
        return True

    async def dispatch(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sends a payload to the next available host in the round-robin rotation via HTTP POST.
        Includes error handling for connection timeouts or refused connections.
        """
        # Ensure we have connectivity before attempting dispatch (optional but recommended)
        # In high-throughput, you might want to do this periodically instead of per-request.
        
        host = self.hosts[self.current_host_index]
        self.current_host_index = (self.current_host_index + 1) % len(self.hosts)
        
        logger.info(f"Dispatching payload to host: {host}")

        try:
            async with aiohttp.ClientSession() as session:
                # Note: In a real ComfyUI environment, the endpoint is usually /prompt
                url = f"{host}/prompt"
                async with session.post(url, json=payload, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        return {
                            "status": "success",
                            "host_used": host,
                            "response": data
                        }
                    else:
                        error_text = await response.text()
                        logger.error(f"Host {host} returned error {response.status}: {error_text}")
                        return {
                            "status": "failed",
                            "host_used": host,
                            "reason": f"HTTP {response.status}"
                        }
        except asyncio.TimeoutError:
            logger.error(f"Dispatch to {host} TIMED OUT.")
            return {"status": "failed", "host_used": host, "reason": "timeout"}
        except aiohttp.ClientConnectorError as e:
            logger.error(f"Connection refused/failed for {host}: {e}")
            return {"status": "failed", "host_used": host, "reason": "connection_refused"}
        except Exception as e:
            logger.exception(f"Unexpected error dispatching to {host}: {e}")
            return {"status": "failed", "host_used": host, "reason": str(e)}

if __name__ == "__main__":
    # Quick test logic
    async def test():
        d = Dispatcher()
        print("--- Connectivity Check ---")
        await d.check_connectivity()
        print("\n--- Test Dispatch (Will likely fail if hosts aren't real) ---")
        print(await d.dispatch({"prompt": {"input": "test"}}))
    asyncio.run(test())
