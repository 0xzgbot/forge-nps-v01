import os
import json
import time
import requests
import re
import sys

NODE_TEXT = "6"          
NODE_RESOLUTION = "8"    
NODE_FILENAME = "11"     
DEFAULT_WIDTH = 1024
DEFAULT_HEIGHT = 576  

class ComfyClient:
    def __init__(self, host, port):
        self.base_url = f"http://{host}:{port}"

    def check_health(self, host, port):
        try:
            response = requests.get(f"{self.base_url}/api/system_stats", timeout=5)
            if response.status_code == 200:
                return True, response.json()
            return False, {"error": f"Status code {response.status_code}"}
        except Exception as e:
            return False, {"error": str(e)}

    def submit_prompt(self, host, port, workflow_dict):
        try:
            response = requests.post(f"{self.base_url}/prompt", json={"prompt": workflow_dict}, timeout=5)
            if response.status_code == 200:
                return response.json().get("prompt_id")
            return None
        except Exception as e:
            print(f"Error submitting prompt: {e}")
            return None

    def poll_job(self, host, port, prompt_id, timeout_sec=300):
        start_time = time.time()
        while time.time() - start_time < timeout_sec:
            try:
                response = requests.get(f"{self.base_url}/history/{prompt_id}", timeout=5)
                if response.status_code == 200:
                    data = response.json()
                    if prompt_id in data:
                        outputs = data[prompt_id].get("outputs", {})
                        for node_id, node_output in outputs.items():
                            if "images" in node_output:
                                return node_output["images"][0]["filename"]
                time.sleep(5)
            except Exception as e:
                print(f"Error polling job: {e}")
                time.sleep(5)
        return None

    def download_output(self, host, port, filename, save_path):
        try:
            url = f"{self.base_url}/view?filename={filename}&type=output&subfolder="
            response = requests.get(url, stream=True, timeout=10)
            if response.status_code == 200:
                with open(save_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                return True
            return False
        except Exception as e:
            print(f"Error downloading output: {e}")
            return False

def generate_sheets(project_slug, host="localhost", port=8188):
    print(f"\n>>> Starting Reference Sheet Generation for project: {project_slug}")
    
    cwd = os.getcwd()
    project_dir = os.path.join(cwd, "projects", project_slug)
    project_md_path = os.path.join(project_dir, "PROJECT.md")
    workflow_path = os.path.join(cwd, "workflows", "z_image_turbo_api.json")
    assets_dir = os.path.join(project_dir, "assets")

    if not os.path.exists(project_md_path):
        print(f"Error: PROJECT.md not found at {project_md_path}")
        return

    with open(project_md_path, 'r') as f:
        md_content = f.read()

    char_blocks = re.split(r'### Character \d+', md_content)[1:] 
    if not char_blocks:
        print("No characters found in PROJECT.md")
        return

    with open(workflow_path, 'r') as f:
        workflow = json.load(f)

    client = ComfyClient(host, port)

    for idx, block in enumerate(char_blocks):
        char_num = idx + 1
        print(f"\nProcessing Character {char_num}...")

        name_match = re.search(r'\|- Name \(internal reference\): (.*)', block)
        desc_match = re.search(r'\|- Description: (.*)', block)
        trigger_match = re.search(r'\|- Trigger word: (.*)', block)
        sample_labels_match = re.search(r'\|- Sample labels: \[(.*)\]', block)

        char_name = name_match.group(1).strip() if name_match else f"char_{char_num}"
        description = desc_match.group(1).strip() if desc_match else "detailed portrait"
        trigger_word = trigger_match.group(1).strip() if trigger_match else f"{project_slug}_char{char_num}"
        sample_labels = [s.strip() for s in sample_labels_match.group(1).split(',')] if sample_labels_match else ["hair", "eyes", "nose", "lips", "ears", "skin"]

        sheets = [
            {
                "type": "head_sheet",
                "prompt": f"photorealism, head sheet, head front, head right side, head only, white background, samples on the right side showing {', '.join(sample_labels)}",
                "filename_suffix": "head_sheet.png"
            },
            {
                "type": "character_sheet",
                "prompt": f"photorealism, character sheet, three-view, full figure only, white background, 6 square samples on the right side showing {', '.join(sample_labels)}",
                "filename_suffix": "character_sheet.png"
            }
        ]

        for sheet in sheets:
            print(f"  Generating {sheet['type']}...")
            run_workflow = json.loads(json.dumps(workflow))
            
            # THE FIX: Access 'prompt' dict specifically
            prompt_data = run_workflow.get("prompt", {})
            
            if NODE_TEXT not in prompt_data:
                print(f"  [!!] CRITICAL ERROR: Node {NODE_TEXT} not found in workflow prompt!")
                continue

            prompt_data[NODE_TEXT]["inputs"]["text"] = sheet["prompt"]
            prompt_data[NODE_RESOLUTION]["inputs"]["width"] = DEFAULT_WIDTH
            prompt_data[NODE_RESOLUTION]["inputs"]["height"] = DEFAULT_HEIGHT
            prompt_data[NODE_FILENAME]["inputs"]["filename_prefix"] = f"{project_slug}_char{char_num}_{sheet['type']}"

            prompt_id = client.submit_prompt(host, port, run_workflow)
            if not prompt_id:
                print(f"  [!!] Failed to submit {sheet['type']} for {char_name}")
                continue
            
            print(f"  Prompt submitted (ID: {prompt_id}). Polling...")
            filename = client.poll_job(host, port, prompt_id)
            
            if filename:
                final_path = os.path.join(assets_dir, sheet['filename_suffix'])
                success = client.download_output(host, port, filename, final_path)
                if success:
                    print(f"  [OK] Saved {sheet['type']} to {final_path}")
                else:
                    print(f"  [!!] Failed to download {filename}")
            else:
                print(f"  [!!] Job timed out or failed for {sheet['type']}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python generate_sheets.py [project_slug]")
    else:
        generate_sheets(sys.argv[1])
