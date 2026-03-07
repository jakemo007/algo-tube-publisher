# assemble_video.py
# ─────────────────────────────────────────────────────────────────────────────
# Pure MoviePy assembler optimized for Cinematic Multi-Clips.
#
# Per-scene:
#   1. Dynamically load ALL clips for a scene (scene_Na, scene_Nb, etc.)
#   2. Resize to 9:16 via MoviePy resize()
#   3. BOOMERANG LOOP to match audio length seamlessly
#   4. Attach narration audio
#   5. White flash at scene start (scenes 2-6)
#   6. Fade in scene 1 / fade out scene 6
# ─────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import glob
import json
import logging
import os
from pathlib import Path

import numpy as np

from moviepy.editor import (
    AudioFileClip,
    ColorClip,
    CompositeVideoClip,
    VideoFileClip,
    concatenate_videoclips,
)
import moviepy.video.fx.all as vfx

from config import (
    ASSETS_DIR,
    LOG_FILE,
    LOG_LEVEL,
    OUTPUT_VIDEO,
    SCRIPT_FILE,
)

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.DEBUG),
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

# ── Target dimensions (YouTube Shorts 9:16) ───────────────────────────────────
TARGET_W: int = 1080
TARGET_H: int = 1920

# ── Render settings ───────────────────────────────────────────────────────────
VIDEO_FPS: int      = 30
VIDEO_CODEC: str    = "libx264"
AUDIO_CODEC: str    = "aac"
RENDER_PRESET: str  = "fast"
RENDER_THREADS: int = 4

# ── Transition settings ───────────────────────────────────────────────────────
FLASH_DURATION: float = 0.25
FADE_IN_DUR: float    = 0.40
FADE_OUT_DUR: float   = 0.55


# ─────────────────────────────────────────────────────────────────────────────
# 9:16 crop using MoviePy resize + crop
# ─────────────────────────────────────────────────────────────────────────────

def _fit_to_916(clip: VideoFileClip) -> VideoFileClip:
    """Scale so height = TARGET_H, then centre-crop width to TARGET_W."""
    clip = clip.resize(height=TARGET_H)
    w, h = clip.size
    if w > TARGET_W:
        x1   = (w - TARGET_W) // 2
        clip = clip.crop(x1=x1, y1=0, x2=x1 + TARGET_W, y2=TARGET_H)
    return clip


# ─────────────────────────────────────────────────────────────────────────────
# White flash transition
# ─────────────────────────────────────────────────────────────────────────────

def _white_flash(clip: VideoFileClip) -> VideoFileClip:
    w, h  = clip.size
    flash = (
        ColorClip(size=(w, h), color=(255, 255, 255))
        .set_duration(FLASH_DURATION)
        .crossfadeout(FLASH_DURATION)
    )
    return CompositeVideoClip([clip, flash])


# ─────────────────────────────────────────────────────────────────────────────
# Seamless Boomerang Loop
# ─────────────────────────────────────────────────────────────────────────────

def _boomerang_clip_to_audio(clip: VideoFileClip, audio: AudioFileClip) -> VideoFileClip:
    """
    If audio is longer than the video, loops the video (forward, reverse, forward)
    until it matches the audio exactly, preventing hard-cut glitches.
    """
    if audio.duration <= clip.duration:
        logger.debug("Scene audio (%.2fs) <= video (%.2fs); trimming video.", audio.duration, clip.duration)
        return clip.subclip(0, audio.duration).set_audio(audio)
        
    logger.debug("Scene audio (%.2fs) > video (%.2fs); boomeranging video.", audio.duration, clip.duration)
    
    # Trim the last 0.1s off to prevent FFMPEG reversing corrupted metadata
    safe_duration = max(0.1, clip.duration - 0.1)
    safe_clip = clip.subclip(0, safe_duration)
    
    clip_reversed = safe_clip.fx(vfx.time_mirror)
    
    loop_clips = [safe_clip]
    current_duration = safe_clip.duration
    use_reverse = True
    
    while current_duration < audio.duration:
        next_clip = clip_reversed if use_reverse else safe_clip
        loop_clips.append(next_clip)
        current_duration += next_clip.duration
        use_reverse = not use_reverse 
        
    full_looped_video = concatenate_videoclips(loop_clips)
    final_video = full_looped_video.subclip(0, audio.duration)
    
    return final_video.set_audio(audio)


# ─────────────────────────────────────────────────────────────────────────────
# Scene builder
# ─────────────────────────────────────────────────────────────────────────────

def _join_luma_clips(index: int) -> VideoFileClip | None:
    """Dynamically load ALL clips for a scene (e.g., scene_1a, scene_1b) and join them."""
    
    # Use glob to find any file matching scene_1a, scene_1b, scene_1c, etc.
    pattern = str(Path(ASSETS_DIR) / f"scene_{index}[a-z].mp4")
    clip_paths = sorted(glob.glob(pattern))

    # If no letter-graded clips exist, look for the legacy single file
    if not clip_paths:
        path_leg = Path(ASSETS_DIR) / f"scene_{index}.mp4"
        if path_leg.exists():
            logger.warning("Scene %d — using legacy scene_%d.mp4.", index, index)
            return VideoFileClip(str(path_leg))
        
        logger.error("Scene %d — no video clips found.", index)
        return None

    # Load all found clips
    clips = [VideoFileClip(p) for p in clip_paths]
    
    if len(clips) == 1:
        logger.debug("Scene %d — only 1 clip found (%s)", index, Path(clip_paths[0]).name)
        return clips[0]

    logger.debug("Scene %d — joining %d clips together.", index, len(clips))
    return concatenate_videoclips(clips, method="compose")


def _build_scene_clip(index: int, total: int) -> VideoFileClip | None:
    audio_path = Path(ASSETS_DIR) / f"voice_{index}.mp3"
    if not audio_path.exists():
        logger.error("Missing audio '%s'.", audio_path)
        return None

    logger.info("Scene %d/%d — loading…", index, total)
    clip = _join_luma_clips(index)
    if clip is None:
        return None

    audio = AudioFileClip(str(audio_path))

    # 9:16 crop
    logger.debug("Scene %d — 9:16 crop…", index)
    clip = _fit_to_916(clip)

    # Safely match video length to audio using Boomerang Loop
    clip = _boomerang_clip_to_audio(clip, audio)

    # Transitions
    if index > 1:
        logger.debug("Scene %d — white flash…", index)
        clip = _white_flash(clip)

    if index == 1:
        clip = clip.fadein(FADE_IN_DUR)
    if index == total:
        clip = clip.fadeout(FADE_OUT_DUR)

    logger.info("Scene %d ready — %.2fs", index, clip.duration)
    return clip


# ─────────────────────────────────────────────────────────────────────────────
# Script loader
# ─────────────────────────────────────────────────────────────────────────────

def _load_script(filepath: str) -> dict | None:
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error("Script '%s' not found.", filepath)
    except json.JSONDecodeError as exc:
        logger.error("Invalid JSON in '%s': %s", filepath, exc)
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Main assembler
# ─────────────────────────────────────────────────────────────────────────────

def build_final_video() -> bool:
    script_data = _load_script(SCRIPT_FILE)
    if not script_data:
        return False

    scenes: list[dict] = script_data.get("scenes", [])
    if not scenes:
        logger.error("No scenes in script.")
        return False

    total = len(scenes)
    logger.info(
        "Assembly — %d scenes → '%s'  [%dx%d @ %dfps]",
        total, OUTPUT_VIDEO, TARGET_W, TARGET_H, VIDEO_FPS,
    )

    final_clips: list[VideoFileClip] = []

    for i, scene in enumerate(scenes, start=1):
        clip = _build_scene_clip(i, total)
        if clip is None:
            logger.error("Aborting — scene %d failed.", i)
            for c in final_clips:
                try: c.close()
                except: pass
            return False
        final_clips.append(clip)

    logger.info("Concatenating %d scenes into final video…", total)
    final_video = concatenate_videoclips(final_clips, method="compose")

    logger.info("Rendering '%s'…", OUTPUT_VIDEO)
    final_video.write_videofile(
        OUTPUT_VIDEO,
        fps=VIDEO_FPS,
        codec=VIDEO_CODEC,
        audio_codec=AUDIO_CODEC,
        preset=RENDER_PRESET,
        threads=RENDER_THREADS,
        logger="bar",   # shows progress bar in terminal
    )

    duration = final_video.duration
    final_video.close()
    for clip in final_clips:
        try: clip.close()
        except: pass

    size_mb = os.path.getsize(OUTPUT_VIDEO) / 1_048_576
    logger.info("Done! '%s' — %.1f MB, %.1fs", OUTPUT_VIDEO, size_mb, duration)
    return True


if __name__ == "__main__":
    build_final_video()