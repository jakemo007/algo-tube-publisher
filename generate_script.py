# generate_script.py
# ─────────────────────────────────────────────────────────────────────────────
# 2D ANIME UPGRADE (60-SECOND OPTIMIZED):
# Forces high-end 2D cel-shaded aesthetic and strictly controls word counts
# to ensure the final audio track is exactly 60 seconds long.
# ─────────────────────────────────────────────────────────────────────────────

import json
import logging
import os

from openai import OpenAI
from dotenv import load_dotenv

from config import (
    LOG_FILE,
    LOG_LEVEL,
    OPENAI_SCRIPT_MODEL,
    SCRIPT_FILE,
    SCRIPT_SCENE_COUNT,
)
from fetch_data import fetch_todays_topic

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
_api_key = os.getenv("OPENAI_API_KEY")
if not _api_key:
    raise EnvironmentError("OPENAI_API_KEY missing from .env")

client = OpenAI(api_key=_api_key)

_REQUIRED_KEYS: set[str] = {
    "title", "description", "character_design",
    "character_setting", "scenes", "animal_name",
}


def _normalise_scenes(data: dict) -> dict:
    """Map GPT variant field names to canonical names."""
    scenes = data.get("scenes")
    if not isinstance(scenes, list):
        return data
    for scene in scenes:
        has_action = bool(scene.get("scene_action", "").strip())
        has_env    = bool(scene.get("scene_environment", "").strip())
        if not has_action or not has_env:
            visual = (
                scene.get("visual_prompt") or
                scene.get("visual_prompts") or
                scene.get("prompt") or ""
            )
            if isinstance(visual, list):
                visual = " ".join(visual)
            action_raw = scene.get("action") or scene.get("scene_action") or ""
            env_raw    = (
                scene.get("environment") or scene.get("setting") or
                scene.get("scene_environment") or scene.get("description") or ""
            )
            if visual and (not action_raw or not env_raw):
                if "Setting:" in visual:
                    parts = visual.split("Setting:", 1)
                    action_raw = action_raw or parts[0].strip().rstrip(".")
                    env_raw    = env_raw    or parts[1].strip()
                elif ". " in visual:
                    parts = visual.split(". ", 1)
                    action_raw = action_raw or parts[0].strip()
                    env_raw    = env_raw    or parts[1].strip()
                else:
                    action_raw = action_raw or visual
                    env_raw    = env_raw    or visual
            if not has_action and action_raw:
                scene["scene_action"] = action_raw.strip()
            if not has_env and env_raw:
                scene["scene_environment"] = env_raw.strip()
    return data


def _validate_script(data: dict) -> list[str]:
    errors: list[str] = []
    for key in _REQUIRED_KEYS:
        if key not in data:
            errors.append(f"Missing top-level key: '{key}'")
    scenes = data.get("scenes")
    if not isinstance(scenes, list) or len(scenes) == 0:
        errors.append("'scenes' must be a non-empty list.")
        return errors
    if len(scenes) != SCRIPT_SCENE_COUNT:
        errors.append(f"Expected {SCRIPT_SCENE_COUNT} scenes, got {len(scenes)}.")
    for i, scene in enumerate(scenes, start=1):
        for field in ("narration", "scene_action", "scene_environment"):
            if not scene.get(field):
                errors.append(f"Scene {i} missing '{field}'.")
    return errors


def generate_video_script(animal_name: str, max_retries: int = 3) -> dict | None:
    logger.info("Generating 2D ANIME script for: %s (60-sec optimized)", animal_name)

    system_prompt = f"""You are the head writer for ZooTots — the viral toddler animal channel.
We are creating a high-end, cinematic 2D animated Short (Demon Slayer/Pokémon style) about a {animal_name}.
CRITICAL REQUIREMENT: The final video must be EXACTLY 60 seconds long.

Return ONLY valid JSON — no markdown, no backticks.

JSON structure:
{{
    "animal_name": "{animal_name}",
    "title": "Viral emoji title under 60 chars #shorts",
    "description": "SEO description with hashtags",
    "character_design": "A single sentence physical description. MUST use specific 2D anime language: thick outlines, clean cel-shading, vibrant flat colors. Mention one cute accessory (tiny hat or scarf). Example: 'A chubby 2D anime style axolotl with flat bubblegum-pink skin, feathery crimson gills, huge round teal eyes, clean thick outlines, cel-shaded animation style, wearing a tiny yellow explorer backpack.'",
    "character_setting": "Vibrant Anime style background for the reference portrait. Example: 'standing in a vibrant colorful Studio Ghibli style lagoon with coral under golden anime sunbeams.'",
    "scenes": [
        {{
            "scene_number": 1,
            "narration": "HOOK narration here. Must be highly enthusiastic.",
            "scene_action": "Action (Anime terminology). Example: 'Waving enthusiastically, eyes wiggling happily, Anime speed lines in the background.'",
            "scene_environment": "Anime background for this scene. Must be different location and color than the reference. Example: 'A dense bamboo forest in deep purple and orange tones, cinematic Ghibli lighting close-up shot.'"
        }}
    ]
}}

SCENE PLAN — write exactly these 6 scenes:
Scene 1 = SCROLL-STOPPING HOOK. One shocking fact. Start with WHOA or Wait or WOW. 
Scene 2 = The weirdest or funniest fact.
Scene 3 = Cool behavior fact — what does it DO that is amazing?
Scene 4 = Super-power or record ability.
Scene 5 = Cute or relatable fact kids emotionally connect with.
Scene 6 = CALL TO ACTION (CTA) — The narration MUST be exactly: "Subscribe to ZooTots for a new animal every day! Don't miss out on the fun!"

NARRATION RULES (STRICT WORD COUNT ENFORCEMENT):
- To hit exactly 60 seconds of audio, the TOTAL script must be approximately 140 words.
- Scene 1 (The Hook) MUST be exactly 15-20 words long. 
- Scenes 2, 3, 4, and 5 MUST be detailed and exactly 25-30 words long each. Do not write short sentences. Explain the fact with extreme enthusiasm and detail.
- Scene 6 MUST be exactly: "Subscribe to ZooTots for a new animal every day! Don't miss out on the fun!"
- Sound like an excited kids TV presenter. Use words like: incredible, magical, super-powered, gigantic!

ENVIRONMENT RULES (Anime Focus):
- Every scene in a completely DIFFERENT location with DIFFERENT vibrant color palette.
- environments must use specific 2D anime descriptors: cel-shaded lighting, flat colors, heavy outlines, speed lines, Ghibli clouds, action backgrounds.
- vary between scenes: electric blue + gold, hot pink + neon green, deep purple + orange, teal + coral, crimson + yellow, icy white + cyan.

CHARACTER ACTION RULES: Actions must be high-energy and expressive anime style: spinning, backflips, happy wiggles.
Keep it to exactly {SCRIPT_SCENE_COUNT} scenes."""

    # ── THE RETRY LOOP ──
    for attempt in range(1, max_retries + 1):
        logger.info("Requesting script from OpenAI (Attempt %d/%d)…", attempt, max_retries)
        try:
            response = client.chat.completions.create(
                model=OPENAI_SCRIPT_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": f"Write a high-end 2D anime script about a {animal_name} that is exactly 140 words long to fill 60 seconds."},
                ],
                response_format={"type": "json_object"},
                temperature=0.7, 
            )
        except Exception:
            logger.exception("OpenAI API call failed on attempt %d.", attempt)
            continue

        raw = response.choices[0].message.content

        try:
            script_data: dict = json.loads(raw)
        except json.JSONDecodeError:
            logger.error("OpenAI returned non-JSON on attempt %d:\n%s", attempt, raw)
            continue

        if not script_data.get("animal_name"):
            script_data["animal_name"] = animal_name.strip().title()

        script_data = _normalise_scenes(script_data)

        errors = _validate_script(script_data)
        if errors:
            # If there are errors, log them and loop back to try again!
            logger.warning(
                "Script validation failed on attempt %d (%d errors):\n  %s",
                attempt, len(errors), "\n  ".join(errors),
            )
            continue

        # If we make it here, the script is perfect!
        try:
            with open(SCRIPT_FILE, "w", encoding="utf-8") as f:
                json.dump(script_data, f, indent=4, ensure_ascii=False)
            logger.info("Script saved → '%s'  title: %s", SCRIPT_FILE, script_data.get("title"))
            return script_data
        except OSError:
            logger.exception("Failed to write script.")
            return None

    logger.error("Step 1 failed — script generation failed after %d attempts. Aborting.", max_retries)
    return None

if __name__ == "__main__":
    todays_animal = fetch_todays_topic()
    if todays_animal:
        generate_video_script(todays_animal)
    else:
        logger.error("fetch_todays_topic() returned nothing.")