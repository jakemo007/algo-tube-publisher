# main.py — ZooTots master orchestrator
# Steps 3-6 only run if Step 2 fully succeeds.

import logging
import sys

from config import ASSETS_DIR, LOG_FILE, LOG_LEVEL, OUTPUT_VIDEO

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.DEBUG),
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


def main() -> None:
    logger.info("━" * 60)
    logger.info("ZooTots Daily Pipeline — Starting")
    logger.info("━" * 60)

    # ── Step 0: Animal topic ──────────────────────────────────────────────────
    logger.info("STEP 0 — Fetching today's animal…")
    from fetch_data import fetch_todays_topic
    animal = fetch_todays_topic()
    if not animal:
        logger.error("Step 0 failed — no animal. Aborting.")
        sys.exit(1)
    logger.info("Step 0 ✓  Animal: %s", animal.upper())

    # ── Step 1: Script ────────────────────────────────────────────────────────
    logger.info("STEP 1 — Generating script…")
    from generate_script import generate_video_script
    script = generate_video_script(animal)
    if not script:
        logger.error("Step 1 failed — script generation failed. Aborting.")
        sys.exit(1)
    logger.info("Step 1 ✓  Title: %s", script.get("title", "N/A"))

    # ── Step 2: Media (FLUX + ElevenLabs + Luma + Drive) ─────────────────────
    logger.info("STEP 2 — Generating media assets…")
    from generate_media import run_media_pipeline
    media_ok = run_media_pipeline()
    if not media_ok:
        logger.error(
            "Step 2 FAILED — Luma/audio/Drive error. "
            "Fix the issue then re-run. Checkpoint saved — will resume from last scene."
        )
        sys.exit(1)
    logger.info("Step 2 ✓  All scenes generated.")

    # ── Step 3: Assemble ──────────────────────────────────────────────────────
    logger.info("STEP 3 — Assembling final video…")
    from assemble_video import build_final_video
    assemble_ok = build_final_video()
    if not assemble_ok:
        logger.error("Step 3 FAILED — assembly error. Aborting.")
        sys.exit(1)
    logger.info("Step 3 ✓  Video assembled.")

    # ── Step 4: YouTube upload ────────────────────────────────────────────────
    logger.info("STEP 4 — Uploading to YouTube…")
    from upload_video import run_upload_pipeline
    run_upload_pipeline()
    logger.info("Step 4 ✓")

    # ── Step 5: Drive backup ──────────────────────────────────────────────────
    logger.info("STEP 5 — Backing up to Drive…")
    from upload_drive import backup_final_assets
    if backup_final_assets():
        logger.info("Step 5 ✓  All assets in Drive.")
    else:
        logger.warning("Step 5 — some Drive uploads failed. Continuing to cleanup.")

    # ── Step 6: Local cleanup ─────────────────────────────────────────────────
    logger.info("STEP 6 — Cleaning up local files…")
    from drive_client import delete_local_assets
    delete_local_assets(ASSETS_DIR, OUTPUT_VIDEO)
    logger.info("Step 6 ✓  Local disk cleared.")

    logger.info("━" * 60)
    logger.info("ZooTots Daily Pipeline — Finished! 🎉")
    logger.info("Drive: asset_holder/%s/", animal.title())
    logger.info("━" * 60)


if __name__ == "__main__":
    main()