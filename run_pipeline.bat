@echo off
cls
echo ==============================================
echo        ZOOTOTS AUTOMATION PIPELINE
echo ==============================================

:: Step 1: Research
echo [1/6] Fetching popular story data...
python fetch_data.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: Research failed.
    pause
    exit /b
)

:: Step 2: Generate Script
echo.
echo [2/6] Brainstorming original story...
python generate_script.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: Script generation failed.
    pause
    exit /b
)

:: Step 3: Generate Media (15-Minute Cooldown Mode)
echo.
echo [3/6] Generating Voiceover and AI Visuals (Taking it slow!)...
python generate_media.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: Media generation failed.
    pause
    exit /b
)

:: Step 4: Assemble the Video
echo.
echo [4/6] Editing and Rendering 60-Second Video...
python assemble_video.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: Video assembly failed.
    pause
    exit /b
)

:: Step 5: Upload to YouTube
echo.
echo [5/6] Initiating YouTube Upload...
python upload_video.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: YouTube upload failed.
    pause
    exit /b
)

:: Step 6: Cloud Backup
echo.
echo [6/6] Pushing to Google One (Drive Backup)...
python upload_drive.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: Google Drive backup failed. Skipping cleanup to protect files!
    pause
    exit /b
)

:: Step 7: Self-Cleaning
echo.
echo [Cleanup] Backup successful! Emptying local workspace...
if exist "assets" rmdir /s /q "assets"
if exist "final_shorts_video.mp4" del /q "final_shorts_video.mp4"
if exist "script_data.json" del /q "script_data.json"

echo.
echo ==============================================
echo   PIPELINE COMPLETE AND WORKSPACE CLEANED! 🚀
echo ==============================================
pause