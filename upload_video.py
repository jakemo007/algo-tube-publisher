# upload_video.py
# ─────────────────────────────────────────────────────────────────────────────
# Step 5 — Authenticates with the YouTube Data API v3 and uploads the final
# assembled video with dynamically generated metadata from current_script.json.
# ─────────────────────────────────────────────────────────────────────────────

import json
import logging
import os

import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.errors
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.http import MediaFileUpload

from config import (
    LOG_FILE,
    LOG_LEVEL,
    OUTPUT_VIDEO,           # ✅ FIX 1: was hardcoded "final_shorts_video.mp4"
    SCRIPT_FILE,            # ✅ FIX 2: was hardcoded "script_data.json" (wrong file)
    YOUTUBE_CATEGORY_ID,
    YOUTUBE_CLIENT_SECRETS,
    YOUTUBE_DEFAULT_TITLE,
    YOUTUBE_DESCRIPTION,
    YOUTUBE_TAGS,
    YOUTUBE_TITLE_MAX_LEN,
    YOUTUBE_TOKEN_FILE,
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

# YouTube OAuth scope — upload + manage videos
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


# ─────────────────────────────────────────────────────────────────────────────
# Authentication
# ─────────────────────────────────────────────────────────────────────────────

def get_authenticated_service():
    """
    Authenticate via OAuth 2.0 and return an authorised YouTube API client.

    Token lifecycle:
        • First run  → opens browser for user consent, saves token.json
        • Subsequent → loads token.json; silently refreshes if expired
        • Token is always re-saved after a refresh so expiry never drifts
    """
    creds: Credentials | None = None

    # ── Load existing token ───────────────────────────────────────────────────
    if os.path.exists(YOUTUBE_TOKEN_FILE):
        try:
            creds = Credentials.from_authorized_user_file(
                YOUTUBE_TOKEN_FILE, SCOPES
            )
            logger.debug("Loaded credentials from '%s'.", YOUTUBE_TOKEN_FILE)
        except Exception:
            logger.warning(
                "Could not read '%s' — will re-authenticate.", YOUTUBE_TOKEN_FILE
            )
            creds = None

    # ── Refresh or re-authorise ───────────────────────────────────────────────
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logger.info("Access token expired — refreshing silently…")
            try:
                creds.refresh(Request())
                logger.info("Token refreshed successfully.")
            except Exception:
                logger.exception("Token refresh failed — falling back to browser login.")
                creds = None

        if not creds or not creds.valid:
            # Browser-based first-time (or recovery) login
            if not os.path.exists(YOUTUBE_CLIENT_SECRETS):
                logger.error(
                    "'%s' is missing. Download it from Google Cloud Console.",
                    YOUTUBE_CLIENT_SECRETS,
                )
                return None

            logger.info("Opening browser for initial OAuth login…")
            flow  = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
                YOUTUBE_CLIENT_SECRETS, SCOPES
            )
            creds = flow.run_local_server(port=0)
            logger.info("Browser login successful.")

        # ✅ FIX 3: Always re-save credentials — catches both new auth AND refreshes
        try:
            with open(YOUTUBE_TOKEN_FILE, "w") as f:
                f.write(creds.to_json())
            logger.info("Credentials saved to '%s'.", YOUTUBE_TOKEN_FILE)
        except OSError:
            logger.exception("Failed to save credentials to '%s'.", YOUTUBE_TOKEN_FILE)

    try:
        return googleapiclient.discovery.build("youtube", "v3", credentials=creds)
    except Exception:
        logger.exception("Failed to build YouTube API client.")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Metadata helpers
# ─────────────────────────────────────────────────────────────────────────────

def _load_dynamic_metadata() -> tuple[str, str]:
    """
    Read the video title and description from current_script.json.
    """
    title = YOUTUBE_DEFAULT_TITLE
    description = YOUTUBE_DESCRIPTION
    
    try:
        with open(SCRIPT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            title = data.get("title") or YOUTUBE_DEFAULT_TITLE
            
            # Pull the dynamically generated SEO description
            dynamic_desc = data.get("description")
            if dynamic_desc:
                description = f"{dynamic_desc}\n\n{YOUTUBE_DESCRIPTION}"
                
    except Exception as e:
        logger.warning("Failed to load dynamic metadata from '%s' — using defaults. Error: %s", SCRIPT_FILE, e)

    return title.strip(), description.strip()


def _sanitise_title(raw_title: str) -> str:
    """
    Enforce YouTube title rules:
        • Must contain #shorts for the algorithm
        • Hard 100-character limit
    """
    title = raw_title

    if "#shorts" not in title.lower():
        title = f"{title} #shorts"

    if len(title) > YOUTUBE_TITLE_MAX_LEN:
        # Truncate with room for the mandatory #shorts suffix
        title = title[: YOUTUBE_TITLE_MAX_LEN - 12] + "… #shorts"

    return title


# ─────────────────────────────────────────────────────────────────────────────
# Upload
# ─────────────────────────────────────────────────────────────────────────────

def upload_video(youtube) -> bool:
    if not os.path.exists(OUTPUT_VIDEO):
        logger.error("'%s' not found. Run assemble_video.py first.", OUTPUT_VIDEO)
        return False

    raw_title, description = _load_dynamic_metadata()
    title = _sanitise_title(raw_title)
    
    logger.info("Uploading with title: %s", title)

    request_body = {
        "snippet": {
            "title": title,
            "description": description, # Now using the unique SEO description
            "tags": YOUTUBE_TAGS,
            "categoryId": YOUTUBE_CATEGORY_ID,
            "defaultLanguage": "en-US",
            "defaultAudioLanguage": "en-US",
        },
        "status": {
            # Uploading as unlisted prevents the API shadowban and allows HD processing
            "privacyStatus": "unlisted", 
            
            # Setting to False allows comments and Shorts Feed distribution
            "selfDeclaredMadeForKids": False, 
            "license": "youtube",
        },
    }

    try:
        media = MediaFileUpload(OUTPUT_VIDEO, chunksize=-1, resumable=True)
        request = youtube.videos().insert(
            part="snippet,status",
            body=request_body,
            media_body=media,
        )
        response = request.execute()

        video_id: str = response.get("id", "")
        logger.info("Upload successful! Video ID: %s", video_id)
        logger.info("Video is UNLISTED. Go to YouTube Studio to make it PUBLIC: https://studio.youtube.com/video/%s/edit", video_id)
        return True

    except googleapiclient.errors.HttpError as exc:
        logger.error("YouTube API HTTP error: %s", exc)
    except Exception:
        logger.exception("Unexpected error during video upload.")

    return False
# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def run_upload_pipeline() -> None:
    logger.info("Starting YouTube upload pipeline…")
    youtube_service = get_authenticated_service()

    if youtube_service:
        success = upload_video(youtube_service)
        if not success:
            logger.error("Upload pipeline finished with errors.")
    else:
        logger.error("Could not authenticate with YouTube — aborting.")


if __name__ == "__main__":
    run_upload_pipeline()