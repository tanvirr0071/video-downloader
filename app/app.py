#!/usr/bin/env python3
"""Video Downloader — YouTube, Facebook, Instagram, Pinterest, TikTok, X and more.
Runs a local web app on http://127.0.0.1:8765 (only your computer can open it).
"""
import json
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import yt_dlp

APP_VERSION = "1.2"
APP_DIR = Path(__file__).resolve().parent
PORT = int(os.environ.get("VD_PORT", "8765"))
DOWNLOAD_DIR = Path(os.environ.get("VD_DIR", Path.home() / "Downloads" / "Video Downloader"))
IS_WIN = platform.system() == "Windows"

# Make the venv's bin (deno lives there) visible to yt-dlp
_bin = Path(sys.executable).parent
os.environ["PATH"] = str(_bin) + os.pathsep + os.environ.get("PATH", "")


def find_ffmpeg():
    """Return a directory containing a binary named ffmpeg / ffmpeg.exe."""
    name = "ffmpeg.exe" if IS_WIN else "ffmpeg"
    system = shutil.which("ffmpeg")
    if system:
        return str(Path(system).parent)
    try:
        import imageio_ffmpeg
        exe = Path(imageio_ffmpeg.get_ffmpeg_exe())
    except Exception:
        return None
    if exe.name == name:
        return str(exe.parent)
    local = Path(os.environ.get("VD_SUPPORT") or APP_DIR) / ".bin"
    try:
        local.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    target = local / name
    if not target.exists() or target.stat().st_size != exe.stat().st_size:
        shutil.copy2(exe, target)
        if not IS_WIN:
            target.chmod(0o755)
    return str(local)


FFMPEG_DIR = find_ffmpeg()
JOBS = {}
JOBS_LOCK = threading.Lock()


def platform_of(url):
    u = url.lower()
    for key, label in (("youtu", "YouTube"), ("facebook", "Facebook"), ("fb.watch", "Facebook"),
                       ("instagram", "Instagram"), ("pinterest", "Pinterest"), ("pin.it", "Pinterest"),
                       ("tiktok", "TikTok"), ("twitter", "X"), ("x.com", "X"), ("vimeo", "Vimeo"),
                       ("reddit", "Reddit"), ("linkedin", "LinkedIn")):
        if key in u:
            return label
    return "Web"


def build_format(mode, quality):
    h = None if quality == "best" else int(quality)
    cap = f"[height<={h}]" if h else ""
    if mode == "audio":
        return "ba/b"
    if mode == "max":
        return f"bv*{cap}+ba/b{cap}/bv*+ba/b"
    # "edit": H.264 + AAC MP4 that opens cleanly in Premiere Pro / After Effects / CapCut
    return (f"bv*[vcodec^=avc]{cap}+ba[acodec^=mp4a]/"
            f"bv*[vcodec^=avc]{cap}+ba/"
            f"b[vcodec^=avc]{cap}/"
            f"bv*{cap}+ba/b{cap}/bv*+ba/b")


def update(job_id, **kw):
    with JOBS_LOCK:
        JOBS[job_id].update(kw)


NO_VIDEO = ("no video", "there is no video", "unsupported url", "no media", "does not contain any video",
            "no formats", "requested format is not available", "not a video")


def is_photo_first(url):
    """Links that are usually photos (or mixed photo+video posts) go to gallery-dl first."""
    u = url.lower()
    if "instagram.com" in u:
        return not any(k in u for k in ("/reel/", "/reels/", "/tv/"))
    if "pinterest." in u or "pin.it" in u:
        return "/pin/" not in u and "pin.it" not in u   # boards and profiles; single pins try video first
    return u.split("?")[0].endswith((".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif", ".heic"))


IS_MAC = platform.system() == "Darwin"
LOGIN_WORDS = ("login", "log in", "logged in", "sign in", "private", "cookies", "members-only", "members only",
               "age-restricted", "confirm your age", "inappropriate", "not a bot", "checkpoint", "401",
               "authorization", "authentication", "requires account", "registered users")

FIXES = [
    # (words that identify the problem, what the person should do)
    (("dpapi", "app-bound", "appbound"),
     "Windows does not let other apps read Chrome or Edge logins. Choose \"Use my Firefox login\" instead, "
     "and log in to the site in Firefox first."),
    (("could not copy chrome cookie", "could not copy", "database is locked", "failed to decrypt",
      "keychain", "safe storage", "secretstorage", "cookies database", "failed to load cookies"),
     "The app couldn't read your browser login. Close that browser completely and try again. On a Mac, "
     "click Always Allow when it asks for Keychain access. If it still fails, choose another browser."),
    (("binarycookies", "operation not permitted"),
     "Reading Safari logins needs permission. Open System Settings, Privacy & Security, Full Disk Access, "
     "and turn on Video Downloader. Or choose \"Use my Chrome login\" instead."),
    (("login required", "login_required", "logged-in", "requires login", "need to log in", "you need to log in"),
     None),
    (("drm",),
     "This video is copy-protected (DRM), like Netflix, Spotify or Apple Music. It can't be downloaded."),
    (("available in your country", "in your country", "geo restrict", "geo-restrict", "not available from your location",
      "blocked it in your country", "georestricted"),
     "This is blocked in your country. A VPN set to another country may work."),
    (("live event will begin", "premieres in", "is live", "live stream", "this live event"),
     "This is a live stream or premiere that hasn't finished. Try again after it ends."),
    (("429", "too many requests", "rate-limit", "rate limit", "ratelimit", "try again later"),
     "The site is limiting downloads for now. Wait 10 to 15 minutes, then try again with fewer links at once."),
    (("no space left", "disk full", "errno 28"),
     "Your disk is full. Free up some space, then try again."),
    (("getaddrinfo", "name or service not known", "nodename nor servname", "temporary failure in name",
      "timed out", "connection reset", "connection refused", "no route to host", "network is unreachable",
      "connectionerror", "connection aborted", "remote end closed"),
     "The internet connection dropped or is blocked. Check that you're online, then try again."),
    (("ffmpeg", "ffprobe"),
     "A helper the app needs is missing. Close the app and open it again so it can repair itself."),
    (("http error 404", "404: not found", "does not exist", "page not found"),
     "That page doesn't exist. Open the link in your browser to check it, then copy it again."),
    (("requested format is not available", "format is not available"),
     "That quality isn't offered for this video. Choose \"Best available\" and try again."),
    (("403", "forbidden"),
     "The site refused the download. Wait a few minutes and try again, the app updates itself each day and "
     "that often fixes it. If it keeps happening, choose a browser login and try again."),
    (("unsupported url", "no video", "no media", "no formats", "nothing to save", "no photos or videos",
      "not a video", "no suitable"),
     "Nothing to save was found at that link. Check that it opens a video, photo or song in your browser. "
     "If the post is private, choose a browser login."),
]


def clean_error(msg):
    """Turn an engine error into one plain instruction the person can act on."""
    import re
    raw = str(msg).replace("\x1b[0;31mERROR:\x1b[0m ", "").replace("ERROR: ", "").strip()
    raw = re.sub(r"\x1b\[[0-9;]*m", "", raw)
    detail = re.sub(r"\s*\(caused by .*\)$", "", re.sub(r"^\[[\w:.-]+\] [^:]{1,80}: ", "", raw))
    low = raw.lower()
    browser = "Chrome" if IS_MAC else "Firefox"
    login_fix = ("This needs you to be logged in. Log in to the site in your browser, choose "
                 f"\"Use my {browser} login\" here, and download again.")
    for words, fix in FIXES:
        if any(w in low for w in words):
            return fix or login_fix
    if any(w in low for w in LOGIN_WORDS):
        return login_fix
    detail = detail[:300].rstrip(" .") + "."
    return detail + " If this keeps happening, close and reopen the app, it updates itself."


def run_gallery(job_id, url, opts, out_dir):
    """Photos and photo posts via gallery-dl. Returns the list of saved files; raises on failure."""
    update(job_id, status="starting", mode="photo", label="Photos")
    cmd = [sys.executable, "-m", "gallery_dl", "-D", str(out_dir), "--no-part",
           "-o", "output.mode=pipe", "-o", "output.progress=false"]
    if not opts.get("playlist"):
        cmd += ["--range", "1-60"]
    browser = opts.get("cookies")
    if browser and browser != "none":
        cmd += ["--cookies-from-browser", browser]
    cmd.append(url)
    env = dict(os.environ)
    if FFMPEG_DIR:
        env["PATH"] = FFMPEG_DIR + os.pathsep + env.get("PATH", "")
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            encoding="utf-8", errors="replace", env=env)
    errs = []

    def read_err():
        for line in proc.stderr:
            line = line.strip()
            if line:
                errs.append(line)
    t = threading.Thread(target=read_err, daemon=True)
    t.start()
    files = []
    for line in proc.stdout:
        line = line.strip()
        if not line:
            continue
        path = line[2:] if line.startswith("# ") else line
        if os.path.sep in path or "/" in path:
            files.append(path)
            n = len(files)
            update(job_id, status="downloading", percent=None, item="",
                   title=f"{n} file{'s' if n != 1 else ''} from {JOBS[job_id]['platform']}")
    proc.wait()
    t.join(timeout=2)
    if not files:
        bad = [e for e in errs if "[error]" in e.lower() or "error" in e.lower()] or errs
        raise RuntimeError(re_strip(bad[-1]) if bad else "No photos or videos were found at that link.")
    return files


def re_strip(line):
    import re
    return re.sub(r"^\[[^\]]*\]\[[^\]]*\]\s*", "", line)


class TailLogger:
    """Keeps yt-dlp's debug output in memory; printed to the log only when a download fails."""
    def __init__(self):
        self.lines = []

    def _add(self, m):
        self.lines.append(str(m)[:600])
        del self.lines[:-120]

    def debug(self, m):
        self._add(m)

    def info(self, m):
        self._add(m)

    def warning(self, m):
        self._add("WARNING: " + str(m))

    def error(self, m):
        self._add("ERROR: " + str(m))

    def dump(self, url):
        print(f"----- yt-dlp debug for {url} -----")
        for line in self.lines:
            print(line)
        print("----- end -----", flush=True)


YT_RETRY_CLIENTS = [None, ["default", "web_safari"], ["tv", "web_embedded"]]


def run_ytdlp(job_id, url, opts, out_dir):
    def hook(d):
        info = d.get("info_dict") or {}
        idx = info.get("playlist_index")
        total = info.get("n_entries") or info.get("playlist_count")
        item = f"{idx} of {total}" if idx and total else ""
        if d["status"] == "downloading":
            done = d.get("downloaded_bytes") or 0
            tot = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            update(job_id, status="downloading",
                   title=info.get("title") or JOBS[job_id]["title"],
                   percent=round(done * 100 / tot, 1) if tot else None,
                   speed=d.get("speed"), eta=d.get("eta"), item=item)
        elif d["status"] == "finished":
            update(job_id, status="processing", percent=100, item=item)

    def pp_hook(d):
        if d["status"] == "started":
            update(job_id, status="processing")

    mode = opts.get("mode", "edit")
    quality = opts.get("quality", "best")
    keep_thumb = bool(opts.get("thumbnail"))
    ydl_opts = {
        "format": (("ba[ext=m4a]/ba[acodec^=mp4a]/ba[ext=mp3]/ba/b" if quality == "best" else "ba/b")
                   if mode == "audio" else build_format(mode, quality)),
        "outtmpl": str(out_dir / "%(title).120B [%(id)s].%(ext)s"),
        "noplaylist": not opts.get("playlist"),
        "progress_hooks": [hook],
        "postprocessor_hooks": [pp_hook],
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "windowsfilenames": True,
        "retries": 10,
        "fragment_retries": 10,
        "concurrent_fragment_downloads": 4,
        "overwrites": False,
        "postprocessors": [],
    }
    if FFMPEG_DIR:
        ydl_opts["ffmpeg_location"] = FFMPEG_DIR
    pps = ydl_opts["postprocessors"]
    if mode == "audio":
        codec = quality if quality in ("flac", "mp3") else "best"
        ex = {"key": "FFmpegExtractAudio", "preferredcodec": codec}
        if codec == "mp3":
            ex["preferredquality"] = "320"
        pps.append(ex)
        pps.append({"key": "FFmpegMetadata", "add_metadata": True})
        ydl_opts["writethumbnail"] = True
        pps.append({"key": "FFmpegThumbnailsConvertor", "format": "jpg", "when": "before_dl"})
        pps.append({"key": "EmbedThumbnail", "already_have_thumbnail": keep_thumb})
    else:
        ydl_opts["merge_output_format"] = "mp4" if mode == "edit" else "mp4/mkv"
        if mode == "edit":
            pps.append({"key": "FFmpegVideoRemuxer", "preferedformat": "mp4"})
        if keep_thumb:
            ydl_opts["writethumbnail"] = True
            pps.append({"key": "FFmpegThumbnailsConvertor", "format": "jpg", "when": "before_dl"})
    if opts.get("subtitles") and mode != "audio":
        ydl_opts.update({"writesubtitles": True, "subtitleslangs": ["en.*", "bn.*"], "subtitlesformat": "srt/best"})
        pps.append({"key": "FFmpegSubtitlesConvertor", "format": "srt"})
    browser = opts.get("cookies")
    if browser and browser != "none":
        ydl_opts["cookiesfrombrowser"] = (browser,)

    update(job_id, status="starting")
    is_yt = any(k in url.lower() for k in ("youtube.com", "youtu.be"))
    attempts = YT_RETRY_CLIENTS if is_yt else [None, None]
    info = None
    for n, clients in enumerate(attempts):
        log = TailLogger()
        o = dict(ydl_opts, logger=log, verbose=True, quiet=False, no_warnings=False)
        if clients:
            o["extractor_args"] = {"youtube": {"player_client": clients}}
        try:
            with yt_dlp.YoutubeDL(o) as ydl:
                info = ydl.extract_info(url, download=False, process=False)
                if info.get("_type", "video") == "video" and only_images(info):
                    raise yt_dlp.utils.DownloadError("There is no video in this link, it is a photo.")
                info = ydl.process_ie_result(info, download=True)
            break
        except Exception as e:  # noqa: BLE001
            log.dump(url)
            if "403" in str(e) and n + 1 < len(attempts):
                print(f"403 on attempt {n + 1}, retrying with player_client={attempts[n + 1]}", flush=True)
                update(job_id, status="starting", percent=0, speed=None, eta=None)
                continue
            raise
    files = []

    def collect(i):
        if not i:
            return
        for e in i.get("entries") or []:
            collect(e)
        for r in i.get("requested_downloads") or []:
            if r.get("filepath"):
                files.append(r["filepath"])
    collect(info)
    update(job_id, title=(info or {}).get("title") or JOBS[job_id]["title"])
    return files


IMAGE_EXTS = {"jpg", "jpeg", "png", "webp", "gif", "avif", "heic", "bmp", "svg"}


def only_images(info):
    """True when everything yt-dlp found is a still image (so it would wrongly become an .mp4)."""
    fmts = info.get("formats") or [info]
    for f in fmts:
        ext = (f.get("ext") or "").lower()
        if not ext and f.get("url"):
            ext = f["url"].split("?")[0].rsplit(".", 1)[-1].lower()
        has_av = (f.get("vcodec") not in (None, "none")) or (f.get("acodec") not in (None, "none"))
        if has_av or ext not in IMAGE_EXTS:
            return False
    return True


AUDIO_LABEL = {"flac": "FLAC", "mp3": "MP3 320", "best": "Original M4A"}


def run_job(job_id, opts):
    job = JOBS[job_id]
    url = job["url"]
    out_dir = DOWNLOAD_DIR / job["platform"]
    out_dir.mkdir(parents=True, exist_ok=True)
    mode = opts.get("mode", "edit")
    if mode == "audio":
        update(job_id, label=AUDIO_LABEL.get(opts.get("quality"), "Audio"))
        order = [run_ytdlp]
    elif is_photo_first(url):
        order = [run_gallery, run_ytdlp]
    else:
        order = [run_ytdlp, run_gallery]
    first_err = None
    for i, fn in enumerate(order):
        try:
            if i:
                update(job_id, status="starting", percent=0, speed=None, eta=None, item="")
            files = fn(job_id, url, opts, out_dir)
            done_label = JOBS[job_id].get("label")
            if fn is run_ytdlp and mode != "audio":
                done_label = None
                update(job_id, mode=mode, label=None)
            n = len(files)
            if fn is run_gallery:
                if n == 1:
                    kind = "Photo" if Path(files[0]).suffix.lower().lstrip(".") in IMAGE_EXTS else "Video"
                    update(job_id, title=f"{kind} from {job['platform']}")
                else:
                    update(job_id, title=f"{n} files from {job['platform']}")
            update(job_id, files=files, status="done", percent=100, speed=None, eta=None, item="",
                   label=done_label, finished=time.time())
            return
        except Exception as e:  # noqa: BLE001
            err = clean_error(e)
            first_err = first_err or err
            low = str(e).lower()
            # move on to the other engine only when this one says there is nothing for it here
            if i + 1 < len(order) and (fn is run_gallery or any(k in low for k in NO_VIDEO)):
                continue
            final = first_err if (i and (any(k in low for k in NO_VIDEO) or "unsupported" in low)) else err
            update(job_id, status="error", error=final, speed=None, eta=None, item="")
            return
    update(job_id, status="error", error=first_err or "Nothing could be saved from that link.", speed=None, eta=None)


def start_job(url, opts):
    job_id = uuid.uuid4().hex[:10]
    with JOBS_LOCK:
        JOBS[job_id] = {"id": job_id, "url": url, "platform": platform_of(url), "title": url,
                        "status": "queued", "percent": 0, "speed": None, "eta": None, "item": "",
                        "error": None, "files": [], "created": time.time(), "mode": opts.get("mode"), "label": None}
    threading.Thread(target=run_job, args=(job_id, opts), daemon=True).start()
    return job_id


def open_path(p):
    p = str(p)
    if IS_WIN:
        os.startfile(p)  # noqa: S606
    elif platform.system() == "Darwin":
        subprocess.Popen(["open", p])
    else:
        subprocess.Popen(["xdg-open", p])


def reveal(p):
    p = str(p)
    if IS_WIN:
        subprocess.Popen(["explorer", "/select,", p])
    elif platform.system() == "Darwin":
        subprocess.Popen(["open", "-R", p])
    else:
        open_path(Path(p).parent)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _json(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def _local_only(self):
        host = (self.headers.get("Host") or "").split(":")[0]
        return host in ("127.0.0.1", "localhost")

    def do_GET(self):
        if not self._local_only():
            return self._send(403, "{}")
        if self.path in ("/", "/index.html"):
            return self._send(200, (APP_DIR / "ui.html").read_bytes(), "text/html")
        if self.path == "/api/jobs":
            with JOBS_LOCK:
                jobs = sorted(JOBS.values(), key=lambda j: j["created"], reverse=True)
                return self._send(200, json.dumps({"jobs": jobs, "folder": str(DOWNLOAD_DIR),
                                                   "ffmpeg": bool(FFMPEG_DIR),
                                                   "version": yt_dlp.version.__version__}))
        self._send(404, "{}")

    def do_POST(self):
        if not self._local_only() or self.headers.get("Origin", "").split("://")[-1].split(":")[0] not in ("", "127.0.0.1", "localhost"):
            return self._send(403, "{}")
        body = self._json()
        if self.path == "/api/download":
            urls = [u.strip() for u in body.get("urls", []) if u.strip().startswith("http")]
            if not urls:
                return self._send(400, json.dumps({"error": "No valid link found."}))
            ids = [start_job(u, body) for u in urls]
            return self._send(200, json.dumps({"ids": ids}))
        if self.path == "/api/open-folder":
            DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
            open_path(DOWNLOAD_DIR)
            return self._send(200, "{}")
        if self.path == "/api/reveal":
            job = JOBS.get(body.get("id"))
            files = [f for f in (job or {}).get("files", []) if os.path.exists(f)]
            if files:
                reveal(files[-1])
            else:
                open_path(DOWNLOAD_DIR / (job or {}).get("platform", ""))
            return self._send(200, "{}")
        if self.path == "/api/restart":
            def again():
                time.sleep(0.4)
                bundle = APP_DIR.parents[1].parent  # .../Video Downloader.app
                if "--window" in sys.argv and platform.system() == "Darwin" and bundle.suffix == ".app":
                    # a fresh launch through macOS; replacing the running process breaks the native window
                    subprocess.Popen(["/bin/sh", "-c", f'sleep 1; open -n "{bundle}"'], start_new_session=True)
                    os._exit(0)
                os.execv(sys.executable, [sys.executable, "-u", str(APP_DIR / "app.py")] + sys.argv[1:])
            threading.Thread(target=again, daemon=True).start()
            return self._send(200, "{}")
        if self.path == "/api/version":
            return self._send(200, json.dumps({"app": APP_VERSION, "yt_dlp": yt_dlp.version.__version__}))
        if self.path == "/api/clear":
            with JOBS_LOCK:
                for k in [k for k, j in JOBS.items() if j["status"] in ("done", "error")]:
                    del JOBS[k]
            return self._send(200, "{}")
        self._send(404, "{}")


def background_update():
    """Keep yt-dlp fresh (sites change often). Runs at most once a day; applies on next launch."""
    uv = os.environ.get("VD_UV")
    stamp = Path(os.environ.get("VD_SUPPORT", APP_DIR)) / ".last-update"
    try:
        if not uv or (stamp.exists() and time.time() - stamp.stat().st_mtime < 86400):
            return
        r = subprocess.run([uv, "pip", "install", "-q", "-U", "--python", sys.executable, "yt-dlp[default]", "deno", "gallery-dl"],
                           capture_output=True, text=True, timeout=600)
        if r.returncode == 0:
            stamp.touch()
        else:
            print("update failed:", r.stderr[-500:])
    except Exception as e:  # noqa: BLE001
        print("update error:", e)


def set_mac_identity():
    """Show the app's own name and icon in the Dock / menu bar."""
    try:
        from Foundation import NSBundle
        from AppKit import NSApplication, NSImage
        info = NSBundle.mainBundle().localizedInfoDictionary() or NSBundle.mainBundle().infoDictionary()
        if info is not None:
            info["CFBundleName"] = "Video Downloader"
        icon = NSImage.alloc().initWithContentsOfFile_(str(APP_DIR / "icon.png"))
        if icon:
            NSApplication.sharedApplication().setApplicationIconImage_(icon)
    except Exception as e:  # noqa: BLE001
        print("identity:", e)


class WindowApi:
    def clipboard(self):
        try:
            from AppKit import NSPasteboard, NSPasteboardTypeString
            return NSPasteboard.generalPasteboard().stringForType_(NSPasteboardTypeString) or ""
        except Exception:  # noqa: BLE001
            return ""


def main():
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    threading.Thread(target=background_update, daemon=True).start()
    window_mode = "--window" in sys.argv
    webview = None
    if window_mode:
        try:
            import webview  # pywebview
        except Exception as e:  # noqa: BLE001
            print("pywebview unavailable, using browser:", e)
            webview = None
    port = 0 if webview else PORT
    try:
        server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    except OSError:
        print(f"Already running -> opening http://127.0.0.1:{PORT}")
        webbrowser.open(f"http://127.0.0.1:{PORT}")
        return
    url = f"http://127.0.0.1:{server.server_address[1]}"
    print(f"Video Downloader running -> {url}  |  saving to {DOWNLOAD_DIR}")
    if webview:
        threading.Thread(target=server.serve_forever, daemon=True).start()
        set_mac_identity()
        webview.create_window("Video Downloader", url, width=960, height=840, min_size=(720, 620),
                              background_color="#0d0f12", js_api=WindowApi(), text_select=True)
        webview.start()
        os._exit(0)
    if not os.environ.get("VD_NO_BROWSER"):
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
