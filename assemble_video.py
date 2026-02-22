import os
import PIL.Image

# ---------------------------------------------------------
# Monkey-patch to fix MoviePy's Pillow 10 compatibility bug
if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.Resampling.LANCZOS
# ---------------------------------------------------------

from moviepy.editor import AudioFileClip, ImageClip, concatenate_videoclips

def build_synchronized_video():
    print("Initializing Module 4: Synchronized Video Assembly...")
    clips = []
    
    for i in range(1, 7):
        audio_path = f"assets/voice_{i}.mp3"
        image_path = f"assets/scene_{i}.jpg"
        
        if not os.path.exists(audio_path) or not os.path.exists(image_path):
            print(f"Error: Missing assets for scene {i}!")
            return
            
        # 1. Load the exact audio for this specific scene
        audio = AudioFileClip(audio_path)
        scene_duration = audio.duration
        
        # 2. Load the image and set it to match the exact audio length
        base_clip = ImageClip(image_path).set_duration(scene_duration)
        
        # 3. Apply the Ken Burns zoom to give it a GIF/Video motion feel
        def zoom_effect(t, duration=scene_duration):
            return 1 + 0.08 * (t / duration)
            
        # 4. Tie the image, the animation, and the audio together
        animated_clip = (
            base_clip.resize(zoom_effect)
            .crop(x_center=540, y_center=960, width=1080, height=1920)
            .set_audio(audio)
        )
        
        clips.append(animated_clip)
        print(f"-> Scene {i} synchronized ({scene_duration:.2f}s).")
        
    print("\nStitching clips together into final timeline...")
    final_video = concatenate_videoclips(clips, method="compose")
    
    output_filename = "final_shorts_video.mp4"
    print(f"\nRendering final video to {output_filename}...")
    
    final_video.write_videofile(
        output_filename, 
        fps=24, 
        codec="libx264", 
        audio_codec="aac",
        threads=4
    )
    
    print("\nSuccess! Perfectly synced video is ready.")

if __name__ == "__main__":
    build_synchronized_video()