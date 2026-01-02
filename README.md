AlphaSpotify (console)
A minimal, performance-focused console music player that uses yt-dlp to resolve stream URLs and mpv for audio-only playback. No heavy GUI, just a simple console menu.

Quick start (source)
- Requires Python 3.9+
- Install deps:  pip install -r requirements.txt
- Run:  python main.py

Portable distribution (no setup for users)
- Bundle mpv with the app. Place mpv binary in:
  - Windows: ./mpv-bin/mpv.exe
  - Linux/macOS: ./mpv-bin/mpv
- The player first tries bundled mpv, then falls back to system mpv on PATH.
- Zip the folder and share. Users only need Python and yt-dlp installed, or ship a standalone build (see below).

Build a true single-file executable (Windows, embeds mpv, ffmpeg, and icon)
This produces one .exe that users download once; no separate mpv/ffmpeg install or network needed.

1) Prepare mpv-bin and ffmpeg-bin next to main.py
   - Download a Windows mpv zip from shinchiro mpv winbuild releases
     https://github.com/shinchiro/mpv-winbuild-cmake/releases
   - Extract the zip.
   - Create a folder: ./mpv-bin
   - Copy mpv.exe and all DLLs into ./mpv-bin

   - Download ffmpeg essentials zip from https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip
   - Extract and copy ffmpeg.exe and DLLs into ./ffmpeg-bin

   - Ensure icon files are in ./icon/ (spotify.ico and spotify.png)

2) Install build tools
   python -m pip install --upgrade pip
   python -m pip install pyinstaller

3) Build using the provided spec file
   python -m PyInstaller AlphaSpotify.spec

4) Run and test
   dist/AlphaSpotify.exe
   - On first launch, it may download mpv/ffmpeg if not bundled, but with bundling, it's standalone.
   - Test on a machine without mpv/ffmpeg installed.

Notes
- The spec includes mpv-bin, ffmpeg-bin, yt_dlp, and icon.
- If issues, add hidden imports as needed.
- Keep packages consistent (x86_64) with your system.

Controls
- Search by query, pick a result, play via mpv.
- Playback is audio-only, streaming directly from the resolved URL.
