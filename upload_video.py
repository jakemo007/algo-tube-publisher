import os
import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.errors
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

# This specific scope allows the script to upload and manage videos
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

def get_authenticated_service():
    """Authenticates the user and saves the token for future silent uploads."""
    creds = None
    client_secrets_file = "client_secret.json"
    token_file = "token.json"

    # 1. Check if we already have a saved token from a previous run
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)

    # 2. If there are no valid credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            # If the token is just expired, silently refresh it in the background
            print("Refreshing expired access token...")
            creds.refresh(Request())
        else:
            # First time ever running (or token was deleted): pop open the browser
            if not os.path.exists(client_secrets_file):
                print(f"Error: {client_secrets_file} is missing in your folder.")
                return None
                
            print("No saved token found. Opening browser for initial login...")
            flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
                client_secrets_file, SCOPES
            )
            creds = flow.run_local_server(port=0)
            
        # 3. Save the credentials (including the refresh token) for the next run
        with open(token_file, 'w') as token:
            token.write(creds.to_json())
            print("Authentication token saved securely to token.json!")

    # Build and return the authorized API client
    return googleapiclient.discovery.build(
        "youtube", "v3", credentials=creds
    )

def upload_video(youtube):
    """Uploads the final MP4 file to the authenticated YouTube channel."""
    video_path = "final_shorts_video.mp4"
    
    if not os.path.exists(video_path):
        print(f"Error: {video_path} not found. Run Module 4 first.")
        return

    print("\nPreparing the video metadata...")
    
    # Define the video's details, tags, language, and category (27 = Education)
    # Define the video's details, tags, language, and category (27 = Education)
    request_body = {
        "snippet": {
            "title": "Fascinating Animal Facts for Toddlers! 🦁✨ #shorts",
            "description": "Fun, fast, and educational animal facts for curious kids! 🐯📚\n\nAt ZooTots, we turn wildlife education into an adventure. Our kid-friendly Shorts are designed to grab your toddler's attention with bright colors and teach them amazing things about the animal kingdom.\n\n🌟 New educational Shorts every day.\n✅ Safe, fun, and parent-approved!\n\nSubscribe to join our little explorer family today! #education #animals #toddlers #shorts\n\n© 2026 ZooTots. All rights reserved.",
            "tags": ["shorts", "toddlers", "education", "animals", "kids", "zootots"],
            "categoryId": "27",
            "defaultLanguage": "en-US",
            "defaultAudioLanguage": "en-US"
        },
        "status": {
            "privacyStatus": "public", 
            "selfDeclaredMadeForKids": True,
            "license": "youtube" # Explicitly sets the Standard YouTube License for copyright protection
        }
    }

    # Attach the physical MP4 file
    media_file = MediaFileUpload(video_path, chunksize=-1, resumable=True)

    print(f"Uploading '{video_path}' to YouTube (this may take a minute depending on your internet speed)...")
    
    try:
        request = youtube.videos().insert(
            part="snippet,status",
            body=request_body,
            media_body=media_file
        )
        response = request.execute()
        
        print("\nSuccess! Your video is live on YouTube Studio.")
        print(f"Video ID: {response.get('id')}")
        print(f"Manage it here: https://studio.youtube.com/video/{response.get('id')}/edit")
        
    except googleapiclient.errors.HttpError as e:
        print(f"\nAn HTTP error occurred:\n{e}")

def run_upload_pipeline():
    print("Initializing Module 5: YouTube Upload...")
    youtube_service = get_authenticated_service()
    
    if youtube_service:
        upload_video(youtube_service)

if __name__ == "__main__":
    run_upload_pipeline()