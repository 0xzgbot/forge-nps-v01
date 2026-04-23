import os
import json
import re
from pathlib import Path

def parse_prompt_library(md_path):
    with open(md_path, 'r') as f:
        content = f.read()

    title_match = re.search(r'^#\s+(.*)', content, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else "Untitled Library"
    
    # Create a slug for ID
    lib_id = title.lower().replace(" ", "_").replace("-", "_")
    if "_" in lib_id:
        lib_id, _ = lib_id.split("_", 1) # simple approach

    entries = []
    
    # Pattern to find H3 headers as entries (based on the files I read)
    # ### 1. The Persona Deep-Dive (Character Creation)
    # **Use Case**: ...
    # **Prompt Structure**: `...`
    entry_pattern = re.compile(r'###\s+(.*?)\n\*\*Use Case\*\*:\s*(.*?)\n\*\*Prompt Structure\*\*:\s*`(.*?)`', re.DOTALL)
    
    matches = entry_pattern.findall(content)
    
    for i, (entry_title, use_case, prompt_structure) in enumerate(matches):
        # Clean up the title and structure
        clean_title = entry_title.strip()
        clean_use_case = use_case.strip()
        clean_prompt = prompt_structure.strip()
        
        # Create an ID for the entry
        entry_id = f"{lib_id}_entry_{i+1}"
        
        # We'll default model_kernel to "Flux" as it's a standard in this context unless specified
        # metadata extraction is tricky from these unstructured MD files, so we'll try to pull what we can
        metadata = {
            "use_case": clean_use_case,
            "source_file": os.path.basename(md_path)
        }

        entries.append({
            "id": entry_id,
            "title": clean_title,
            "model_kernel": "Flux", # Default
            "base_prompt": clean_prompt,
            "metadata": metadata
        })

    return {
        "id": lib_id,
        "title": title,
        "entries": entries
    }

def migrate_prompts(src_dir, dest_dir):
    src_path = Path(src_dir)
    dest_path = Path(dest_dir)
    dest_path.mkdir(parents=True, exist_ok=True)

    for md_file in src_path.glob("*.md"):
        print(f"Migrating {md_file.name}...")
        library_data = parse_prompt_library(md_file)
        
        # Save as JSON with the same name (but .json)
        out_name = md_file.stem + ".json"
        with open(dest_path / out_name, 'w') as f:
            json.dump(library_data, f, indent=4)

def migrate_banks(src_templates, dest_dir):
    src_path = Path(src_templates)
    dest_path = Path(dest_dir)
    dest_path.mkdir(parents=True, exist_ok=True)

    # The bank_loader expects {name}_bank.txt
    for txt_file in src_path.glob("*.txt"):
        # Example: lighting_bank.txt (already correct?) 
        # Wait, let's check the source names from my previous 'find'
        # /Users/zgbot/Desktop/forge_nps/templates/character_banks/lighting_bank.txt
        # They seem to ALREADY have the suffix. I just need to copy them.
        print(f"Migrating bank {txt_file.name}...")
        dest_file = dest_path / txt_file.name
        with open(txt_file, 'r') as src, open(dest_file, 'w') as dst:
            dst.write(src.read())

if __name__ == "__main__":
    PROMPT_SRC = "/Users/zgbot/Desktop/forge_nps/projects/prompt_libraries/"
    PROMPT_DEST = "/Users/zgbot/Desktop/forge_nps/data/prompt_libraries/"
    BANK_SRC = "/Users/zgbot/Desktop/forge_nps/templates/character_banks/"
    BANK_DEST = "/Users/zgbot/Desktop/forge_nps/data/character_banks/"

    print("--- Migrating Prompt Libraries ---")
    migrate_prompts(PROMPT_SRC, PROMPT_DEST)
    
    print("\n--- Migrating Character Banks ---")
    migrate_banks(BANK_SRC, BANK_DEST)
    print("\nMigration Complete.")
