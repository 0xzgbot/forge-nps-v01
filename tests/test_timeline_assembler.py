import pytest
import asyncio
import os
from core.assembly.timeline_assembler import TimelineAssembler

@pytest.mark.asyncio
async def test_timeline_assembler():
    assembler = TimelineAssembler()
    session_id = "test_session_123"
    
    # Mock assets for testing
    temp_asset = "/tmp/test_shot.mp4"
    temp_audio = "/tmp/test_audio.wav"
    
    with open(temp_asset, "w", encoding="utf-8") as f:
        f.write("dummy video content")
    with open(temp_audio, "w", encoding="utf-8") as f:
        f.write("dummy audio content")

    session_summary = {
        "metadata": {
            "autonomy_score": 0.85,
            "learnings": ["Use more cinematic lighting", "Avoid fast cuts"],
            "created_at": "2026-04-20T19:20:00Z"
        },
        "shots": [
            {
                "asset_path": temp_asset,
                "audio_path": temp_audio,
                "duration": 5.0,
                "iterations": 2,
                "kimi_reasoning_trace": "Improved lighting via prompt engineering.",
                "final_prompt": "Cinematic shot of a forest at dawn",
                "audit_status": "passed"
            },
            {
                "asset_path": "/tmp/non_existent.mp4",  # Missing asset test
                "audio_path": temp_audio,
                "duration": 3.5,
                "iterations": 1,
                "kimi_reasoning_trace": "Standard shot.",
                "final_prompt": "A simple mountain view",
                "audit_status": "pending"
            }
        ]
    }

    print("--- Running Assembly ---")
    manifest = await assembler.assemble(session_id, session_summary)
    import json
    print(json.dumps(manifest, indent=2))

    print("\n--- Testing FFMPEG Export ---")
    concat_path = assembler.export_ffmpeg_manifest(manifest)
    print(f"Concat script path: {concat_path}")
    
    if os.path.exists(concat_path):
        print("Concat script content:")
        with open(concat_path, "r", encoding="utf-8") as f:
            print(f.read())

    # Cleanup
    os.remove(temp_asset)
    os.remove(temp_audio)
    if os.path.exists(concat_path):
        os.remove(concat_path)

if __name__ == "__main__":
    asyncio.run(test_timeline_assembler())
