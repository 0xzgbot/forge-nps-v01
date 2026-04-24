import sys
import os
from pipelines.comfy_client import ComfyClient

# Configuration
HOST = "100.112.87.8"
PORTS = [8188, 8189]
REQUIRED_MODELS = [
    "z_image_turbo_bf16.safetensors",
    "ltx-2.3-22b-dev-fp8.safetensors" # Based on plan name: ltx-2.3-22b-dev-fp8.safetensors
]

def run_health_check():
    print(f"=== ComfyUI Health Check (Host: {HOST}) ===\n")
    
    for port in PORTS:
        client = ComfyClient(HOST, port)
        print(f"Checking GPU Instance on Port: {port}")
        
        # 1. Health check
        is_online, stats = client.check_health(HOST, port)
        if is_online:
            print(f"  STATUS: [ONLINE]")
            # Print some basic system info if available
            if 'system_stats' in stats:
                print(f"  System Info: {stats['system_stats']}")
        else:
            print(f"  STATUS: [OFFLINE/ERROR] - {stats.get('error', 'Unknown error')}")
            continue

        # 2. Model check
        # Note: list_models is tricky; we'll try to find if required models are in the object_info or similar
        print(f"  Searching for required models...")
        available_models = client.list_models(HOST, port)
        
        # The plan implies checking specific filenames. 
        # Since ComfyUI /object_info returns node info, not necessarily a clean file list,
        # we will check if the model names exist as substrings in the object info/loaded models description
        # OR (better) we try to see if they are mentioned in the 'diffusion_model' loader keys.
        
        all_found = []
        for req in REQUIRED_MODELS:
            # We do a broad check across all returned model-related strings
            # This is an approximation because /object_info doesn't return a file list directly, 
            # but it returns the names of nodes which often include the model name.
            found = any(req.lower() in str(m).lower() for m in available_models)
            if found:
                all_found.append(req)
            else:
                print(f"  [!!] MISSING MODEL: {req}")

        if len(all_found) == len(REQUIRED_MODELS):
            print("  [OK] All required models confirmed present.")
        elif len(all_found) > 0:
            print(f"  [!] Partial success. Found: {all_found}")
        else:
            print("  [!!] No required models found.")
            
        print("-" * 40)

if __name__ == "__main__":
    # Ensure the root is in sys.path so 'pipelines' can be imported
    sys.path.append(os.getcwd())
    run_health_check()
