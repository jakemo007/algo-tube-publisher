import os
import json
from googleapiclient.discovery import build
from dotenv import load_dotenv

# Load environment variables
_ = load_dotenv()
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

def fetch_popular_stories():
    print("Initializing Module 1: Researching popular children's stories...")
    
    if not YOUTUBE_API_KEY:
        print("Error: Missing YOUTUBE_API_KEY in your .env file.")
        return

    youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)

    try:
        # We target specific keywords that parents search for at bedtime/storytime
        request = youtube.search().list(
            q="popular cat stories for kids toddlers",
            part='snippet',
            type='video',
            order='viewCount', 
            maxResults=10,
            safeSearch='strict'
        )
        response = request.execute()

        research_data = []
        for item in response.get('items', []):
            title = item['snippet']['title']
            description = item['snippet']['description']
            research_data.append({
                "title": title,
                "description": description
            })

        # Save the finding so Module 2 can read them
        with open('research_data.json', 'w', encoding='utf-8') as f:
            json.dump(research_data, f, indent=4)
            
        print("Success! Popular story titles saved to research_data.json.")

    except Exception as e:
        print(f"An error occurred while fetching data: {e}")

if __name__ == "__main__":
    fetch_popular_stories()