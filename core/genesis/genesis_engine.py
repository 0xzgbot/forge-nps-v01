import logging
import os
from typing import Dict, Any, Optional
from pathlib import Path

from core.bridge.kimi_bridge import KimiBridge
from core.genesis.world_bible_generator import WorldBibleGenerator
from core.genesis.script_generator import ScriptGenerator

logger = logging.getLogger("GenesisEngine")

class GenesisEngine:
    """
    Phase D: Idea-to-Production Engine.
    Orchestrates the transition from a single creative idea to a full, 
    initialized production project including World Bible and Pilot Script.
    """

    def __init__(self, kimi_bridge: KimiBridge, projects_dir: str = "data/projects"):
        self.kimi_bridge = kimi_bridge
        self.projects_dir = Path(projects_dir)
        self.bible_gen = WorldBibleGenerator(kimi_bridge)
        self.script_gen = ScriptGenerator(kimi_bridge)

    async def create_from_idea(self, idea: str, project_name: Optional[str] = None, 
                               genre_hint: Optional[str] = None, num_scenes: int = 2) -> Dict[str, Any]:
        """
        The primary entry point for the Genesis pipeline.
        1. Generates World Bible (D1)
        2. Generates Pilot Script (D2)
        3. Initializes Project Folder structure
        4. Saves all files to the project directory
        """
        if not project_name:
            # Sanitize idea for a folder name
            project_name = re.sub(r'[^a-z0-9]+', '_', idea.lower().strip()[:20])

        logger.info(f"Starting Genesis pipeline for concept: '{idea}' (Project: {project_name})")
        
        # 1. Generate World Bible
        bible_data = await self.bible_gen.generate(idea, genre_hint)
        bible_text = bible_data.get("world_bible_text", "")
        if not bible_text: # Fallback check in case the dictionary key differs from generator output
             # Based on previous testing, let's ensure we handle various possible return formats
             if isinstance(bible_data, str):
                 bible_text = bible_data
             else:
                 bible_text = bible_data.get("content", "")

        # 2. Generate Pilot Script
        script_data = await self.script_gen.generate(bible_data, num_scenes=num_scenes)
        script_text = script_data.get("script_text", "")
        if not script_text:
             if isinstance(script_data, str):
                 script_text = script_data
             else:
                 script_text = script_data.get("content", "")

        # 3. Initialize Project Directory
        project_path = self.projects_dir / project_name
        os.makedirs(project_path / "outputs", exist_ok=True)
        os.makedirs(project_path / "sessions", exist_ok=True)
        os.makedirs(project_path / "reasoning_logs", exist_ok=True)

        # 4. Save files
        manifest = {
            "project_name": project_name,
            "project_path": str(project_path),
            "world_bible_path": str(project_path / "world_bible.md"),
            "script_path": str(project_path / "pilot_script.md"),
            "genesis_summary": f"Genesis produced a {num_scenes}-scene script based on '{idea}'."
        }

        # Write the Markdown files
        with open(manifest["world_bible_path"], "w", encoding="utf-8") as f:
            f.write(bible_text)
        
        with open(manifest["script_path"], "w", encoding="utf-8") as f:
            f.write(script_text)

        # Write a simple project manifest for the orchestrator to read later
        with open(project_path / "PROJECT.md", "w", encoding="utf-8") as f:
            f.write(f"# PROJECT: {project_name}\n\n{manifest['genesis_summary']}")

        logger.info(f"Genesis pipeline complete. Project created at: {project_path}")
        return manifest

    async def create_from_brief(self, project_name: str, 
                                world_bible_path: str, 
                                script_path: str) -> Dict[str, Any]:
        """
        Bypasses the generation phase for existing content.
        Used when a user provides their own Bible and Script.
        """
        logger.info(f"Initializing project from existing brief: {project_name}")
        
        project_path = self.projects_dir / project_name
        os.makedirs(project_path / "outputs", exist_ok=True)
        os.makedirs(project_path / "sessions", exist_ok=True)
        os.makedirs(project_path / "reasoning_logs", exist_ok=True)

        manifest = {
            "project_name": project_name,
            "project_path": str(project_path),
            "world_bible_path": os.path.abspath(world_bible_path),
            "script_path": os.path.abspath(script_path),
            "genesis_summary": "Project initialized from provided brief (Genesis bypass)."
        }

        # Copy files to the project folder for local containment
        shutil.copy(world_bible_path, project_path / "world_bible.md")
        shutil.copy(script_path, project_path / "pilot_script.md")

        with open(project_path / "PROJECT.md", "w", encoding="utf-8") as f:
            f.write(f"# PROJECT: {project_name}\n\n{manifest['genesis_summary']}")

        return manifest

import re
