# rag_database.py
# ─────────────────────────────────────────────────────────────────────────────
# ChromaDB vector store for caching generated videos.
#
# ChromaDB metadata schema (per entry):
#   {
#     "drive_file_id": "1BxiMVFEL...",   ← Google Drive file ID
#     "animal":        "Lion",            ← character tag for filtering
#     "file_name":     "scene_1.mp4"      ← human-readable name for logging
#   }
#
# On a cache hit, the caller receives the Drive file ID and is responsible
# for downloading the file locally before using it in assembly.
# ─────────────────────────────────────────────────────────────────────────────

import logging
import os

import chromadb
from chromadb.utils import embedding_functions
from dotenv import load_dotenv

from config import (
    CHROMA_COLLECTION_NAME,
    CHROMA_STORAGE_PATH,
    EMBEDDING_MODEL,
    LOG_FILE,
    LOG_LEVEL,
    RAG_SIMILARITY_THRESHOLD,
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

# ── API key validation ────────────────────────────────────────────────────────
load_dotenv()

OPENAI_API_KEY: str | None = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise EnvironmentError(
        "OPENAI_API_KEY is missing from your .env file. "
        "This key is required for ChromaDB text embeddings."
    )


# ── ChromaDB collection factory ───────────────────────────────────────────────

def _build_collection(
    storage_path: str = CHROMA_STORAGE_PATH,
    collection_name: str = CHROMA_COLLECTION_NAME,
) -> chromadb.Collection:
    client = chromadb.PersistentClient(path=storage_path)
    openai_ef = embedding_functions.OpenAIEmbeddingFunction(
        api_key=OPENAI_API_KEY,
        model_name=EMBEDDING_MODEL,
    )
    return client.get_or_create_collection(
        name=collection_name,
        embedding_function=openai_ef,
    )


video_collection: chromadb.Collection = _build_collection()


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def search_video_cache(
    scene_description: str,
    animal: str = "",
    threshold: float = RAG_SIMILARITY_THRESHOLD,
) -> dict | None:
    """
    Query the RAG database for a semantically similar cached video.

    Two-layer guard against false cache hits:
        1. animal filter  — only match videos from the same animal.
                            A lion scene must never reuse an axolotl scene.
        2. distance check — cosine distance must be below threshold (default 0.15).
                            Only near-identical prompts reuse cached video.
                            Previously 1.2 (way too loose) — every new scene
                            would "hit" the cache and Luma was never called.

    Args:
        scene_description: cache_key = "scene_action | scene_environment"
        animal:            Animal name — filters results to same character only.
        threshold:         Max cosine distance for a valid match (0=identical).

    Returns:
        Metadata dict on a genuine hit, ``None`` on miss or error.
    """
    logger.info(
        "Searching RAG cache for animal='%s', prompt='%s'",
        animal or "any", scene_description[:60],
    )

    if video_collection.count() == 0:
        logger.debug("Collection is empty — cache miss.")
        return None

    try:
        # Only search within the same animal — prevents cross-animal false hits
        where_filter = {"animal": {"$eq": animal}} if animal else None
        query_kwargs = {
            "query_texts": [scene_description],
            "n_results": 1,
        }
        if where_filter:
            query_kwargs["where"] = where_filter

        results = video_collection.query(**query_kwargs)
    except Exception:
        logger.exception("ChromaDB query failed — treating as cache miss.")
        return None

    distances = results.get("distances", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]

    if not distances or not metadatas:
        logger.info("No results returned — cache miss.")
        return None

    best_dist = distances[0]
    if best_dist < threshold:
        meta = metadatas[0]
        logger.info(
            "RAG cache HIT  (distance=%.4f ≤ %.4f) → %s / %s",
            best_dist, threshold,
            meta.get("animal", "?"), meta.get("file_name", "?"),
        )
        return meta

    logger.info(
        "RAG cache MISS (distance=%.4f > %.4f) — sending to Luma API.",
        best_dist, threshold,
    )
    return None


def ingest_new_video(
    scene_description: str,
    drive_file_id: str,
    animal: str,
    file_name: str,
) -> bool:
    """
    Persist a newly generated video's Drive reference into ChromaDB.

    Uses ``upsert`` so re-running the pipeline never raises a duplicate-ID error.

    Args:
        scene_description: The visual prompt / action that produced this video.
        drive_file_id:     Google Drive file ID of the stored .mp4.
        animal:            Short character label (e.g. 'Lion').
        file_name:         Human-readable filename (e.g. 'scene_1.mp4').

    Returns:
        ``True`` on success, ``False`` on failure.
    """
    # Use Drive file ID as the ChromaDB document ID — globally unique
    doc_id = drive_file_id

    try:
        video_collection.upsert(
            documents=[scene_description],
            metadatas=[{
                "drive_file_id": drive_file_id,
                "animal":        animal,
                "file_name":     file_name,
            }],
            ids=[doc_id],
        )
        logger.info(
            "Ingested into RAG vault: %s / %s (id=%s)",
            animal, file_name, drive_file_id,
        )
        return True
    except Exception:
        logger.exception(
            "Failed to ingest '%s' into ChromaDB.", file_name
        )
        return False


# ── Smoke test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logger.info(
        "Vector database initialised. Vault size: %d video(s).",
        video_collection.count(),
    )