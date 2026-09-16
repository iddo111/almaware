"""
Generic media grabber — auto-routes URLs to yt-dlp (video/audio) or gallery-dl (galleries).
Single URL, list of URLs, or a text file of URLs (one per line).

Usage:
    grab.py https://www.youtube.com/watch?v=...
    grab.py "https://archive.org/details/some-talk" "https://www.bandcamp.com/track/..."
    grab.py --list urls.txt
    grab.py --list urls.txt --concurrent 4
    grab.py --backend ytdlp https://example.com/video
    grab.py --audio-only https://www.youtube.com/playlist?list=...

Output: D:\\CLAUDE\\tools\\grabber\\downloads\\<site>\\<title>.<ext>
"""
from __future__ import annotations
import argparse
import concurrent.futures
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(r"D:\CLAUDE\tools\grabber")
OUT = ROOT / "downloads"
OUT.mkdir(parents=True, exist_ok=True)

# Backend hints — when in doubt, yt-dlp is the default (handles 1500+ sites).
GALLERY_DOMAINS = {
    "deviantart.com", "pinterest.com", "imgur.com", "tumblr.com",
    "flickr.com", "500px.com", "artstation.com", "behance.net",
    "instagram.com",  # gallery-dl handles photo posts better; yt-dlp handles reels
    "reddit.com",      # mixed; gallery-dl for image subs
    "twitter.com", "x.com",  # mixed; gallery-dl is usually better for images
}

YTDLP_DOMAINS = {
    "youtube.com", "youtu.be", "vimeo.com", "twitch.tv", "soundcloud.com",
    "bandcamp.com", "archive.org", "dailymotion.com", "tiktok.com",
    "facebook.com", "ted.com", "coursera.org", "udemy.com",
    "podcast", "rss", "anchor.fm", "spotify.com",
}


def domain_of(url: str) -> str:
    try:
        host = urlparse(url).hostname or ""
        return host.replace("www.", "").lower()
    except Exception:
        return ""


def pick_backend(url: str, override: str | None = None) -> str:
    if override in ("ytdlp", "gallery"):
        return override
    d = domain_of(url)
    if any(d.endswith(g) for g in GALLERY_DOMAINS):
        return "gallery"
    return "ytdlp"  # default


def grab_ytdlp(url: str, audio_only: bool = False) -> int:
    site_dir = OUT / (domain_of(url) or "misc")
    site_dir.mkdir(parents=True, exist_ok=True)
    out_template = str(site_dir / "%(title).200B [%(id)s].%(ext)s")
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "-o", out_template,
        "--no-overwrites",
        "--continue",
        "--retries", "10",
        "--fragment-retries", "10",
        "--ignore-errors",
        "--write-info-json",
        "--write-thumbnail",
        "--embed-metadata",
        "--embed-thumbnail",
        url,
    ]
    if audio_only:
        cmd[3:3] = ["-x", "--audio-format", "mp3", "--audio-quality", "0"]
    print(f"[ytdlp] {url}")
    return subprocess.call(cmd)


def grab_gallery(url: str) -> int:
    site_dir = OUT / "_gallery"
    site_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable, "-m", "gallery_dl",
        "-d", str(site_dir),
        "--write-metadata",
        url,
    ]
    print(f"[gallery] {url}")
    return subprocess.call(cmd)


def grab_one(url: str, backend: str | None, audio_only: bool) -> tuple[str, int]:
    url = url.strip()
    if not url or url.startswith("#"):
        return (url, 0)
    chosen = pick_backend(url, backend)
    if chosen == "gallery":
        return (url, grab_gallery(url))
    return (url, grab_ytdlp(url, audio_only=audio_only))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("urls", nargs="*", help="One or more URLs")
    ap.add_argument("--list", help="Path to a .txt file with one URL per line (# = comment)")
    ap.add_argument("--backend", choices=["ytdlp", "gallery"], help="Force a backend instead of auto-detect")
    ap.add_argument("--audio-only", action="store_true", help="yt-dlp: extract audio only (mp3 best quality)")
    ap.add_argument("--concurrent", type=int, default=1, help="Parallel downloads (default 1; be polite)")
    args = ap.parse_args()

    urls: list[str] = list(args.urls)
    if args.list:
        urls += [l.strip() for l in Path(args.list).read_text(encoding="utf-8").splitlines() if l.strip() and not l.strip().startswith("#")]
    if not urls:
        ap.print_help()
        sys.exit(2)

    print(f"== {len(urls)} URL(s), backend={args.backend or 'auto'}, parallel={args.concurrent}, output={OUT} ==")
    failures = []
    if args.concurrent <= 1:
        for u in urls:
            url, rc = grab_one(u, args.backend, args.audio_only)
            if rc != 0:
                failures.append((url, rc))
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrent) as ex:
            futs = [ex.submit(grab_one, u, args.backend, args.audio_only) for u in urls]
            for f in concurrent.futures.as_completed(futs):
                url, rc = f.result()
                if rc != 0:
                    failures.append((url, rc))

    print(f"\n== done. {len(urls) - len(failures)}/{len(urls)} succeeded. failures: {len(failures)} ==")
    for u, rc in failures:
        print(f"  rc={rc}  {u}")
    sys.exit(0 if not failures else 1)


if __name__ == "__main__":
    main()
