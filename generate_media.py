import os
import json
import asyncio
import edge_tts
import requests
import time
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
HF_API_KEY = os.getenv("HUGGINGFACE_API_KEY")

async def generate_scene_audio(text, index):
    """Generates a dedicated MP3 for a single scene."""
    voice = "en-US-AriaNeural"
    filename = f"assets/voice_{index}.mp3"
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(filename)
    print(f"   Saved {filename}")

def generate_scene_image(prompt, index):
    """Generates a dedicated image for a single scene."""
    if not HF_API_KEY:
        print("Error: Missing HUGGINGFACE_API_KEY.")
        return
        
    API_URL = "https://router.huggingface.co/hf-inference/models/black-forest-labs/FLUX.1-schnell"
    headers = {"Authorization": f"Bearer {HF_API_KEY}"}
    
    # Enforce the high-end 3D animated style for your story
    enhanced_prompt = f"{prompt}, bright colorful high-end 3D animated children's movie style, highly detailed"
    
    try:
        response = requests.post(API_URL, headers=headers, json={"inputs": enhanced_prompt})
        
        if response.status_code == 503:
            print("   Model loading. Waiting 15 seconds...")
            time.sleep(15)
            response = requests.post(API_URL, headers=headers, json={"inputs": enhanced_prompt})

        if response.status_code == 200:
            filename = f"assets/scene_{index}.jpg"
            with open(filename, 'wb') as f:
                f.write(response.content)
            print(f"   Saved {filename}")
        else:
            print(f"   Error: Status {response.status_code}. Details: {response.text}")
            
    except Exception as e:
        print(f"   Error generating image {index}: {e}")

def run_media_pipeline():
    os.makedirs("assets", exist_ok=True)
    
    try:
        with open('script_data.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        print("Error: script_data.json not found. Run generate_script.py first.")
        return
    
    scenes = data.get("scenes", [])
    # UPDATED: Now requires exactly 6 scenes for the 60-second format
    if not scenes or len(scenes) != 6:
        print(f"Error: Invalid script data. Expected exactly 6 scenes, found {len(scenes)}.")
        return
        
    print("\nGenerating synchronized audio and images for 6 scenes...")
    
    # Generate Audio
    print("\n--- Generating Audio ---")
    async def build_all_audio():
        for i, scene in enumerate(scenes):
            await generate_scene_audio(scene["text"], i + 1)
    asyncio.run(build_all_audio())
    
    # Generate Images
    print("\n--- Generating AI Images ---")
    for i, scene in enumerate(scenes):
        generate_scene_image(scene["visual_prompt"], i + 1)
        
    print("\nModule 3 complete! Perfect sync assets are ready.")

if __name__ == "__main__":
    run_media_pipeline()