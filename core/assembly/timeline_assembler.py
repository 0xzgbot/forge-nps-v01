import os
import asyncio
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

class TimelineAssembler:
    """
    Implements J13: Consolidates session metadata, shot assets, and audio 
    into a single production manifest.
    """

    def __init__(self):
        self.logger = logger

    async def assemble(self, session_id: str, session_summary: Dict[str, Any]) -> Dict[str, Any]:
        """
        Ingests a session summary and shot list to create a final production manifest.
        
        Args:
            session_id: Unique identifier for the session.
            session_summary: Dictionary containing 'metadata' and 'shots'.
            
        Returns:
            A consolidated production manifest dictionary.
        """
        self.logger.info(f"Assembling timeline for session: {session_id}")

        # Extract metadata from summary
        metadata = session_summary.get("metadata", {})
        shot_list = session_summary.get("shots", [])

        manifest = {
            "session_id": session_id,
            "metadata": {
                "autonomy_score": metadata.get("autonomy_score"),
                "total_shots": len(shot_list),
                "learnings": metadata.get("learnings", []),
                "created_at": metadata.get("created_at")
            },
            "production_shots": []
        }

        for index, shot in enumerate(shot_list):
            # Build per-shot details
            shot_entry = {
                "sequence_order": index,
                "asset_path": shot.get("asset_path"),
                "audio_path": shot.get("audio_path"),
                "duration": shot.get("duration"),
                "iterations": shot.get("iterations", 1),
                "kimi_reasoning": shot.get("kimi_reasoning_trace"),
                "final_prompt": shot.get("final_prompt"),
                "audit_status": shot.get("audit_status", "pending")
            }

            # Graceful handling of missing asset paths with warnings in the manifest
            if not shot_entry["asset_path"] or not os.path.exists(shot_entry["asset_path"]):
                self.logger.warning(f"Missing or invalid asset path for shot {index}: {shot_entry['asset_path']}")
                shot_entry["warning"] = f"Asset path missing or unreachable: {shot_entry['asset_path']}"

            if not shot_entry["audio_path"] or not os.path.exists(shot_entry["audio_path"]):
                self.logger.warning(f"Missing or invalid audio path for shot {index}: {shot_entry['audio_path']}")
                shot_entry["audio_warning"] = f"Audio path missing or unreachable: {shot_entry['audio_path']}"

            manifest["production_shots"].append(shot_entry)

        self.logger.info(f"Assembly complete for session {session_id} with {len(manifest['production_shots'])} shots.")
        return manifest

    def export_ffmpeg_manifest(self, assembly: Dict[str, Any]) -> str:
        """
        Generates an ffmpeg concat script path.
        Simulated/placeholder for hackathon demo purposes.
        
        Args:
            assembly: The consolidated production manifest.
            
        Returns:
            Path to the generated ffmpeg concat script.
        """
        self.logger.info("Generating ffmpeg concat script (simulated)...")
        
        # In a real implementation, this would write a text file with 'file /path/to/asset' lines
        # For the hackathon demo, we return a placeholder path.
        placeholder_path = f"/tmp/cinesmith_{assembly['session_id']}_concat.txt"
        
        # Simulate writing the file (optional but good for demonstration)
        try:
            with open(placeholder_path, "w", encoding="utf-8") as f:
                f.write("# Simulated ffmpeg concat script\n")
                for shot in assembly.get("production_shots", []):
                    if shot.get("asset_path") and os.path.exists(shot["asset_path"]):
                        f.write(f"file '{os.path.abspath(shot['asset_path'])}'\n")
                    else:
                        f.write(f"# Skipping missing asset: {shot.get('asset_path')}\n")
            self.logger.info(f"Simulated concat script created at: {placeholder_path}")
        except Exception as e:
            self.logger.error(f"Failed to simulate ffmpeg manifest export: {e}")
            return ""

        return placeholder_path
