@echo off
cls
echo ==============================================
echo        YOUTUBE AUTOMATION PIPELINE
echo ==============================================

:: Step 1: Research Trending Data
echo [1/5] Fetching trending research data...
python fetch_data.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: Research failed. Check your YouTube API Key.
    pause
    exit /b
)

:: Step 2: Generate Script with Gemini
echo.
echo [2/5] Generating viral script and scene prompts...
python generate_script.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: Script generation failed. Check your Gemini API Key.
    pause
    exit /b
)

:: Step 3: Generate Audio and AI Images
echo.
echo [3/5] Generating Voiceover and AI Visuals...
python generate_media.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: Media generation failed. Check your Hugging Face Token.
    pause
    exit /b
)

:: Step 4: Assemble the Video
echo.
echo [4/5] Editing and Rendering Video (Ken Burns Effect)...
python assemble_video.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: Video assembly failed. Check your MoviePy/Pillow installation.
    pause
    exit /b
)

:: Step 5: Upload to YouTube
echo.
echo [5/5] Initiating YouTube Upload...
:: Note: This will prompt for browser login the first time.
python upload_video.py

echo.
echo ==============================================
echo        PIPELINE COMPLETE! 🚀
echo ==============================================
pause