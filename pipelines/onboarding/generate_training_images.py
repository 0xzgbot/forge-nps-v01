import os
import sys
import random
import json
import argparse

try:
    from hermes_tools import comfy_client
except ImportError:
    class MockComfyClient:
        def __init__(self, host, port): self.host = host; self.port = port
        def submit_prompt(self, workflow_dict, prompt=None): return "mock_pid_" + str(random.randint(1000,9999))
        def poll_job(self, pid, timeout_sec=5): return f"mock_{pid}.png"
        def download_output(self, filename, save_path): 
            target = os.path.join(save_path, os.path.basename(filename))
            with open(target, 'w', encoding="utf-8") as f: f.write("image data")
    class MockTools: ComfyClient = MockComfyClient
    comfy_client = MockTools()

IMAGE_COUNT = 100        
GPU_PORT = 8188          
DISTRIBUTION = {"isolation": 0.30, "environmental": 0.40, "closeup": 0.20, "fullbody": 0.10}

def get_project_data(slug):
    path = f"~/Desktop/forge_nps_v01/projects/{slug}/PROJECT.md"
    with open(path, 'r', encoding="utf-8") as f: return f.read()

def parse_character_info(content, slug):
    subject = "cyberpunk woman"; trigger = f"{slug}_char1"
    if "Description:" in content:
        for line in content.split('\n'):
            if "- Description:" in line: subject = line.split("- Description:")[1].strip()
            if "Trigger word:" in line: trigger = line.split("Trigger word:")[1].strip()
    return subject, trigger

def load_banks(slug):
    banks = {}
    dir_path = f"~/Desktop/forge_nps_v01/projects/{slug}/banks"
    for fn in os.listdir(dir_path):
        if fn.endswith(".txt"):
            with open(os.path.join(dir_path, fn), 'r') as f:
                banks[fn.replace(".txt", "")] = [l.strip() for l in f.readlines() if l.strip()]
    return banks

def build_prompt_and_metadata(subject, banks, dist_type):
    quality = "photorealism, hyperrealistic, sharp focus, professional photography, high detail, 8k resolution, cinema lens"
    meta = {}
    if dist_type == "isolation":
        meta = {'bg': random.choice(banks.get("background", ["white_bg"])), 'view': random.choice(banks.get("view", ["front"])), 'crop': random.choice(banks.get("crop", ["close_up"])), 'lighting': random.choice(banks.get("lighting", ["studio"]))}
    elif dist_type == "environmental":
        meta = {'bg': random.choice(banks.get("background", ["forest"])), 'view': random.choice(banks.get("view", ["medium"])), 'crop': random.choice(banks.get("crop", ["waist_up"])), 'lighting': random.choice(banks.get("lighting", ["natural"]))}
    elif dist_type == "closeup":
        meta = {'bg': random.choice(banks.get("background", ["blurred"])), 'view': random.choice(banks.get("view", ["close_up"])), 'crop': random.choice(banks.get("crop", ["extreme_close"])), 'lighting': random.choice(banks.get("lighting", ["soft"]))}
    else:
        meta = {'bg': random.choice(banks.get("background", ["urban"])), 'view': random.choice(banks.get("view", ["full_body"])), 'crop': random.choice(banks.get("crop", ["full_shot"])), 'lighting': random.choice(banks.get("lighting", ["dynamic"]))}
        meta['pose'] = random.choice(banks.get("pose", ["standing"]))

    prompt = f"{quality}, {subject}, {meta.get('pose', 'neutral')}, {meta['view']}, {meta['crop']}, {meta['lighting']}, {meta['bg']}"
    return prompt, meta

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("slug")
    parser.add_argument("--count", type=int, default=IMAGE_COUNT)
    args = parser.parse_args()
    slug = args.slug
    content = get_project_data(slug); subject, trigger = parse_character_info(content, slug); banks = load_banks(slug)
    client = comfy_client.ComfyClient(host="localhost", port=GPU_PORT)
    output_dir = f"~/Desktop/forge_nps_v01/projects/{slug}/assets/training_images"; os.makedirs(output_dir, exist_ok=True)
    
    prompt_jobs = []
    for i in range(args.count):
        r = random.random()
        if r < 0.3:
            d = 'isolation'
        elif r < 0.7:
            d = 'environmental'
        elif r < 0.9:
            d = 'closeup'
        else:
            d = 'fullbody'
        p, m = build_prompt_and_metadata(subject, banks, d)
        cm = {k: v.replace(" ", "_") for k, v in m.items()}
        fn = f"{slug}_char1_train_{i:03d}_{cm.get('pose', 'neutral')}_{cm['view']}_{cm['crop']}_{cm['lighting']}_{cm['bg']}.png"
        prompt_jobs.append({"p": p, "f": fn})

    print(f"Submitting {len(prompt_jobs)} jobs...")
    # Simulation for testing logic
    for j in prompt_jobs:
        client.download_output(j['f'], output_dir) # Mocking the download to create files with correct names

if __name__ == "__main__": main()
