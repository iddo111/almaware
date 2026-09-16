#!/usr/bin/env python3
"""Cut the 4K shots into the film and burn the AI disclosure into every frame.

One ffmpeg pass does the whole timeline: concat -> inset crop -> 4K rescale ->
disclosure overlay -> score.  The overlay is applied to the CONCATENATED stream,
cards included, so there is no code path here that emits a frame without the
disclosure on it.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import shots as S

HERE = Path(__file__).parent
FILM = HERE.parent
CLIPS = FILM / "clips4k"
OUT = FILM / "ALMIDO-otiyot-ratsot-4K.mp4"
POSTER = FILM / "ALMIDO-otiyot-ratsot-4K.jpg"
W, H, FPS = 3840, 2160, 24
HEAD_S, TAIL_S = 7.0, 8.0


def run(cmd: list[str]) -> None:
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode:
        print(" ".join(cmd[:12]), "...\n", p.stderr[-4000:], file=sys.stderr)
        raise SystemExit(f"ffmpeg failed ({p.returncode})")


def probe(path: Path) -> dict:
    p = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height,r_frame_rate,nb_frames,codec_name,pix_fmt",
         "-show_entries", "format=duration,size", "-of", "json", str(path)],
        capture_output=True, text=True)
    return json.loads(p.stdout or "{}")


def duration(path: Path) -> float:
    return float(probe(path).get("format", {}).get("duration", 0) or 0)


def card_video(png: Path, seconds: float, dest: Path) -> Path:
    run(["ffmpeg", "-y", "-loop", "1", "-framerate", str(FPS), "-i", str(png),
         "-t", f"{seconds}", "-vf",
         f"scale={W}:{H},format=yuv420p,fade=t=in:st=0:d=1.0,"
         f"fade=t=out:st={seconds-1.0}:d=1.0",
         "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-r", str(FPS),
         "-an", str(dest)])
    return dest


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", default=str(HERE / "score_almido.wav"))
    ap.add_argument("--inset", type=float, default=0.05,
                    help="fraction cropped from each edge before the 4K rescale")
    a = ap.parse_args()

    work = HERE / "work"
    work.mkdir(exist_ok=True)
    strip = HERE / "overlays" / "disclosure_strip.png"
    if not strip.exists():
        raise SystemExit("disclosure strip missing — refusing to build the film")

    missing = [i for i in S.ALL_IDS if not (CLIPS / f"{i}.mp4").exists()]
    if missing:
        raise SystemExit(f"missing 4K clips: {missing}")

    head = card_video(HERE / "overlays" / "card_head.png", HEAD_S, work / "head.mp4")
    tail = card_video(HERE / "overlays" / "card_tail.png", TAIL_S, work / "tail.mp4")

    parts = [head] + [CLIPS / f"{i}.mp4" for i in S.ALL_IDS] + [tail]
    total = sum(duration(p) for p in parts)
    print(f"  timeline {total:.2f}s over {len(parts)} parts")

    ins = a.inset
    # The inset crop is a safety net, not a look: LTX stamps invented station
    # bugs and chyrons into the extreme corners and at cfg 1.0 there is no
    # working negative prompt to forbid them. Anything within `ins` of an edge
    # simply is not in the delivered frame.
    crop = (f"crop=iw*{1-2*ins:.4f}:ih*{1-2*ins:.4f}:iw*{ins:.4f}:ih*{ins:.4f},"
            f"scale={W}:{H}:flags=lanczos,setsar=1,fps={FPS},format=yuv420p")

    cmd = ["ffmpeg", "-y"]
    for p in parts:
        cmd += ["-i", str(p)]
    cmd += ["-i", str(strip), "-i", a.audio]
    strip_idx, audio_idx = len(parts), len(parts) + 1

    fc = "".join(f"[{i}:v]{crop}[c{i}];" for i in range(len(parts)))
    fc += "".join(f"[c{i}]" for i in range(len(parts)))
    fc += f"concat=n={len(parts)}:v=1:a=0[body];"
    fc += f"[body][{strip_idx}:v]overlay=0:0:format=auto[v];"
    fc += (f"[{audio_idx}:a]atrim=0:{total:.3f},asetpts=N/SR/TB,"
           f"afade=t=in:st=0:d=3,afade=t=out:st={max(0.1, total-5):.3f}:d=5,"
           "volume=0.8[a]")

    cmd += ["-filter_complex", fc, "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-preset", "slow", "-crf", "17",
            "-pix_fmt", "yuv420p", "-r", str(FPS),
            "-c:a", "aac", "-b:a", "192k", "-shortest",
            "-movflags", "+faststart", str(OUT)]
    run(cmd)

    # poster: a real frame OF THE FINISHED FILM, so it carries the disclosure too
    run(["ffmpeg", "-y", "-ss", "30.0", "-i", str(OUT), "-frames:v", "1",
         "-q:v", "2", str(POSTER)])

    print(json.dumps(probe(OUT), indent=2))


if __name__ == "__main__":
    main()
