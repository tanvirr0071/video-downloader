@echo off
REM Video Downloader by Tanvir - Windows launcher. Double-click to start.
title Video Downloader by Tanvir
cd /d "%~dp0"
set "SUP=%LOCALAPPDATA%\Video Downloader"
set "UV=%~dp0bin\uv.exe"
set "VD_UV=%UV%"
set "VD_SUPPORT=%SUP%"
set "UV_PYTHON_INSTALL_DIR=%SUP%\python"
set "UV_CACHE_DIR=%SUP%\cache"
set "PYTHONUNBUFFERED=1"
set "PY=%SUP%\venv\Scripts\python.exe"
if not exist "%SUP%" mkdir "%SUP%"
if exist "%SUP%\.ready-v1" if exist "%PY%" goto upgrade

echo.
echo   First launch: setting up. This takes a minute or two and needs internet.
echo.
if exist "%SUP%\venv" rmdir /s /q "%SUP%\venv"
"%UV%" venv --python 3.13 "%SUP%\venv"
if errorlevel 1 goto fail
"%UV%" pip install --python "%PY%" "yt-dlp[default]" deno imageio-ffmpeg gallery-dl
if errorlevel 1 goto fail
type nul > "%SUP%\.ready-v1"
type nul > "%SUP%\.last-update"
type nul > "%SUP%\.ready-v2"
goto run

:upgrade
if exist "%SUP%\.ready-v2" goto run
echo   Adding photo downloads...
"%UV%" pip install --python "%PY%" -U "yt-dlp[default]" deno imageio-ffmpeg gallery-dl
if not errorlevel 1 type nul > "%SUP%\.ready-v2"

:run
echo.
echo   Video Downloader is running. It opens in your browser.
echo   Keep this window open while you use it. Close it to quit.
echo.
"%PY%" -u "%~dp0app\app.py"
goto end

:fail
echo.
echo   Setup did not finish. Check your internet connection and run this file again.
echo   Still failing? See "READ ME FIRST", under "If something goes wrong".
echo.
pause

:end
