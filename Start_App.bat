@echo off
echo Initializing environment, please wait...

:: 1. Download standalone uv if it doesn't exist in the folder
if not exist uv.exe (
    echo Downloading runner...
    powershell -Command "Invoke-WebRequest -Uri 'https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip' -OutFile 'uv.zip'; Expand-Archive -Path 'uv.zip' -DestinationPath '.' -Force; Remove-Item 'uv.zip'"
)

:: 2. Run the application (uv will auto-fetch Windows Python and your dependencies)
echo Starting application...
.\uv.exe run cp-generator

:: 3. Keep the window open only if the app crashes
if %ERRORLEVEL% neq 0 pause
