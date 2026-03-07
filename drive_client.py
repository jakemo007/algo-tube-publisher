# drive_client.py
# ─────────────────────────────────────────────────────────────────────────────
# Reusable Google Drive client used by every module that needs to store or
# retrieve files from cloud storage.
#
# Folder structure in Drive:
#   asset_holder/
#     <AnimalName>/
#       character_reference.jpg
#       scene_1.mp4  …  scene_N.mp4
#       voice_1.mp3  …  voice_N.mp3
#       final_video.mp4
#       current_script.json
#
# ChromaDB stores the Drive file ID (not a local path) for every cached video.
# On a RAG cache hit, the video is downloaded from Drive to a temp local path
# for assembly, then the temp file is deleted.
# ─────────────────────────────────────────────────────────────────────────────

import io
import logging
import os
import re

import googleapiclient.discovery
import googleapiclient.errors
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
import google_auth_oauthlib.flow

from config import (
    DRIVE_CLIENT_SECRETS,
    DRIVE_ROOT_FOLDER,
    DRIVE_TOKEN_FILE,
    LOG_FILE,
    LOG_LEVEL,
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

SCOPES = ["https://www.googleapis.com/auth/drive.file"]


# ─────────────────────────────────────────────────────────────────────────────
# Authentication
# ─────────────────────────────────────────────────────────────────────────────

def get_drive_service():
    """
    Authenticate with Google Drive OAuth 2.0 and return an authorised client.

    Token lifecycle:
        • First run   → browser consent → saves drive_token.json
        • Subsequent  → loads token; silently refreshes if expired
        • Token always re-saved after refresh so expiry never drifts
    """
    creds: Credentials | None = None

    if os.path.exists(DRIVE_TOKEN_FILE):
        try:
            creds = Credentials.from_authorized_user_file(DRIVE_TOKEN_FILE, SCOPES)
        except Exception:
            logger.warning("Could not read '%s' — will re-authenticate.", DRIVE_TOKEN_FILE)
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logger.info("Drive token expired — refreshing silently…")
            try:
                creds.refresh(Request())
            except Exception:
                logger.exception("Token refresh failed — falling back to browser login.")
                creds = None

        if not creds or not creds.valid:
            if not os.path.exists(DRIVE_CLIENT_SECRETS):
                logger.error(
                    "'%s' is missing. Download it from Google Cloud Console.",
                    DRIVE_CLIENT_SECRETS,
                )
                return None
            logger.info("Opening browser for Drive OAuth login…")
            flow  = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
                DRIVE_CLIENT_SECRETS, SCOPES
            )
            creds = flow.run_local_server(port=0)

        # Always re-save — covers both new auth and refreshed tokens
        try:
            with open(DRIVE_TOKEN_FILE, "w") as f:
                f.write(creds.to_json())
            logger.info("Drive credentials saved to '%s'.", DRIVE_TOKEN_FILE)
        except OSError:
            logger.exception("Could not save Drive token.")

    try:
        return googleapiclient.discovery.build("drive", "v3", credentials=creds)
    except Exception:
        logger.exception("Failed to build Drive API client.")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Folder management
# ─────────────────────────────────────────────────────────────────────────────

def sanitise_name(name: str) -> str:
    """Remove characters illegal in Drive folder/file names."""
    return re.sub(r'[\\/*?:"<>|#]', "", name).strip()


def get_or_create_folder(
    drive_service,
    folder_name: str,
    parent_id: str | None = None,
) -> str | None:
    """
    Find an existing Drive folder by name (and optionally parent), or create it.

    Returns the folder's Drive file ID, or ``None`` on error.
    """
    try:
        query = (
            f"mimeType='application/vnd.google-apps.folder' "
            f"and name='{folder_name}' and trashed=false"
        )
        if parent_id:
            query += f" and '{parent_id}' in parents"

        results = (
            drive_service.files()
            .list(q=query, spaces="drive", fields="files(id, name)")
            .execute()
        )
        items = results.get("files", [])

        if items:
            logger.debug("Found existing Drive folder '%s' (id=%s).", folder_name, items[0]["id"])
            return items[0]["id"]

        # Folder doesn't exist — create it
        meta = {
            "name": folder_name,
            "mimeType": "application/vnd.google-apps.folder",
        }
        if parent_id:
            meta["parents"] = [parent_id]

        folder = drive_service.files().create(body=meta, fields="id").execute()
        folder_id = folder["id"]
        logger.info("Created Drive folder '%s' (id=%s).", folder_name, folder_id)
        return folder_id

    except googleapiclient.errors.HttpError:
        logger.exception("Drive API error while managing folder '%s'.", folder_name)
        return None


def get_animal_folder_id(drive_service, animal_name: str) -> str | None:
    """
    Ensure the path  asset_holder/<animal_name>/  exists in Drive
    and return the animal sub-folder's ID.

    Creates any missing folders automatically.
    """
    clean_animal = sanitise_name(animal_name.title())

    root_id = get_or_create_folder(drive_service, DRIVE_ROOT_FOLDER)
    if not root_id:
        return None

    animal_id = get_or_create_folder(drive_service, clean_animal, root_id)
    return animal_id   # may be None if creation failed


# ─────────────────────────────────────────────────────────────────────────────
# File upload
# ─────────────────────────────────────────────────────────────────────────────

_MIME_MAP: dict[str, str] = {
    ".mp4":  "video/mp4",
    ".mp3":  "audio/mpeg",
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".json": "application/json",
    ".png":  "image/png",
}

def upload_file(
    drive_service,
    local_path: str,
    parent_folder_id: str,
    drive_filename: str | None = None,
) -> str | None:
    """
    Upload a local file to a specific Drive folder.

    Args:
        local_path:       Path to the file on disk.
        parent_folder_id: Drive ID of the destination folder.
        drive_filename:   Name to use in Drive (defaults to the local filename).

    Returns:
        The Drive file ID of the uploaded file, or ``None`` on failure.
    """
    if not os.path.exists(local_path):
        logger.error("Cannot upload — file not found: %s", local_path)
        return None

    ext      = os.path.splitext(local_path)[1].lower()
    mimetype = _MIME_MAP.get(ext, "application/octet-stream")
    name     = drive_filename or os.path.basename(local_path)

    meta  = {"name": name, "parents": [parent_folder_id]}
    media = MediaFileUpload(local_path, mimetype=mimetype, resumable=True)

    try:
        result = (
            drive_service.files()
            .create(body=meta, media_body=media, fields="id")
            .execute()
        )
        file_id: str = result["id"]
        logger.info("Uploaded '%s' to Drive (id=%s).", name, file_id)
        return file_id
    except Exception:
        logger.exception("Failed to upload '%s' to Drive.", local_path)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# File download
# ─────────────────────────────────────────────────────────────────────────────

def download_file(drive_service, file_id: str, dest_path: str) -> bool:
    """
    Download a Drive file to a local path.

    Used when the RAG cache returns a Drive file ID and we need the video
    locally for MoviePy assembly.

    Args:
        file_id:   Drive file ID.
        dest_path: Local path to write the downloaded file to.

    Returns:
        ``True`` on success, ``False`` on failure.
    """
    logger.info("Downloading Drive file %s → %s", file_id, dest_path)
    try:
        request  = drive_service.files().get_media(fileId=file_id)
        buf      = io.BytesIO()
        downloader = MediaIoBaseDownload(buf, request)

        done = False
        while not done:
            _, done = downloader.next_chunk()

        os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)
        with open(dest_path, "wb") as f:
            f.write(buf.getvalue())

        logger.info("Download complete: %s", dest_path)
        return True
    except Exception:
        logger.exception("Failed to download Drive file %s.", file_id)
        return False


# ─────────────────────────────────────────────────────────────────────────────
# File deletion
# ─────────────────────────────────────────────────────────────────────────────

def delete_local_assets(assets_dir: str, output_video: str) -> None:
    """
    Delete the local assets folder and the assembled output video after they
    have been successfully uploaded to YouTube and backed up to Drive.

    This is called by main.py as the final cleanup step.

    Args:
        assets_dir:   Path to the assets/ folder.
        output_video: Path to the final assembled .mp4 file.
    """
    import shutil

    if os.path.exists(assets_dir):
        try:
            shutil.rmtree(assets_dir)
            logger.info("Local assets folder deleted: %s", assets_dir)
        except OSError:
            logger.exception("Could not delete assets folder '%s'.", assets_dir)

    if os.path.exists(output_video):
        try:
            os.remove(output_video)
            logger.info("Local output video deleted: %s", output_video)
        except OSError:
            logger.exception("Could not delete output video '%s'.", output_video)