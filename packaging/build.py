"""Build the two release zips from this repository.

Usage: python3 packaging/build.py <folder with uv wheels> <output folder>
"""
import glob
import os
import shutil
import stat
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WHEELS = Path(sys.argv[1])
OUT = Path(sys.argv[2])
WORK = OUT / "work"


def from_wheel(pattern, member_suffix, dest):
    wheel = glob.glob(str(WHEELS / pattern))[0]
    with zipfile.ZipFile(wheel) as z:
        name = next(n for n in z.namelist() if n.endswith(member_suffix))
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(z.read(name))


def licenses(dest):
    dest.mkdir(parents=True, exist_ok=True)
    from_wheel("uv-*win_amd64.whl", "licenses/LICENSE-MIT", dest / "uv-LICENSE-MIT.txt")
    from_wheel("uv-*win_amd64.whl", "licenses/LICENSE-APACHE", dest / "uv-LICENSE-APACHE.txt")
    shutil.copy(ROOT / "THIRD-PARTY-NOTICES.md", dest / "THIRD-PARTY-NOTICES.md")


def text(src, dest, crlf=False, bom=True):
    """Plain text; guides get a BOM so Notepad and TextEdit show the Bangla correctly."""
    t = (ROOT / src).read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    if crlf:
        t = t.replace("\n", "\r\n")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(t, encoding="utf-8-sig" if bom else "utf-8", newline="")


def make_executable(p):
    p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def zip_dir(src, zip_path):
    """Zip keeping Unix permissions, so the Mac launcher stays executable."""
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for path in sorted(src.rglob("*")):
            rel = path.relative_to(src).as_posix()
            info = zipfile.ZipInfo(rel + ("/" if path.is_dir() else ""), time.localtime()[:6])
            info.create_system = 3
            info.external_attr = (path.stat().st_mode & 0xFFFF) << 16
            if path.is_dir():
                info.external_attr |= 0x10
                z.writestr(info, b"")
            else:
                info.compress_type = zipfile.ZIP_DEFLATED
                z.writestr(info, path.read_bytes())


shutil.rmtree(OUT, ignore_errors=True)
WORK.mkdir(parents=True)

# ---- Mac ----
mac = WORK / "mac"
app = mac / "Video Downloader.app" / "Contents"
(app / "MacOS").mkdir(parents=True)
shutil.copy(ROOT / "packaging/mac/Info.plist", app / "Info.plist")
launcher = app / "MacOS" / "Video Downloader"
launcher.write_text((ROOT / "packaging/mac/launcher.sh").read_text(encoding="utf-8").replace("\r\n", "\n"),
                    encoding="utf-8", newline="")
make_executable(launcher)
res = app / "Resources"
shutil.copytree(ROOT / "app", res / "app", ignore=shutil.ignore_patterns("__pycache__"))
shutil.copy(ROOT / "packaging/mac/AppIcon.icns", res / "AppIcon.icns")
from_wheel("uv-*macosx*arm64*.whl", "scripts/uv", res / "bin" / "uv")
from_wheel("uv-*macosx*x86_64*.whl", "scripts/uv", res / "bin" / "uv-x86_64")
make_executable(res / "bin" / "uv")
make_executable(res / "bin" / "uv-x86_64")
licenses(res / "licenses")
text("packaging/mac/READ ME FIRST.txt", mac / "READ ME FIRST.txt")
zip_dir(mac, OUT / "Video-Downloader-by-Tanvir-Mac.zip")

# ---- Windows ----
win = WORK / "win" / "Video Downloader"
shutil.copytree(ROOT / "app", win / "app", ignore=shutil.ignore_patterns("__pycache__"))
text("packaging/windows/Start Video Downloader.bat", win / "Start Video Downloader.bat", crlf=True, bom=False)
from_wheel("uv-*win_amd64.whl", "scripts/uv.exe", win / "bin" / "uv.exe")
licenses(win / "licenses")
text("packaging/windows/READ ME FIRST.txt", win / "READ ME FIRST.txt", crlf=True)
zip_dir(WORK / "win", OUT / "Video-Downloader-by-Tanvir-Windows.zip")

shutil.rmtree(WORK)
for z in sorted(OUT.glob("*.zip")):
    print(f"{z.name}  {z.stat().st_size / 1e6:.1f} MB")
