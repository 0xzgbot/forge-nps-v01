import os
import shutil
import sys

# Use absolute paths derived from the environment or project root
BASE_DIR = "~/Desktop/forge_nps_v01"
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
PROJECTS_DIR = os.path.join(BASE_DIR, "projects")
SCRIPTS_DIR = os.path.join(BASE_DIR, "scripts")

def create_project(project_name):
    if not project_name:
        print("Error: No project name provided.")
        sys.exit(1)

    slug = project_name.lower().replace(" ", "-")
    project_path = os.path.join(PROJECTS_DIR, slug)

    if os.path.exists(project_path):
        print(f"Error: Project '{slug}' already exists at {project_path}")
        sys.exit(1)

    # 1. Create folder structure
    subfolders = [
        "assets/reference",
        "assets/training_images",
        "assets/generations/anchors",
        "assets/generations/videos",
        "assets/loras/validation",
        "banks"
    ]

    print(f"Creating project: {slug}")
    os.makedirs(project_path)
    for sub in subfolders:
        os.makedirs(os.path.join(project_path, sub), exist_ok=True)

    # 2. Copy PROJECT_TEMPLATE.md -> projects/[slug]/PROJECT.md
    template_file = os.path.join(TEMPLATES_DIR, "PROJECT_TEMPLATE.md")
    dest_project_md = os.path.join(project_path, "PROJECT.md")
    if os.path.exists(template_file):
        shutil.copy2(template_file, dest_project_md)
        print(f"  - Copied template to {dest_project_md}")
    else:
        print(f"  !! Warning: PROJECT_TEMPLATE.md not found at {template_file}!")

    # 3. Copy all bank files from templates/character_banks -> projects/[slug]/banks/
    banks_template_dir = os.path.join(TEMPLATES_DIR, "character_banks")
    dest_banks_dir = os.path.join(project_path, "banks")
    if os.path.exists(banks_template_dir):
        for item in os.listdir(banks_template_dir):
            s = os.path.join(banks_template_dir, item)
            d = os.path.join(dest_banks_dir, item)
            if os.path.isfile(s):
                shutil.copy2(s, d)
        print(f"  - Copied character banks to {dest_banks_dir}")
    else:
        print(f"  !! Warning: character_banks folder not found at {banks_template_dir}!")

    print(f"\nProject '{slug}' initialized successfully at {project_path}")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python new_project.py [project_name]")
        sys.exit(1)
    
    create_project(sys.argv[1])
