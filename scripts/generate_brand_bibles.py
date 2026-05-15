#!/usr/bin/env python3
"""
Generate brand bibles for all 7 hackathon campaigns via Kimi K2.5 (NVIDIA NIM).
"""
import asyncio
import json
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from core.bridge.config_manager import ConfigManager
from core.bridge.kimi_bridge import KimiBridge
from core.genesis.world_bible_generator import WorldBibleGenerator

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("BrandBibleGen")

CAMPAIGNS = [
    {
        "name": "aurora_cosmetics",
        "idea": "A luxury vegan cosmetics brand called Aurora that uses bioluminescent algae extracts. The campaign shows a woman applying glowing skincare at dawn by a misty lake.",
        "genre": "Beauty / Lifestyle / Cinematic"
    },
    {
        "name": "summit_coffee",
        "idea": "An artisan mountain coffee brand called Summit Coffee. The campaign follows a mountaineer brewing pour-over coffee at 14,000 feet as golden sunrise hits the peaks.",
        "genre": "Adventure / Artisan / Documentary-style"
    },
    {
        "name": "neon_drift",
        "idea": "A cyberpunk street racing short film called Neon Drift. Two rival drivers race through rain-soaked neon Tokyo streets at midnight. Synthwave aesthetic.",
        "genre": "Cyberpunk / Action / Sci-Fi"
    },
    {
        "name": "wes_anderson_film",
        "idea": "A whimsical Wes Anderson-style short film about a quirky family running a boutique hotel in the Swiss Alps. Symmetrical frames, pastel colors, deadpan humor.",
        "genre": "Comedy / Fine Art / Narrative"
    },
    {
        "name": "animated_short",
        "idea": "A Studio Ghibli-inspired animated short about a young girl who discovers a hidden forest spirit world behind her grandmother's garden. Hand-painted aesthetic, magical realism.",
        "genre": "Animation / Fantasy / Family"
    },
    {
        "name": "fitness_campaign",
        "idea": "A high-energy fitness transformation campaign called 'Iron Genesis'. An athlete trains from dawn to dusk across urban rooftops, beaches, and mountain trails. Gritty, motivational, cinematic.",
        "genre": "Sports / Transformation / Motivational"
    },
    {
        "name": "car_commercial",
        "idea": "A luxury electric vehicle commercial for a sleek EV called 'Voltara'. The car glides silently through futuristic cityscapes and coastal highways at twilight. Premium, minimalist, aspirational.",
        "genre": "Automotive / Luxury / Cinematic"
    }
]

async def generate_bible(kimi: KimiBridge, campaign: dict, projects_dir: Path):
    name = campaign["name"]
    idea = campaign["idea"]
    genre = campaign["genre"]

    project_path = projects_dir / name
    project_path.mkdir(parents=True, exist_ok=True)
    bible_path = project_path / "brand_bible.md"

    if bible_path.exists() and bible_path.stat().st_size > 500:
        logger.info(f"SKIP {name}: brand bible already exists ({bible_path.stat().st_size} bytes)")
        return True

    logger.info(f"START {name}: generating brand bible...")
    try:
        gen = WorldBibleGenerator(kimi)
        result = await gen.generate(idea, genre_hint=genre)
        bible_text = result.get("world_bible_text", "")

        if not bible_text or len(bible_text) < 200:
            logger.error(f"FAIL {name}: generated bible too short or empty")
            return False

        with open(bible_path, "w", encoding="utf-8") as f:
            f.write(bible_text)

        logger.info(f"SUCCESS {name}: saved {len(bible_text)} chars to {bible_path}")
        return True

    except Exception as e:
        logger.error(f"FAIL {name}: {type(e).__name__}: {e}")
        return False

async def main():
    cm = ConfigManager(str(PROJECT_ROOT / ".env"))
    missing = cm.validate()
    if missing:
        logger.error(f"Missing config: {missing}")
        sys.exit(1)

    bridge = KimiBridge(
        endpoint_url=cm.get_nim_endpoint(),
        api_key=cm.get_kimi_api_key(),
        config_manager=cm
    )

    projects_dir = PROJECT_ROOT / "data" / "projects"
    projects_dir.mkdir(parents=True, exist_ok=True)

    results = {}
    for campaign in CAMPAIGNS:
        ok = await generate_bible(bridge, campaign, projects_dir)
        results[campaign["name"]] = ok
        # Small delay between requests to avoid rate limits
        await asyncio.sleep(1)

    logger.info("=" * 50)
    logger.info("BRAND BIBLE GENERATION COMPLETE")
    logger.info("=" * 50)
    for name, ok in results.items():
        status = "✅ PASS" if ok else "❌ FAIL"
        logger.info(f"  {status}: {name}")

    failed = [n for n, ok in results.items() if not ok]
    if failed:
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
