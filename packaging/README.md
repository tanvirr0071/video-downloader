# Packaging

How the release zips are put together. The download engines are not stored here: the app installs them on first launch with uv.

**Mac** (`Video Downloader.app`)
```
Contents/Info.plist                 packaging/mac/Info.plist
Contents/MacOS/Video Downloader     packaging/mac/launcher.sh   (chmod 755)
Contents/Resources/AppIcon.icns     packaging/mac/AppIcon.icns
Contents/Resources/app/             app/app.py, app/ui.html, app/icon.png
Contents/Resources/bin/uv           uv for Apple Silicon (from the uv wheel on PyPI)
Contents/Resources/bin/uv-x86_64    uv for Intel Macs
Contents/Resources/licenses/        uv licenses and THIRD-PARTY-NOTICES.md
```
Zip it next to `READ ME FIRST.txt` as `Video-Downloader-by-Tanvir-Mac.zip`.

**Windows** (`Video Downloader/`)
```
Start Video Downloader.bat          packaging/windows/Start Video Downloader.bat  (CRLF line endings)
app/                                app/app.py, app/ui.html, app/icon.png
bin/uv.exe                          uv for Windows x64 (from the uv wheel on PyPI)
licenses/                           uv licenses and THIRD-PARTY-NOTICES.md
READ ME FIRST.txt                   packaging/windows/READ ME FIRST.txt
```
Zip the folder as `Video-Downloader-by-Tanvir-Windows.zip`.

Upload both zips to a new GitHub Release. The website's buttons always point at the latest release.
