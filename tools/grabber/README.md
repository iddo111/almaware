# Generic Media Grabber

One-command bulk downloader. Auto-routes any URL to the right backend:
- **yt-dlp** for video/audio (1500+ sites — YouTube, Vimeo, Bandcamp, archive.org, podcasts, lectures, news, etc.)
- **gallery-dl** for image galleries (DeviantArt, Pinterest, Tumblr, Flickr, ArtStation, Imgur, etc.)

iddoperez.ai

## Install state (already done)
- `yt-dlp 2026.03.17` ✓
- `gallery-dl 1.32.1` ✓
- Output dir: [D:\CLAUDE\tools\grabber\downloads\](file:///D:/CLAUDE/tools/grabber/downloads/) — one subfolder per source site.

## Usage

### Single URL (any supported site)
```cmd
D:\CLAUDE\tools\grabber\grab.cmd https://www.youtube.com/watch?v=dQw4w9WgXcQ
```

### Many URLs at once
```cmd
grab.cmd "https://archive.org/details/CC_500" "https://bandcamp.com/track/..." "https://vimeo.com/..."
```

### From a file (best for big lists — your band recordings, lecture series, etc.)
Drop URLs (one per line, `#` for comments) into `urls.txt`:
```
# Iddo's research talks
https://archive.org/details/some-lecture
https://www.youtube.com/playlist?list=...
# Bandcamp wishlist
https://bandcamp.com/track/...
```
Then:
```cmd
grab.cmd --list urls.txt --concurrent 3
```

### Audio-only (extract MP3 from any video)
```cmd
grab.cmd --audio-only https://www.youtube.com/watch?v=...
```
For an entire playlist:
```cmd
grab.cmd --audio-only "https://www.youtube.com/playlist?list=..."
```

### Force a specific backend
```cmd
grab.cmd --backend ytdlp https://some.site/...
grab.cmd --backend gallery https://www.deviantart.com/...
```

## What you get per download
- Best-quality video + audio merged
- Thumbnail embedded
- Metadata embedded (title, uploader, date, etc.)
- A `.info.json` next to each file (full source metadata)
- Resumable — re-running picks up where it stopped, won't re-download done files

## Where files land
[D:\CLAUDE\tools\grabber\downloads\](file:///D:/CLAUDE/tools/grabber/downloads/)
- `youtube.com/` — your YouTube content
- `vimeo.com/` — etc.
- `archive.org/` — public-domain video/audio
- `bandcamp.com/`
- `_gallery/` — gallery-dl output (organized into per-site sub-folders inside)

## Maintenance
yt-dlp publishes weekly. Refresh anytime:
```cmd
python -m pip install -U yt-dlp gallery-dl
```

## Common URL types it handles well
- YouTube videos, channels, playlists, shorts
- Vimeo
- Bandcamp tracks + entire discographies
- archive.org video/audio collections
- SoundCloud sets + likes
- Podcast RSS feeds (point at the .xml URL)
- TED talks, Coursera previews
- Twitch VODs (yt-dlp), Twitch live (use streamlink instead — `pip install streamlink`)
- Bulk gallery-dl: any DeviantArt artist, Pinterest board, Tumblr blog, Flickr album

## Limits / honesty
- Login-walled content needs `--cookies-from-browser firefox` (or chrome/edge). Add `--cookies-from-browser firefox` to the `grab.py` cmd list if you need this.
- Geographic blocks need a VPN in another tab.
- Live streams: use [streamlink](https://streamlink.github.io/) — different tool, simpler interface (`streamlink <url> best`).
