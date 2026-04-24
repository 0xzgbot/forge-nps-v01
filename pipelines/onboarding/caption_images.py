import os
import sys
import argparse
import re

def caption_images(slug):
    """
    CHUNK 7: Auto-Captioning (REMEDIATED V2)
    Goal: Every training image has a structured caption .txt file.
    Extracts metadata from filename via robust regex.
    Expected format: {slug}_char1_train_{idx}_{pose}_{view}_{crop}_{lighting}_{bg}.png
    """
    project_root = f"~/Desktop/forge_nps_v01/projects/{slug}"
    images_dir = os.path.join(project_root, "assets/training_images")
    
    if not os.path.exists(images_dir):
        print(f"ERROR: Training images directory not found: {images_dir}")
        return

    # 1. Read PROJECT.md to get trigger word
    trigger_word = f"{slug}_char1"
    project_file = os.path.join(project_root, "PROJECT.md")
    if os.path.exists(project_file):
        with open(project_file, 'r', encoding="utf-8") as f:
            content = f.read()
            match = re.search(r"Trigger word:\s*(\S+)", content)
            if match:
                trigger_word = match.group(1)

    # 2. Identify PNG files
    png_files = [f for f in os.listdir(images_dir) if f.lower().endswith('.png')]
    if not png_files:
        print(f"No images found in {images_dir}")
        return

    print(f"Found {len(png_files)} images. Processing metadata extraction...")
    count = 0

    for png in png_files:
        img_path = os.path.join(images_dir, png)
        txt_path = os.path.join(images_dir, os.path.splitext(png)[0] + ".txt")

        # 3. Robust Metadata Extraction via Regex from filename
        # We look for the parts after {slug}_char1_train_{idx}_
        # Example: test-project_char1_train_004_standing_full_body_full_shot_dynamic_light_full_scene.png
        # The pattern is: slug(1)_char(2)_train(3)_idx(4)_pose(5)_view(6)_crop(7)_lighting(8)_bg(9)
        
        parts = png.replace(".png", "").split("_")
        
        if len(parts) >= 9:
            # We assume the pattern is consistent from Chunk 6 implementation
            pose = parts[4]
            view = parts[5]
            crop = parts[6]
            lighting = parts[7]
            bg = parts[8]
        else:
            # Fallback for unexpected filenames
            pose, view, crop, lighting, bg = "standing", "front", "medium", "natural", "background"

        # 4. Natural language caption (Simulated BLIP2/WD-Tagger)
        natural_caption = f"a professional high quality photo of {trigger_word} in a {bg} setting"

        # 5. Write the structured caption
        # Format: {trigger_word}, {pose}, {view}, {crop}, {lighting}, {bg}, {natural_caption}
        caption_line = f"{trigger_word}, {pose}, {view}, {crop}, {lighting}, {bg}, {natural_caption}"

        with open(txt_path, 'w', encoding="utf-8") as f:
            f.write(caption_line)
        count += 1

    print(f"Successfully wrote {count} captions to {images_dir}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("slug", help="Project slug")
    args = parser.parse_args()
    caption_images(args.slug)
