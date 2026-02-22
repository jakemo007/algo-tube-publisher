import os
import json
from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel

# Load environment variables
load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# Define the new structural layout: 5 explicit scenes
class Scene(BaseModel):
    text: str
    visual_prompt: str

class VideoContent(BaseModel):
    scenes: list[Scene]

def load_research_data(filepath='research_data.json'):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print("Warning: research_data.json not found.")
        return []

def generate_video_content(topic):
    print(f"Generating viral script and scenes for: '{topic}'...")
    research_items = load_research_data()
    
    # Format the research data
    context_text = "Trending context:\n"
    for item in research_items[:5]:
        context_text += f"Title: {item.get('title')}\n"

    # The new High-Retention Prompt
    # The New 60-Second Storytelling Prompt
    prompt = f"""
    You are a master storyteller for a kid-friendly YouTube channel named ZooTots.
    
    Topic: {topic}
    Research Context: {context_text}
    
    STRICT RULES:
    1. NARRATIVE FORMAT: Write a fun, engaging story following a specific, named animal character (e.g., 'Barnaby the Bear' or 'Pip the Penguin').
    2. THE HOOK: Scene 1 must instantly introduce the character doing something exciting, funny, or surprising. No boring introductions.
    3. EDUCATIONAL VALUE: Weave 2 to 3 real, fascinating facts about the animal naturally into their adventure.
    4. LENGTH & PACING: The total spoken text across all scenes MUST be around 140 to 150 words. This ensures the final voiceover is exactly 60 seconds long.
    5. SCENES: You must break the story into exactly 6 scenes to keep the visuals moving.
    
    Task:
    Output exactly 6 scenes. For each scene, provide the spoken text and a highly detailed visual prompt for an AI image generator. Ensure the visuals are bright, colorful, and styled like a high-end 3D animated children's movie.
    """
    
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=VideoContent,
        temperature=0.7,
    )
    
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=config,
        )
        output_data = json.loads(response.text)
        
        with open('script_data.json', 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=4)
            
        print("Success! Script and prompts saved to script_data.json")
        return output_data
    except Exception as e:
        print(f"An error occurred: {e}")
        return None

if __name__ == "__main__":
    # Test the script generator
    generate_video_content("animal story for toddlers")