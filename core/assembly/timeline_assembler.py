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

    def _silence_clip(self, ffmpeg: str, path: Path, dest: Path) -> Optional[Path]:
        dest.parent.mkdir(parents=True, exist_ok=True)
        copy_cmd = [ffmpeg, "-y", "-i", str(path), "-c:v", "copy", "-an", str(dest)]
        proc = subprocess.run(copy_cmd, capture_output=True, text=True)
        if proc.returncode == 0 and dest.exists() and dest.stat().st_size > 0:
            return dest
        encode_cmd = [
            ffmpeg, "-y", "-i", str(path),
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an",
            str(dest),
        ]
        proc = subprocess.run(encode_cmd, capture_output=True, text=True)
        if proc.returncode == 0 and dest.exists() and dest.stat().st_size > 0:
            return dest
        self.logger.warning("Could not mute clip %s: %s", path, (proc.stderr or "")[-200:])
        return None

    def export_cut(
        self,
        clips: List[Path],
        output: Path,
        *,
        keep_audio: bool = True,
        muted_paths: Optional[List[Path]] = None,
    ) -> Dict[str, Any]:
        """Concat clips with ffmpeg. Prefer stream copy; re-encode if needed. Keep stereo.

        muted_paths strip audio on those clips only. Unmuted H3 clips keep stereo (-ac 2).
        """
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            return {"ok": False, "error": "ffmpeg_not_installed", "output": ""}
        existing = [Path(c) for c in clips if Path(c).exists()]
        if not existing:
            return {"ok": False, "error": "no_clips", "output": ""}
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        muted = {str(Path(p).resolve()) for p in (muted_paths or [])}
        prepared: List[Path] = []
        mute_dir = output.parent / f".{output.stem}_mute"
        for path in existing:
            if keep_audio and str(path.resolve()) in muted:
                silent = self._silence_clip(ffmpeg, path, mute_dir / f"{path.stem}.muted{path.suffix}")
                prepared.append(silent or path)
            else:
                prepared.append(path)
        any_audio = keep_audio and any(str(path.resolve()) not in muted for path in existing)
        concat_path = output.with_suffix(".concat.txt")
        lines = ["ffconcat version 1.0\n"]
        for path in prepared:
            escaped = path.resolve().as_posix().replace("'", r"'\''")
            lines.append(f"file '{escaped}'\n")
        concat_path.write_text("".join(lines), encoding="utf-8")
        can_copy = any_audio and not muted
        if can_copy:
            copy_cmd = [
                ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_path),
                "-c", "copy", str(output),
            ]
            proc = subprocess.run(copy_cmd, capture_output=True, text=True)
            if proc.returncode == 0 and output.exists() and output.stat().st_size > 0:
                return {
                    "ok": True,
                    "output": str(output),
                    "mode": "copy",
                    "clips": [str(p) for p in existing],
                    "muted": [str(p) for p in existing if str(p.resolve()) in muted],
                }
        encode_cmd = [
            ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_path),
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            str(output),
        ]
        if any_audio:
            encode_cmd = encode_cmd[:-1] + ["-c:a", "aac", "-ac", "2", str(output)]
        else:
            encode_cmd = encode_cmd[:-1] + ["-an", str(output)]
        proc = subprocess.run(encode_cmd, capture_output=True, text=True)
        if proc.returncode == 0 and output.exists() and output.stat().st_size > 0:
            return {
                "ok": True,
                "output": str(output),
                "mode": "reencode",
                "clips": [str(p) for p in existing],
                "muted": [str(p) for p in existing if str(p.resolve()) in muted],
            }
        return {
            "ok": False,
            "error": (proc.stderr or proc.stdout or "ffmpeg_failed")[-800:],
            "output": "",
        }

    def extract_frame(self, clip: Path, time_sec: float, dest: Path) -> Dict[str, Any]:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            return {"ok": False, "error": "ffmpeg_not_installed"}
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            ffmpeg, "-y", "-ss", f"{max(0.0, float(time_sec)):.3f}",
            "-i", str(clip), "-frames:v", "1", "-q:v", "2", str(dest),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode == 0 and dest.exists() and dest.stat().st_size > 0:
            return {"ok": True, "output": str(dest)}
        return {"ok": False, "error": (proc.stderr or "extract_failed")[-400:]}

    def slice_clip(self, clip: Path, start_sec: float, end_sec: Optional[float], dest: Path) -> Dict[str, Any]:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            return {"ok": False, "error": "ffmpeg_not_installed"}
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        cmd = [ffmpeg, "-y", "-ss", f"{max(0.0, float(start_sec)):.3f}", "-i", str(clip)]
        if end_sec is not None:
            duration = max(0.04, float(end_sec) - float(start_sec))
            cmd += ["-t", f"{duration:.3f}"]
        cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-ac", "2", str(dest)]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode == 0 and dest.exists() and dest.stat().st_size > 0:
            return {"ok": True, "output": str(dest)}
        return {"ok": False, "error": (proc.stderr or "slice_failed")[-400:]}

    def stitch_range(
        self,
        original: Path,
        middle: Path,
        start_sec: float,
        end_sec: float,
        dest: Path,
    ) -> Dict[str, Any]:
        """Keep original before start and after end; replace the middle with a new take."""
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            return {"ok": False, "error": "ffmpeg_not_installed"}
        work = Path(dest).parent / f".{Path(dest).stem}_range"
        work.mkdir(parents=True, exist_ok=True)
        parts: List[Path] = []
        if float(start_sec) > 0.04:
            prefix = work / "prefix.mp4"
            pre = self.slice_clip(original, 0.0, float(start_sec), prefix)
            if not pre.get("ok"):
                return pre
            parts.append(prefix)
        if Path(middle).exists():
            parts.append(Path(middle))
        suffix = work / "suffix.mp4"
        post = self.slice_clip(original, float(end_sec), None, suffix)
        if post.get("ok"):
            parts.append(suffix)
        if not parts:
            return {"ok": False, "error": "nothing_to_stitch"}
        return self.export_cut(parts, Path(dest), keep_audio=True)

    def color_pass(self, clip: Path, dest: Path, *, preset: str = "") -> Dict[str, Any]:
        """Mild continuity grade. Does not replace H3 stereo."""
        from core.hermes.produce.finish import color_vf

        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            return {"ok": False, "error": "ffmpeg_not_installed"}
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        vf = color_vf(preset)
        copy_cmd = [
            ffmpeg, "-y", "-i", str(clip), "-vf", vf,
            "-c:a", "copy", "-movflags", "+faststart", str(dest),
        ]
        proc = subprocess.run(copy_cmd, capture_output=True, text=True)
        if proc.returncode == 0 and dest.exists() and dest.stat().st_size > 0:
            return {"ok": True, "output": str(dest), "mode": "color"}
        encode_cmd = [
            ffmpeg, "-y", "-i", str(clip), "-vf", vf,
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-ac", "2",
            "-movflags", "+faststart", str(dest),
        ]
        proc = subprocess.run(encode_cmd, capture_output=True, text=True)
        if proc.returncode == 0 and dest.exists() and dest.stat().st_size > 0:
            return {"ok": True, "output": str(dest), "mode": "color"}
        return {"ok": False, "error": (proc.stderr or "color_pass_failed")[-400:]}
