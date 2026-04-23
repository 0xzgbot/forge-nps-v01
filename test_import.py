
import sys
import os
sys.path.append('~/Desktop/forge_nps')

try:
    from core.bridge.config_manager import ConfigManager
    print("SUCCESS: ConfigManager imported successfully via absolute path injection.")
except Exception as e:
    print(f"FAILURE: Could not import ConfigManager. Error: {e}")
