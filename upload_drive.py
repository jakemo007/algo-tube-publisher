# upload_drive.py
# ─────────────────────────────────────────────────────────────────────────────
# Step 5 — Final Drive backup.
#
# By this point every scene video and audio is already in Drive (uploaded
# incrementally by generate_media.py). This module just adds the two
# remaining files that are only ready after assembly:
#   • final_video.mp4       → asset_holder/<animal>/final_video.mp4
#   • current_script.json   → asset_holder/<animal>/current_script.json
#
# All Drive auth and folder logic lives in drive_client.py.
# ─────────────────────────────────────────────────────────────────────────────

import json
import logging

from config import (
    LOG_FILE,
    LOG_LEVEL,
    OUTPUT_VIDEO,
    SCRIPT_FILE,
)
from drive_client import (
    get_animal_folder_id,
    get_drive_service,
    upload_file,
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


def _get_animal_name() -> str:
    """Read the animal name from the script file for folder routing."""
    try:
        with open(SCRIPT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        title: str = data.get("title") or ""
        parts = title.split()
        return parts[0] if parts else "Unknown"
    except Exception:
        logger.warning("Could not read animal name from script — using 'Unknown'.")
        return "Unknown"


def backup_final_assets() -> bool:
    """
    Upload final_video.mp4 and current_script.json to the animal's Drive folder.

    Returns:
        ``True`` if both files were uploaded successfully, ``False`` otherwise.
    """
    logger.info("Starting final Drive backup…")

    drive_service = get_drive_service()
    if not drive_service:
        logger.error("Drive authentication failed — skipping backup.")
        return False

    animal = _get_animal_name()
    folder_id = get_animal_folder_id(drive_service, animal)
    if not folder_id:
        logger.error("Could not find/create Drive folder for '%s'.", animal)
        return False

    success = True

    for local_path in (OUTPUT_VIDEO, SCRIPT_FILE):
        file_id = upload_file(drive_service, local_path, folder_id)
        if file_id:
            logger.info("Backed up '%s' to Drive (id=%s).", local_path, file_id)
        else:
            logger.error("Failed to back up '%s' to Drive.", local_path)
            success = False

    if success:
        logger.info(
            "Final backup complete. All assets in Drive under "
            "'asset_holder/%s/'.", animal
        )
    return success


if __name__ == "__main__":
    backup_final_assets()