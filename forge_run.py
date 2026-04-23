import asyncio
import argparse
import logging
import os
import sys
from pathlib import Path

# Add project root to sys.path for seamless imports
sys.path.append('~/Desktop/forge_nps')

from core.bridge.kimi_bridge import KimiBridge
from core.genesis.genesis_engine import GenesisEngine
from core.genesis.asset_prompt_generator import AssetPromptGenerator
from core.comfyui_integration import ComfyUIBatchSubmitter

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("ForgeMaster")

class ForgeOrchestrator:
    """
    The 'Baton': Programmatic glue for the entire production pipeline.
    Idea -> Genesis (Lore/Script) -> AssetPromptGen (Shots/Cinematics) -> ComfyUI Submission.
    """

    def __init__(self, hosts=None, projects_dir="data/projects"):
        # Initialize Bridge and Core Engines
        self.kimi = KimiBridge()
        self.genesis = GenesisEngine(self.kimi, projects_dir=projects_dir)
        self.prompt_gen = AssetPromptGenerator(self.kimi)
        self.submitter = ComfyUIBatchSubmitter(hosts=hosts or ["http://localhost:8188", "http://localhost:8189"])

    async def run_full_production(self, idea: str, project_name: str = None):
        """The complete end-to-end pipeline."""
        logger.info("="*60)
        logger.info(f"🚀 FORGE PRODUCTION STARTING: '{idea}'")
        logger.info("="*60)

        # --- PHASE 1: GENESIS (Lore & Scripting) ---
        logger.info("\n[PHASE 1/3] Initiating Genesis Pipeline...")
        manifest = await self.genesis.create_from_idea(idea, project_name=project_name)
        
        project_path = Path(manifest['project_path'])
        bible_path = Path(manifest['world_bible_path'])
        script_path = Path(manifest['script_path'])

        # Load generated content back for the next phase
        with open(bible_path, 'r', encoding='utf-8') as f:
            bible_content = f.read()
        with open(script_path, 'r', encoding='utf-8') as f:
            script_content = f.read()

        # --- PHASE 2: ASSET PROMPT GENERATION ---
        logger.info("\n[PHASE 2/3] Generating Cinematic Prompt Batches...")
        
        # We need to pass the data in a format ScriptGenerator/AssetPromptGenerator expects
        # For AssetPromptGen, we simulate the parsed dictionary from D2
        # In a production refactor, D2 would return this dict directly.
        from core.genesis.script_generator import ScriptGenerator # ensure parser is available
        parser = ScriptGenerator(self.kimi) 
        parsed_script = parser._parse_script_markdown(script_content)
        
        # We simulate the Bible Dict as well (or refactor D1 to return it)
        # For now, we'll create a minimal dict compatible with J9 requirements
        mock_bible_dict = {"content": bible_content} 

        prompt_batch = await self.prompt_gen.generate_prompts_from_script(parsed_script, mock_bible_dict)
        
        if not prompt_batch:
            logger.error("Prompt generation returned an empty batch. Aborting.")
            return

        # Save the generated prompts to a JSON file within the project structure for traceability
        payloads_dir = project_path / "JSON_PAYLOADS"
        payloads_dir.mkdir(exist_ok=True)
        
        payload_filename = f"PROMPTS_{project_name}_BATCH.json"
        payload_file_path = payloads_dir / payload_filename
        
        with open(payload_file_path, 'w', encoding='utf-8') as f:
            import json
            json.dump(prompt_batch, f, indent=2)
        
        logger.info(f"✅ Prompts saved to: {payload_file_path}")

        # --- PHASE 3: COMFYUI SUBMISSION ---
        logger.info("\n[PHASE 3/3] Submitting Batches to ComfyUI...")
        
        # We pass the batch directly (J8 was built for this)
        submission_results = await self.submitter.submit_batch(prompt_batch)

        # --- FINAL SUMMARY ---
        logger.info("\n" + "="*60)
        logger.info("🏁 PRODUCTION PIPELINE COMPLETE")
        logger.info("="*60)
        
        success_count = sum(1 for r in submission_results if r['status'] == 'success')
        fail_count = len(submission_results) - success_count
        
        print(f"\nSummary:")
        print(f"  - Project:      {project_name or idea}")
        print(f"  - Shots Total:  {len(prompt_batch)}")
        print(f"  - Successful:   {success_count}")
        print(f"  - Failed:       {fail_count}")
        print(f"  - Output Dir:   {project_path / 'outputs'}")
        print("="*60)

async def main():
    parser = argparse.ArgumentParser(description="Forge Master Orchestrator")
    parser.add_argument("--idea", type=str, required=True, help="The creative concept for the project.")
    parser.add_argument("--name", type=str, help="Custom name for the project directory.")
    parser.add_argument("--hosts", nargs='*', help="Comma-separated list of ComfyUI hosts (e.g. http://IP:8188)")

    args = parser.parse_args()

    orchestrator = ForgeOrchestrator(hosts=args.hosts)
    await orchestrator.run_full_production(idea=args.idea, project_name=args.name)

if __name__ == "__main__":
    asyncio.run(main())
