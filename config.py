# config.py — ZooTots pipeline central config

# ── RAG / ChromaDB ────────────────────────────────────────────────────────────
CHROMA_STORAGE_PATH: str    = "./chroma_storage"
CHROMA_COLLECTION_NAME: str = "video_assets"
EMBEDDING_MODEL: str        = "text-embedding-3-small"
RAG_SIMILARITY_THRESHOLD: float = 0.15
RAG_BYPASS_CACHE: bool      = False

# ── ElevenLabs ────────────────────────────────────────────────────────────────
ELEVENLABS_VOICE_ID: str    = "21m00Tcm4TlvDq8ikWAM"   # Rachel
ELEVENLABS_MODEL_ID: str    = "eleven_multilingual_v2"
ELEVENLABS_OUTPUT_FORMAT: str = "mp3_44100_128"

# ── Hugging Face / FLUX ───────────────────────────────────────────────────────
HF_IMAGE_API_URL: str = (
    "https://router.huggingface.co/hf-inference/models/"
    "black-forest-labs/FLUX.1-schnell"
)
HF_IMAGE_STYLE_SUFFIX: str = (
    ", Pixar 3D render, bright saturated kids movie style, "
    "character fully visible, centered, sharp focus, vibrant lighting"
)
HF_MAX_RETRIES: int  = 3
HF_RETRY_SLEEP: int  = 10

# ── Luma AI ───────────────────────────────────────────────────────────────────
LUMA_MODEL: str             = "ray-flash-2"
LUMA_CLIPS_PER_SCENE: int   = 2      # 2 Luma calls × ~5s = ~10s per scene
LUMA_POLL_INTERVAL: int     = 8
LUMA_TIMEOUT_SECONDS: int   = 300
LUMA_MAX_POLL_ATTEMPTS: int = 120

# ── Character image ───────────────────────────────────────────────────────────
CHARACTER_IMAGE_PATH: str = "assets/character_reference.jpg"
IMGBB_UPLOAD_URL: str     = "https://api.imgbb.com/1/upload"

# ── OpenAI ────────────────────────────────────────────────────────────────────
OPENAI_MODEL: str        = "gpt-4o-mini"
OPENAI_SCRIPT_MODEL: str = OPENAI_MODEL
HISTORY_FILE: str        = "used_animals.txt"
FALLBACK_ANIMAL: str     = "Penguin"
TOPIC_MAX_TOKENS: int    = 10
TOPIC_TEMPERATURE: float = 0.8
SCRIPT_SCENE_COUNT: int  = 6   # 6 scenes × ~10s = ~60s

# ── File paths ────────────────────────────────────────────────────────────────
ASSETS_DIR: str      = "assets"
SCRIPT_FILE: str     = "current_script.json"
OUTPUT_VIDEO: str    = "final_video.mp4"
CHECKPOINT_FILE: str = "pipeline_checkpoint.json"

# ── Music ─────────────────────────────────────────────────────────────────────
# Drop any royalty-free .mp3 into the project root named "music.mp3"
# The pipeline will loop it and mix it under narration at MUSIC_VOLUME.
MUSIC_FILE: str      = "music.mp3"
MUSIC_VOLUME: float  = 0.15      # 0.0 = silent, 1.0 = full volume

# ── Caption rendering (PIL-based, no ImageMagick needed) ──────────────────────
CAPTION_FONT_SIZE: int      = 52
CAPTION_MAX_CHARS: int      = 28    # chars per line before wrapping
CAPTION_Y_POS: float        = 0.76  # fraction from top (bottom quarter)
CAPTION_COLOR: tuple        = (255, 255, 255)
CAPTION_STROKE_COLOR: tuple = (0, 0, 0)
CAPTION_STROKE_WIDTH: int   = 3

# ── Google Drive ──────────────────────────────────────────────────────────────
DRIVE_CLIENT_SECRETS: str = "drive_client_secret.json"
DRIVE_TOKEN_FILE: str     = "drive_token.json"
DRIVE_ROOT_FOLDER: str    = "asset_holder"

# ── YouTube ───────────────────────────────────────────────────────────────────
YOUTUBE_CLIENT_SECRETS: str = "client_secret.json"
YOUTUBE_TOKEN_FILE: str     = "token.json"
YOUTUBE_CATEGORY_ID: str    = "27"
YOUTUBE_DEFAULT_TITLE: str  = "ZooTots Animal Adventure! 🐾 #shorts"
YOUTUBE_DESCRIPTION: str    = (
    "Fun, fast animal facts for curious kids! 🐯📚\n\n"
    "New Shorts every day. Subscribe! "
    "#education #animals #toddlers #shorts\n\n"
    "© 2026 ZooTots. All rights reserved."
)
YOUTUBE_TAGS: list[str]    = ["shorts", "toddlers", "education", "animals", "kids", "zootots"]
YOUTUBE_TITLE_MAX_LEN: int = 100

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_FILE: str  = "pipeline.log"
LOG_LEVEL: str = "DEBUG"