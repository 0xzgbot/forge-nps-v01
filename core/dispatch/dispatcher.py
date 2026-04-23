import asyncio
import logging
import os
from typing import Dict, Any
import httpx

from core.bridge.config_manager import ConfigManager

logger = logging.getLogger("ComfyDispatcher")

class ComfyDispatcher:
    """
    Handles the distribution of payloads to ComfyUI instances.
    Supports dual-host round-robin load balancing with real API integration.
    """
    def __init__(self, hosts: list[str] = None):
        if hosts is not None:
            self.hosts = hosts
        else:
            config = ConfigManager()
            self.hosts = [config.get_comfyui_primary()]
            secondary = os.getenv("COMFYUI_SECONDARY", "")
            if secondary:
                self.hosts.append(secondary)
        
        self._round_robin_index = 0
        logger.info(f"ComfyDispatcher initialized with hosts: {self.hosts}")

    def _round_robin_host(self) -> str:
        """Returns the next host in the rotation."""
        host = self.hosts[self._round_robin_index]
        self._round_robin_index = (self._round_robin_index + 1) % len(self.hosts)
        return host

    async def check_connectivity(self) -> bool:
        """
        Performs a pre-flight connectivity check for all configured ports.
        Calls '/system_stats' on each host and logs latency.
        Returns True if at least one host is reachable, False otherwise.
        """
        logger.info("Performing pre-flight connectivity check...")
        reachable_hosts = []
        
        async with httpx.AsyncClient() as client:
            for host in self.hosts:
                try:
                    # Using /system_stats as specified in A2 requirements
                    url = f"{host.rstrip('/')}/system_stats"
                    response = await client.get(url, timeout=2.0)
                    if response.status_code < 500:
                        logger.info(f"Host {host} is REACHABLE (Status: {response.status_code})")
                        reachable_hosts.append(host)
                    else:
                        logger.warning(f"Host {host} returned error status: {response.status_code}")
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
        host = self._round_robin_host()
        logger.info(f"Dispatching payload to host: {host}")

        try:
            async with httpx.AsyncClient() as client:
                # Note: In a real ComfyUI environment, the endpoint is usually /prompt
                url = f"{host.rstrip('/')}/prompt"
                response = await client.post(url, json=payload, timeout=10.0)
                
                if response.status_code == 200:
                    data = response.json()
                    return {
                        "status": "success",
                        "host_used": host,
                        "response": data
                    }
                else:
                    error_text = response.text
                    logger.error(f"Host {host} returned error {response.status_code}: {error_text}")
                    return {
                        "status": "failed",
                        "host_used": host,
                        "reason": f"HTTP {response.status_code}"
                    }
        except httpx.TimeoutException:
            logger.error(f"Dispatch to {host} TIMED OUT.")
            return {"status": "failed", "host_used": host, "reason": "timeout"}
        except (httpx.ConnectError, httpx.ConnectTimeout) as e:
            logger.error(f"Connection refused/failed for {host}: {e}")
            return {"status": "failed", "host_used": host, "reason": "connection_refused"}
        except Exception as e:
            logger.exception(f"Unexpected error dispatching to {host}: {e}")
            return {"status": "failed", "host_used": host, "reason": str(e)}

    async def dispatch_batch(self, payloads: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
        """Dispatches a batch of payloads concurrently."""
        tasks = [self.dispatch(p) for p in payloads]
        return await asyncio.gather(*tasks)

if __name__ == "__main__":
    # Quick local test (requires manual execution or integration test run)
    async def main():
        d = ComfyDispatcher(["http://127.0.0.1:8188"])
        print(await d.dispatch({"test": "data"}))

    asyncio.run(main())
