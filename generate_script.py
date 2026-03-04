import os
import json
from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel

# Load environment variables
load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# Maintaining the structure, but adding a required title field
class Scene(BaseModel):
    text: str
    visual_prompts: list[str] 

class VideoContent(BaseModel):
    title: str  # NEW: Gemini will now generate a unique title
    scenes: list[Scene]

def load_research_data(filepath='research_data.json'):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print("Warning: research_data.json not found.")
        return []

def generate_video_content():
    print("Initializing Module 2: Brainstorming an original story and title...")
    research_items = load_research_data()
    
    if not research_items:
        print("Error: No research data found. Run fetch_data.py first.")
        return None

    context_text = "Most popular kids animal stories on YouTube right now:\n"
    for item in research_items[:5]:
        context_text += f"- {item.get('title')}\n"

    # Updated Prompt: Now requests a title and enforces the Subscribe CTA
    prompt = f"""
    You are a master storyteller and video editor for a kid-friendly YouTube channel named ZooTots.
    
    Research Context:
    {context_text}
    
    STRICT RULES:
    1. CREATE A UNIQUE TOPIC: Invent a brand new, original 60-second story about a specific, named animal character.
    2. THE TITLE: Write a catchy, highly-clickable YouTube Shorts title (under 60 characters) with 1 or 2 emojis. Do not include #shorts, I will add that later.
    3. THE HOOK: Scene 1 must instantly grab attention. No boring introductions.
    4. EDUCATIONAL: Weave 2 to 3 fascinating, real facts about the animal.
    5. THE CTA: The spoken text in the final scene (Scene 6) MUST end with a high-energy phrase asking the viewer to subscribe to ZooTots.
    6. LENGTH: The total spoken text across all scenes MUST be around 140 to 150 words.
    7. SCENES: You must output exactly 6 scenes.
    8. FAST VISUAL PACING: For EACH scene, provide exactly 5 different visual prompts.
    
    Task:
    Output the unique title and exactly 6 scenes. Make the visuals bright, colorful, high-end 3D animated children's movie style.
    """
    
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=VideoContent,
        temperature=0.8, 
    )
    
    try:
        print("Asking Gemini to write the script. This takes a few seconds...")
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=config,
        )
        output_data = json.loads(response.text)
        
        with open('script_data.json', 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=4)
            
        print(f"Success! Generated Title: '{output_data.get('title')}'")
        return output_data
        
    except Exception as e:
        print(f"An error occurred: {e}")
        return None

if __name__ == "__main__":
    generate_video_content()