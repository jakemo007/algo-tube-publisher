# fetch_data.py
# ─────────────────────────────────────────────────────────────────────────────
# Step 0 — Picks today's animal topic using OpenAI, while ensuring we never
# repeat an animal that has already been covered.
#
# History is stored in used_animals.txt (one lowercase animal per line).
# The file is only written AFTER the chosen animal passes all validation,
# preventing duplicates and empty entries from ever entering the history.
# ─────────────────────────────────────────────────────────────────────────────

import logging
import os
import re

from dotenv import load_dotenv
from openai import OpenAI

from config import (
    FALLBACK_ANIMAL,
    HISTORY_FILE,
    LOG_FILE,
    LOG_LEVEL,
    OPENAI_MODEL,
    TOPIC_MAX_TOKENS,
    TOPIC_TEMPERATURE,
)

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.DEBUG),
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

# ── OpenAI client ─────────────────────────────────────────────────────────────
load_dotenv()
_api_key = os.getenv("OPENAI_API_KEY")
if not _api_key:
    raise EnvironmentError("OPENAI_API_KEY is missing from your .env file.")

client = OpenAI(api_key=_api_key)


# ─────────────────────────────────────────────────────────────────────────────
# History helpers
# ─────────────────────────────────────────────────────────────────────────────

def load_used_animals() -> list[str]:
    """
    Return a lowercase list of every animal already covered.
    Returns an empty list if the history file does not yet exist.
    """
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return [line.strip().lower() for line in f if line.strip()]
    except OSError:
        logger.exception("Could not read history file '%s'.", HISTORY_FILE)
        return []


def save_animal_to_history(animal_name: str) -> None:
    """
    Append *animal_name* (lowercase) to the history file.

    Always saves in lowercase so the file stays consistent regardless of
    how OpenAI capitalised the response.
    """
    try:
        with open(HISTORY_FILE, "a", encoding="utf-8") as f:
            f.write(f"{animal_name.lower()}\n")
        logger.debug("Saved '%s' to history.", animal_name)
    except OSError:
        logger.exception("Could not write '%s' to history file.", animal_name)


def _clean_animal_name(raw: str) -> str:
    """
    Strip punctuation, extra whitespace, and sentence fragments from the
    raw OpenAI response so we get a clean animal name.

    E.g. "Sure! I'll pick a **Capybara**." → "Capybara"
    """
    # Remove markdown bold/italic markers
    cleaned = re.sub(r"[*_`]", "", raw)
    # Keep only letters, spaces, and hyphens (handles "axolotl", "sea-lion")
    cleaned = re.sub(r"[^a-zA-Z\s\-]", "", cleaned)
    # Collapse whitespace and title-case
    cleaned = " ".join(cleaned.split()).title()
    return cleaned


# ─────────────────────────────────────────────────────────────────────────────
# Main topic picker
# ─────────────────────────────────────────────────────────────────────────────

def fetch_todays_topic() -> str:
    """
    Ask OpenAI to suggest a fresh, kid-friendly animal that hasn't been
    covered yet, then validate and record it before returning.

    Validation steps (all applied before saving to history):
        1. Response is non-empty after cleaning
        2. Response looks like a single animal name (≤ 5 words)
        3. Animal is NOT already in used_animals.txt

    Falls back to FALLBACK_ANIMAL only when the API call itself fails.
    The fallback is also saved to history so it can never repeat.

    Returns:
        A validated, title-cased animal name string.
    """
    logger.info("Step 0: Fetching today's animal topic…")

    used_animals = load_used_animals()
    logger.info("History contains %d animal(s) already used.", len(used_animals))

    system_prompt = (
        "You are a producer for a highly viral toddler educational YouTube Shorts channel. "
        "Your job is to pick the subject for today's video. "
        "It must be a cute, fascinating, or bizarre animal that kids would love.\n"
        f"CRITICAL RULE: Do NOT pick any animal from this list: "
        f"{', '.join(used_animals) if used_animals else 'None yet'}.\n"
        "Return ONLY the animal's name. No punctuation, no extra words, nothing else."
    )

    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": "Pick today's animal."},
            ],
            max_tokens=TOPIC_MAX_TOKENS,
            temperature=TOPIC_TEMPERATURE,
        )

        raw = response.choices[0].message.content or ""
        animal = _clean_animal_name(raw)

        # ── Validation ────────────────────────────────────────────────────────

        # 1. Non-empty
        if not animal:
            logger.warning(
                "OpenAI returned an empty or unparseable response: '%s'. "
                "Using fallback.", raw
            )
            return _use_fallback(used_animals)

        # 2. Looks like a name, not a sentence (rough heuristic: ≤ 5 words)
        if len(animal.split()) > 5:
            logger.warning(
                "Response looks like a sentence, not a name: '%s'. "
                "Using fallback.", animal
            )
            return _use_fallback(used_animals)

        # ✅ FIX: 3. Check OpenAI actually respected the exclusion list
        if animal.lower() in used_animals:
            logger.warning(
                "OpenAI ignored the exclusion list and suggested '%s' again. "
                "Using fallback.", animal
            )
            return _use_fallback(used_animals)

        # ── All checks passed: save THEN return ───────────────────────────────
        # ✅ FIX: History is written only after validation — never on bad data
        save_animal_to_history(animal)
        logger.info("Today's topic: %s", animal.upper())
        return animal

    except Exception:
        logger.exception("OpenAI API call failed — using fallback animal.")
        return _use_fallback(used_animals)


def _use_fallback(used_animals: list[str]) -> str:
    """
    Return the fallback animal and record it in history so it is
    never silently reused on repeated API failures.

    If even the fallback is already used, log a warning and return it
    anyway (the pipeline should still run; duplication is better than crashing).
    """
    animal = FALLBACK_ANIMAL

    # ✅ FIX: Fallback is now always saved to history
    if animal.lower() not in used_animals:
        save_animal_to_history(animal)
    else:
        logger.warning(
            "Fallback animal '%s' is also already in history — "
            "consider updating FALLBACK_ANIMAL in config.py.", animal
        )

    logger.info("Using fallback topic: %s", animal.upper())
    return animal


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    topic = fetch_todays_topic()
    logger.info("fetch_data test complete. Topic returned: '%s'", topic)