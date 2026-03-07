# generate_media.py
# ─────────────────────────────────────────────────────────────────────────────
# 2D ANIME PIPELINE (KLING AI):
# 1. FLUX generates a 2D Anime style character reference image.
# 2. ImgBB hosts the image.
# 3. ElevenLabs generates the voiceover.
# 4. Kling AI (v1.5 Standard) takes the image and animates it with heavy anime 
#    action prompts to create a high-retention, cinematic mini-movie.
# ─────────────────────────────────────────────────────────────────────────────

import base64
import json
import logging
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs

from config import (
    ASSETS_DIR,
    CHARACTER_IMAGE_PATH,
    CHECKPOINT_FILE,
    ELEVENLABS_MODEL_ID,
    ELEVENLABS_OUTPUT_FORMAT,
    ELEVENLABS_VOICE_ID,
    HF_IMAGE_API_URL,
    HF_MAX_RETRIES,
    HF_RETRY_SLEEP,
    IMGBB_UPLOAD_URL,
    LOG_FILE,
    LOG_LEVEL,
    RAG_BYPASS_CACHE,
    SCRIPT_FILE,
)
from drive_client import (
    download_file,
    get_animal_folder_id,
    get_drive_service,
    upload_file,
)
from rag_database import ingest_new_video, search_video_cache

# We use 2 clips per scene for that fast-paced cinematic editing
KLING_CLIPS_PER_SCENE = 2
KLING_POLL_INTERVAL = 10
KLING_TIMEOUT_SECONDS = 600 # Kling can take slightly longer than Luma

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.DEBUG),
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

load_dotenv()

def _require_env(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise EnvironmentError(f"Required env var '{key}' missing from .env")
    return value

HF_API_KEY: str         = _require_env("HUGGINGFACE_API_KEY")
IMGBB_API_KEY: str      = _require_env("IMGBB_API_KEY")
ELEVENLABS_API_KEY: str = _require_env("ELEVENLABS_API_KEY")
KLING_API_KEY: str      = _require_env("KLING_API_KEY") # Add this to your .env file!

eleven_client = ElevenLabs(api_key=ELEVENLABS_API_KEY)


# ─────────────────────────────────────────────────────────────────────────────
# Checkpoint helpers
# ─────────────────────────────────────────────────────────────────────────────
def _load_checkpoint() -> dict:
    if not os.path.exists(CHECKPOINT_FILE):
        return {}
    try:
        with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data
    except (json.JSONDecodeError, OSError):
        return {}

def _save_checkpoint(cp: dict) -> None:
    try:
        with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
            json.dump(cp, f, indent=2)
    except OSError:
        pass

def _clear_checkpoint() -> None:
    try:
        if os.path.exists(CHECKPOINT_FILE):
            os.remove(CHECKPOINT_FILE)
    except OSError:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# FLUX: 2D Anime Image Generator
# ─────────────────────────────────────────────────────────────────────────────
def generate_character_image(character_design: str, character_setting: str) -> bool:
    logger.info("Generating FLUX 2D Anime character reference image…")
    
    # We aggressively force the 2D Anime style here so Kling knows what to animate
    anime_suffix = "High quality 2D anime style, Studio Ghibli, flat colors, clean cel-shaded outlines, vibrant anime lighting, colorful illustration."
    
    flux_prompt = (
        f"{character_design}, "
        f"{character_setting}. "
        "Character centered in frame, full body visible. "
        f"{anime_suffix}"
    )
    logger.debug("FLUX prompt: %s", flux_prompt[:180])

    headers = {"Authorization": f"Bearer {HF_API_KEY}"}
    Path(CHARACTER_IMAGE_PATH).parent.mkdir(parents=True, exist_ok=True)

    for attempt in range(1, HF_MAX_RETRIES + 1):
        try:
            response = requests.post(
                HF_IMAGE_API_URL,
                headers=headers,
                json={"inputs": flux_prompt},
                timeout=90,
            )
            if response.status_code == 200:
                with open(CHARACTER_IMAGE_PATH, "wb") as f:
                    f.write(response.content)
                logger.info("Character image saved: %s", CHARACTER_IMAGE_PATH)
                return True
        except requests.RequestException:
            logger.exception("HF request error (attempt %d/%d).", attempt, HF_MAX_RETRIES)
        time.sleep(HF_RETRY_SLEEP)
    return False

# ─────────────────────────────────────────────────────────────────────────────
# ImgBB upload (Required for Kling)
# ─────────────────────────────────────────────────────────────────────────────
def upload_to_imgbb(image_path: str) -> str | None:
    logger.info("Uploading reference image to ImgBB…")
    try:
        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        res = requests.post(
            IMGBB_UPLOAD_URL,
            data={"key": IMGBB_API_KEY, "image": b64},
            timeout=30,
        )
        res.raise_for_status()
        url: str = res.json()["data"]["url"]
        logger.info("ImgBB URL: %s", url)
        return url
    except requests.RequestException:
        logger.exception("ImgBB upload failed.")
    return None

# ─────────────────────────────────────────────────────────────────────────────
# ElevenLabs audio
# ─────────────────────────────────────────────────────────────────────────────
def generate_scene_audio(text: str, index: int) -> bool:
    logger.info("Scene %d — ElevenLabs voiceover…", index)
    filename = Path(ASSETS_DIR) / f"voice_{index}.mp3"
    try:
        response = eleven_client.text_to_speech.convert(
            text=text,
            voice_id=ELEVENLABS_VOICE_ID,
            model_id=ELEVENLABS_MODEL_ID,
            output_format=ELEVENLABS_OUTPUT_FORMAT,
        )
        with open(filename, "wb") as f:
            for chunk in response:
                if chunk:
                    f.write(chunk)
        return True
    except Exception:
        logger.exception("Scene %d — ElevenLabs failed.", index)
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Kling AI API Wrapper & Prompt Builders
# ─────────────────────────────────────────────────────────────────────────────

_CAMERA_PROGRESSIONS: list[tuple[str, str]] = [
    ("fast zoom in shot, action lines", "dynamic low-angle hero shot"),
    ("sudden close-up shot, intense anime eyes", "fast tracking shot following action"),
    ("fast panning action shot", "whip pan to character close-up"),
    ("dutch angle dramatic shot", "fast aerial overhead shot"),
]

def _build_kling_prompts(
    scene_action: str,
    scene_environment: str,
    scene_index: int,
) -> tuple[str, str]:
    """
    Builds two distinct prompts for Kling to generate a cinematic A/B cut.
    Forces 2D anime styling.
    """
    cam_a, cam_b = _CAMERA_PROGRESSIONS[(scene_index - 1) % len(_CAMERA_PROGRESSIONS)]

    base = (
        "2D Anime style animation, Studio Ghibli aesthetic, flat colors, clean lines. "
        "HIGH SPEED MOTION, fluid anime physics. "
    )

    prompt_a = (
        f"{base}"
        f"Camera: {cam_a}. "
        f"Action: {scene_action}. "
        f"Environment: {scene_environment}. "
        "Exaggerated, energetic anime movement."
    )

    # Evolve the action for the second clip
    continuation_actions = {
        "jump": "mid-air freeze frame before landing explosively",
        "spin": "spinning with anime speed lines surrounding them",
        "run": "sprinting forward, leaving a dust cloud behind",
        "gasp": "huge sweat drop on forehead, extremely shocked anime expression",
        "hug": "crying waterfalls of happy anime tears",
    }
    
    cont_action = "moving dynamically through the scene with fast anime physics"
    action_lower = scene_action.lower()
    for stem, replacement in continuation_actions.items():
        if stem in action_lower:
            cont_action = replacement
            break

    prompt_b = (
        f"{base}"
        f"Camera: {cam_b}. "
        f"Action: {cont_action}. "
        f"Environment: {scene_environment}. "
    )

    return prompt_a, prompt_b

def generate_kling_video(prompt: str, image_url: str, video_path: str) -> bool:
    """
    Custom REST wrapper for the Kling AI v1.5 Standard API.
    Costs ~$0.10 per clip instead of Luma's $0.32.
    """
    logger.info("Submitting generation to Kling AI (v1.5 Standard)…")
    
    headers = {
        "Authorization": f"Bearer {KLING_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # 1. Submit the Task
    submit_url = "https://api.klingai.com/v1/videos/image2video"
    payload = {
        "model_name": "kling-v1-5", # Standard v1.5 model
        "prompt": prompt,
        "image": image_url,
        "duration": 5, # 5 second clips
    }
    
    try:
        response = requests.post(submit_url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        task_data = response.json()
        task_id = task_data.get("data", {}).get("task_id")
        
        if not task_id:
            logger.error("Kling API rejected submission: %s", task_data)
            return False
            
        logger.info("Kling task submitted (id=%s). Waiting for render...", task_id)
    except requests.RequestException as e:
        logger.error("Failed to connect to Kling API: %s", e)
        return False

    # 2. Poll for Completion
    poll_url = f"https://api.klingai.com/v1/videos/image2video/{task_id}"
    deadline = time.time() + KLING_TIMEOUT_SECONDS
    
    while time.time() < deadline:
        try:
            status_res = requests.get(poll_url, headers=headers, timeout=30)
            status_data = status_res.json()
            state = status_data.get("data", {}).get("task_status")
            
            if state == "succeed":
                # 3. Download the Video
                video_url = status_data.get("data", {}).get("task_result", {}).get("videos", [{}])[0].get("url")
                if video_url:
                    logger.info("Kling render complete! Downloading...")
                    vid_res = requests.get(video_url, timeout=120)
                    with open(video_path, "wb") as f:
                        f.write(vid_res.content)
                    return True
                else:
                    logger.error("Kling finished but provided no video URL.")
                    return False
                    
            elif state == "failed":
                logger.error("Kling generation failed internally: %s", status_data)
                return False
                
            time.sleep(KLING_POLL_INTERVAL)
            
        except requests.RequestException:
            logger.warning("Kling polling error. Retrying...")
            time.sleep(KLING_POLL_INTERVAL)
            
    logger.error("Kling generation timed out.")
    return False

# ─────────────────────────────────────────────────────────────────────────────
# Scene processors
# ─────────────────────────────────────────────────────────────────────────────
def _process_scene_audio(scene: dict, index: int, drive_service, animal_folder_id: str) -> None:
    audio_path = Path(ASSETS_DIR) / f"voice_{index}.mp3"
    if not audio_path.exists():
        narration = scene.get("narration") or ""
        generate_scene_audio(narration, index)
    upload_file(drive_service, str(audio_path), animal_folder_id)

def _process_scene_video(
    scene: dict, index: int, frame0_url: str, character_design: str,
    animal: str, drive_service, animal_folder_id: str,
) -> bool:
    
    scene_action      = scene.get("scene_action", "moving quickly")
    scene_environment = scene.get("scene_environment", "a colourful magical world")
    
    cache_key = f"2D_ANIME | {character_design} | {scene_action} | {scene_environment}"

    prompt_a, prompt_b = _build_kling_prompts(scene_action, scene_environment, index)
    clip_prompts = [prompt_a, prompt_b]
    clip_labels  = [chr(ord("a") + i) for i in range(KLING_CLIPS_PER_SCENE)]

    for clip_label, luma_prompt in zip(clip_labels, clip_prompts):
        clip_fname = f"scene_{index}{clip_label}.mp4"
        clip_path  = str(Path(ASSETS_DIR) / clip_fname)

        if os.path.exists(clip_path):
            continue

        if clip_label == "a" and not RAG_BYPASS_CACHE:
            # Reusing Outro logic for Scene 6
            search_key = cache_key if index != 6 else "2D_ANIME | Outro | Subscribe action."
            cache_meta = search_video_cache(search_key, animal="generic" if index == 6 else animal)
            
            if cache_meta and cache_meta.get("drive_file_id"):
                if download_file(drive_service, cache_meta["drive_file_id"], clip_path):
                    import shutil
                    for other_label in clip_labels[1:]:
                        other_path = str(Path(ASSETS_DIR) / f"scene_{index}{other_label}.mp4")
                        if not os.path.exists(other_path):
                            shutil.copy2(clip_path, other_path)
                    return True

        # CALLING KLING INSTEAD OF LUMA
        if not generate_kling_video(luma_prompt, frame0_url, clip_path):
            return False

        file_id = upload_file(drive_service, clip_path, animal_folder_id, clip_fname)
        
        if clip_label == "a" and file_id:
            ingest_key = cache_key if index != 6 else "2D_ANIME | Outro | Subscribe action."
            ingest_new_video(
                scene_description=ingest_key,
                drive_file_id=file_id,
                animal="generic" if index == 6 else animal,
                file_name=clip_fname,
            )

    return True

# ─────────────────────────────────────────────────────────────────────────────
# Master Pipeline
# ─────────────────────────────────────────────────────────────────────────────
def _load_script(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        raise

def _extract_animal_name(data: dict) -> str:
    name = data.get("animal_name", "").strip()
    return name.title() if name else "Animal"

def run_media_pipeline() -> bool:
    Path(ASSETS_DIR).mkdir(exist_ok=True)
    data              = _load_script(SCRIPT_FILE)
    scenes            = data.get("scenes", [])
    char_design: str  = data.get("character_design", "A cute 2D anime animal")
    char_setting: str = data.get("character_setting", "In a beautiful anime landscape")
    animal            = _extract_animal_name(data)
    total             = len(scenes)

    if not scenes: return False

    drive_service = get_drive_service()
    if not drive_service: return False

    animal_folder_id = get_animal_folder_id(drive_service, animal)
    if not animal_folder_id: return False

    checkpoint        = _load_checkpoint()
    completed_scenes: list[int] = checkpoint.get("completed_scenes", [])
    
    # Restoring the FLUX image lock for consistent 2D faces!
    frame0_url: str | None = checkpoint.get("character_image_url")

    char_on_disk = os.path.exists(CHARACTER_IMAGE_PATH)
    if not char_on_disk:
        if not generate_character_image(char_design, char_setting):
            return False
        frame0_url = None
        checkpoint.pop("character_image_url", None)
        checkpoint["char_image_in_drive"] = False
        _save_checkpoint(checkpoint)

    if not frame0_url:
        frame0_url = upload_to_imgbb(CHARACTER_IMAGE_PATH)
        if not frame0_url:
            return False
        checkpoint["character_image_url"] = frame0_url
        _save_checkpoint(checkpoint)

    if not checkpoint.get("char_image_in_drive"):
        upload_file(drive_service, CHARACTER_IMAGE_PATH, animal_folder_id, "character_reference.jpg")
        checkpoint["char_image_in_drive"] = True
        _save_checkpoint(checkpoint)

    for i, scene in enumerate(scenes, start=1):
        if i in completed_scenes:
            continue

        logger.info("═══ Scene %d / %d  [%s] ═══", i, total, animal)
        _process_scene_audio(scene, i, drive_service, animal_folder_id)
        
        success = _process_scene_video(scene, i, frame0_url, char_design, animal, drive_service, animal_folder_id)

        if not success:
            return False

        completed_scenes.append(i)
        checkpoint["completed_scenes"] = completed_scenes
        _save_checkpoint(checkpoint)

    _clear_checkpoint()
    return True

if __name__ == "__main__":
    run_media_pipeline()