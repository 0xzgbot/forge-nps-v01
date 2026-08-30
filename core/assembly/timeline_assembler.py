import os
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class TimelineAssembler:
    """
    Consolidates session metadata, shot assets, and audio into a production
    manifest, then (optionally) runs ffmpeg concat while keeping stereo audio.
    """

    def __init__(self):
        self.logger = logger

    async def assemble(self, session_id: str, session_summary: Dict[str, Any]) -> Dict[str, Any]:
        self.logger.info(f"Assembling timeline for session: {session_id}")

        metadata = session_summary.get("metadata", {})
        shot_list = session_summary.get("shots", [])

        manifest = {
            "session_id": session_id,
            "metadata": {
                "autonomy_score": metadata.get("autonomy_score"),
                "total_shots": len(shot_list),
                "learnings": metadata.get("learnings", []),
                "created_at": metadata.get("created_at"),
            },
            "production_shots": [],
        }

        for index, shot in enumerate(shot_list):
            shot_entry = {
                "sequence_order": index,
                "asset_path": shot.get("asset_path"),
                "audio_path": shot.get("audio_path"),
                "duration": shot.get("duration"),
                "iterations": shot.get("iterations", 1),
                "kimi_reasoning": shot.get("kimi_reasoning_trace"),
                "final_prompt": shot.get("final_prompt"),
                "audit_status": shot.get("audit_status", "pending"),
            }

            if not shot_entry["asset_path"] or not os.path.exists(shot_entry["asset_path"]):
                self.logger.warning(f"Missing or invalid asset path for shot {index}: {shot_entry['asset_path']}")
                shot_entry["warning"] = f"Asset path missing or unreachable: {shot_entry['asset_path']}"

            if not shot_entry["audio_path"] or not os.path.exists(shot_entry["audio_path"]):
                self.logger.warning(f"Missing or invalid audio path for shot {index}: {shot_entry['audio_path']}")
                shot_entry["audio_warning"] = f"Audio path missing or unreachable: {shot_entry['audio_path']}"

            manifest["production_shots"].append(shot_entry)

        self.logger.info(f"Assembly complete for session {session_id} with {len(manifest['production_shots'])} shots.")
        return manifest

    def export_ffmpeg_manifest(self, assembly: Dict[str, Any], dest: Optional[str] = None) -> str:
        """Write an ffmpeg concat demuxer list for existing clip files."""
        session_id = str(assembly.get("session_id") or "session")
        placeholder_path = dest or f"/tmp/cinesmith_{session_id}_concat.txt"
        try:
            with open(placeholder_path, "w", encoding="utf-8") as f:
                f.write("ffconcat version 1.0\n")
                for shot in assembly.get("production_shots", []):
                    asset = shot.get("asset_path")
                    if asset and os.path.exists(asset):
                        escaped = os.path.abspath(asset).replace("'", r"'\''")
                        f.write(f"file '{escaped}'\n")
                    else:
                        f.write(f"# Skipping missing asset: {asset}\n")
            self.logger.info(f"Concat script created at: {placeholder_path}")
        except Exception as e:
            self.logger.error(f"Failed to write ffmpeg manifest: {e}")
            return ""
        return placeholder_path

    def export_cut(
        self,
        clips: List[Path],
        output: Path,
        *,
        keep_audio: bool = True,
    ) -> Dict[str, Any]:
        """Concat clips with ffmpeg. Prefer stream copy; re-encode if needed. Keep stereo."""
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            return {"ok": False, "error": "ffmpeg_not_installed", "output": ""}
        existing = [Path(c) for c in clips if Path(c).exists()]
        if not existing:
            return {"ok": False, "error": "no_clips", "output": ""}
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        concat_path = output.with_suffix(".concat.txt")
        lines = ["ffconcat version 1.0\n"]
        for path in existing:
            escaped = path.resolve().as_posix().replace("'", r"'\''")
            lines.append(f"file '{escaped}'\n")
        concat_path.write_text("".join(lines), encoding="utf-8")
        copy_cmd = [
            ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_path),
            "-c", "copy", str(output),
        ]
        proc = subprocess.run(copy_cmd, capture_output=True, text=True)
        if proc.returncode == 0 and output.exists() and output.stat().st_size > 0:
            return {"ok": True, "output": str(output), "mode": "copy", "clips": [str(p) for p in existing]}
        encode_cmd = [
            ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_path),
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac" if keep_audio else "copy",
            "-ac", "2",
            "-movflags", "+faststart",
            str(output),
        ]
        if not keep_audio:
            encode_cmd = [
                ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_path),
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an",
                "-movflags", "+faststart",
                str(output),
            ]
        proc = subprocess.run(encode_cmd, capture_output=True, text=True)
        if proc.returncode == 0 and output.exists() and output.stat().st_size > 0:
            return {"ok": True, "output": str(output), "mode": "reencode", "clips": [str(p) for p in existing]}
        return {
            "ok": False,
            "error": (proc.stderr or proc.stdout or "ffmpeg_failed")[-800:],
            "output": "",
        }
