import os
import json
from dotenv import load_dotenv
from googleapiclient.discovery import build

# Load environment variables
load_dotenv()
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

def get_trending_topics(seed_keyword, max_results=5):
    """
    Searches YouTube for the top videos related to a seed keyword
    and extracts their metadata for research.
    Uses safeSearch='strict' to ensure kid-friendly results.
    """
    print(f"Searching YouTube for top safe videos about: '{seed_keyword}'...")
    
    try:
        # Build the YouTube API client
        youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)

        # Execute the search request
        request = youtube.search().list(
            q=seed_keyword,
            part='snippet',
            type='video',
            order='viewCount', # Changed from relevance to viewCount
            maxResults=max_results,
            safeSearch='strict'
        )
        response = request.execute()

        research_data = []

        # Parse the JSON response
        for item in response.get('items', []):
            video_data = {
                'video_id': item['id']['videoId'],
                'title': item['snippet']['title'],
                'description': item['snippet']['description'],
                'channel': item['snippet']['channelTitle'],
                'publish_time': item['snippet']['publishedAt']
            }
            research_data.append(video_data)

        # Save the extracted data to a local file
        output_file = 'research_data.json'
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(research_data, f, indent=4)
            
        print(f"Success! Extracted {len(research_data)} videos and saved to {output_file}")
        return research_data

    except Exception as e:
        print(f"An error occurred: {e}")
        return None

if __name__ == "__main__":
    # Test the module with a kid-friendly niche
    seed = "animal story for toddlers"
    get_trending_topics(seed)