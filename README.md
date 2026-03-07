# algo-tube-publisher

Automated YouTube video creation pipeline using Python, Gemini, and Veo.

# Create the environment

conda create -n youtube-auto python=3.13 -y

# Activate the environment

conda activate youtube-auto

drive_client.py (new) ← reusable Drive auth + folder/upload/download/delete
↑ used by
generate_media.py ← upload each video to Drive after generation, store drive_file_id in ChromaDB
rag_database.py ← metadata stores drive_file_id; cache hit downloads from Drive
upload_drive.py ← rewrite using drive_client.py; backs up final_video + script
main.py ← add Step 5 (Drive backup) + Step 6 (local cleanup)
config.py ← add Drive folder constants, remove VIDEO_VAULT_DIR
