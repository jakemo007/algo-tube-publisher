import os
import json
import asyncio
import edge_tts
import requests
import time
from dotenv import load_dotenv

load_dotenv()
HF_API_KEY = os.getenv("HUGGINGFACE_API_KEY")

async def generate_scene_audio(text, index):
    voice = "en-US-JennyNeural"
    filename = f"assets/voice_{index}.mp3"
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(filename)
    print(f"   Saved {filename}")

def generate_scene_image(prompt, scene_index, img_index):
    if not HF_API_KEY:
        print("Error: Missing HUGGINGFACE_API_KEY.")
        return
        
    API_URL = "https://router.huggingface.co/hf-inference/models/black-forest-labs/FLUX.1-schnell"
    headers = {"Authorization": f"Bearer {HF_API_KEY}"}
    
    enhanced_prompt = f"{prompt}, bright colorful high-end 3D animated children's movie style, highly detailed"
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = requests.post(API_URL, headers=headers, json={"inputs": enhanced_prompt})
            
            if response.status_code == 200:
                filename = f"assets/scene_{scene_index}_img_{img_index}.jpg"
                with open(filename, 'wb') as f:
                    f.write(response.content)
                print(f"   Saved {filename}")
                return 
                
            elif response.status_code in [503, 429]:
                print(f"   API busy. Waiting 10 seconds (Attempt {attempt+1}/{max_retries})...")
                time.sleep(10)
            else:
                print(f"   Error: Status {response.status_code}. Details: {response.text}")
                break 
                
        except Exception as e:
            print(f"   Error generating image: {e}")
            time.sleep(5)

def run_media_pipeline():
    os.makedirs("assets", exist_ok=True)
    
    try:
        with open('script_data.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        print("Error: script_data.json missing.")
        return
    
    scenes = data.get("scenes", [])
    if not scenes or len(scenes) != 6:
        print(f"Error: Expected exactly 6 scenes.")
        return
        
    print("\nGenerating synchronized audio and 30 high-paced images...")
    
    # Generate Audio
    print("\n--- Generating Audio (6 files) ---")
    async def build_all_audio():
        for i, scene in enumerate(scenes):
            await generate_scene_audio(scene["text"], i + 1)
    asyncio.run(build_all_audio())
    
    # Generate Images (5 per scene)
    print("\n--- Generating AI Images (Stealth Mode: ~15 minute duration) ---")
    for i, scene in enumerate(scenes):
        print(f"\nProcessing Scene {i+1} visuals...")
        prompts = scene.get("visual_prompts", [])
        
        while len(prompts) < 5: prompts.append(prompts[0] if prompts else "cute animal")
            
        for j in range(5):
            generate_scene_image(prompts[j], i + 1, j + 1)
            # 25-second delay to guarantee free-tier API stability
            print("   Waiting 25 seconds for API cooldown...")
            time.sleep(25) 
            
    print("\nModule 3 complete! Fast-paced assets are ready.")

if __name__ == "__main__":
    run_media_pipeline()