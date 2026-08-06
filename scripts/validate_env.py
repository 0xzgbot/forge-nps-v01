#!/usr/bin/env python3
"""Validate Cinesmith environment variables and service reachability."""

import os
import sys
import time
from pathlib import Path

# Colors for terminal output
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BLUE = "\033[94m"
RESET = "\033[0m"

# Ensure repo root on path for cinesmith_env diagnostics
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

REQUIRED_ENV_VARS = [
    "NIM_ENDPOINT",
    "KIMI_API_KEY",
    "COMFYUI_PRIMARY",
    "COMFYUI_SECONDARY",
    "DASHBOARD_PORT",
    "MOCK_MODE"
]

def print_status(label, status, color=GREEN):
    print(f"{label:<30} [{color}{status}{RESET}]")

def check_env_file():
    env_path = Path(".env")
    template_path = Path(".env.template")
    
    if not env_path.exists():
        print(f"{RED}[!] ERROR: .env file not found.{RESET}")
        print(f"    Please copy the template: cp .env.template .env")
        return False, env_path
    
    if not template_path.exists():
        print(f"{YELLOW}[?] WARNING: .env.template not found.{RESET}")
    
    return True, env_path

def validate_vars(env_path):
    # Load vars manually to avoid extra dependency on python-dotenv if not installed
    variables = {}
    try:
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, value = line.split("=", 1)
                    variables[key.strip()] = value.strip()
    except Exception as e:
        print(f"{RED}[!] Error reading .env file: {e}{RESET}")
        return False, {}

    missing_vars = []
    for var in REQUIRED_ENV_VARS:
        val = variables.get(var)
        # Check if the value is missing or exactly equal to a known template placeholder
        if not val or any(placeholder in str(val).lower() for placeholder in ["your_", "placeholder", "example"]):
            missing_vars.append(var)
    
    if missing_vars:
        print(f"{RED}[!] ERROR: Missing or placeholder environment variables:{RESET}")
        for var in missing_vars:
            print(f"    - {var}")
        return False, variables
    
    return True, variables


def ping_endpoint(url, label, timeout=3):
    if not url.startswith("http"):
        return f"{RED}Invalid URL{RESET}"
    
    try:
        start_time = time.time()
        # We use a lightweight request to check connectivity
        response = requests.get(url, timeout=timeout)
        latency = (time.time() - start_time) * 1000
        if response.status_code < 400:
            return f"{GREEN}OK ({latency:.2f}ms){RESET}"
        else:
            return f"{YELLOW}HTTP {response.status_code}{RESET}"
    except requests.exceptions.ConnectionError:
        return f"{RED}Unreachable{RESET}"
    except requests.exceptions.Timeout:
        return f"{RED}Timeout{RESET}"
    except Exception as e:
        return f"{RED}Error: {str(e)}{RESET}"

def estimate_nim_latency(endpoint):
    if not endpoint or "your_" in endpoint:
        return f"{YELLOW}Skipped (Invalid Endpoint){RESET}"
    
    try:
        start_time = time.time()
        # Attempt a HEAD request to check latency without payload
        # Note: Some APIs might reject HEAD, so we use GET if needed
        response = requests.get(endpoint, timeout=5)
        latency = (time.time() - start_time) * 1000
        return f"{GREEN}{latency:.2f}ms{RESET}"
    except Exception:
        return f"{RED}N/A (Check connectivity){RESET}"

def main():
    print(f"\n{BLUE}=== CINESMITH NPS Environment Validation ==={RESET}\n")

    # 0. Hermes isolation (always check)
    try:
        from core.cinesmith_env import hermes_isolation_status, apply_hermes_isolation
        apply_hermes_isolation()
        status = hermes_isolation_status()
        if status.get("using_global_hermes"):
            print(f"{RED}[!] HERMES_HOME points at global ~/.hermes — Cinesmith should use repo hermes_home/{RESET}")
            print(f"    Current: {status.get('process_hermes_home')}")
        else:
            print_status("Hermes Isolation", "OK")
            print(f"    HERMES_HOME={status.get('hermes_home')}")
    except Exception as exc:
        print(f"{YELLOW}[?] Hermes isolation check skipped: {exc}{RESET}")

    # 1. Check .env existence
    exists, env_path = check_env_file()
    if not exists:
        sys.exit(1)

    # 2. Validate variables
    vars_ok, vars_dict = validate_vars(env_path)
    if not vars_ok:
        print(f"\n{RED}Environment validation failed.{RESET}")
        sys.exit(1)
    else:
        print_status("Environment Variables", "VALID")

    # 3. Check ComfyUI Endpoints
    print("\nChecking Service Connectivity...")
    primary_url = vars_dict.get("COMFYUI_PRIMARY")
    secondary_url = vars_dict.get("COMFYUI_SECONDARY")

    p_status = ping_endpoint(primary_url, "Primary ComfyUI")
    print(f"{'ComfyUI Primary':<30} [{p_status}]")

    s_status = ping_endpoint(secondary_url, "Secondary ComfyUI")
    print(f"{'ComfyUI Secondary':<30} [{s_status}]")

    # 4. NIM Latency
    nim_endpoint = vars_dict.get("NIM_ENDPOINT")
    print("\nChecking AI Inference...")
    nim_latency = estimate_nim_latency(nim_endpoint)
    print(f"{'NIM Latency':<30} [{nim_latency}]")

    # 5. Final Result
    print(f"\n{BLUE}========================================={RESET}")
    print(f"Launch with: bash scripts/launch_cinesmith.sh")
    if vars_ok and "Unreachable" not in p_status and "Unreachable" not in s_status:
        print(f"{GREEN}SUCCESS: Environment is ready for use.{RESET}")
        sys.exit(0)
    else:
        print(f"{YELLOW}WARNING: Some services are unreachable. Check your connections.{RESET}")
        sys.exit(0)  # Don't exit 1 on connection issues, just warn

if __name__ == "__main__":
    try:
        import requests  # noqa: F401
    except ImportError:
        print(f"{RED}[!] ERROR: 'requests' library not found. Please run: pip install requests{RESET}")
        sys.exit(1)

    main()
