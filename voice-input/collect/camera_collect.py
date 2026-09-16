#!/usr/bin/env python3
"""
camera_collect.py - 24/7 camera frame capture for future multimodal Eran.

Companion to the always-on Hebrew mic (which logs voice 24/7 to
voice-input\\profiles\\iddo1\\samples.jsonl). This grabs a still frame from an
available camera every N seconds into a dated media store, with a manifest,
so that when a real webcam is plugged in we already have a passive visual
stream to pair with the voice stream.

DESIGN CONTRACT (do not break the locked mic):
  - This is a NEW, standalone file. It does NOT import, touch, or write into
    voice_input.py / supervisor.py / mic.py / ui_toggle.py / config.json, and
    it NEVER writes into profiles\\iddo1\\samples.jsonl. It only reads the
    camera and writes under collect\\media\\.
  - Privacy-aware: owner's own machine, 100% local. Nothing is uploaded.
    A capture can be paused at any moment by creating a file named PAUSE in
    the collect\\ folder (see --pause-file). Delete it to resume.

HONEST CAMERA CAVEAT (2026-06-17):
  This PC currently has NO real webcam. The only enumerated camera is the
  "Windows Virtual Camera Device" (a SoftwareDevice). cv2 index 0 *opens* and
  returns frames, but those frames are all-black (mean=std=min=max=0). This
  script therefore:
    * detects cameras and tries to open them,
    * inspects each frame and classifies an all-zero / zero-variance frame as
      a "blank/virtual" source,
    * by default SKIPS writing blank frames (so we don't fill the disk with
      black images), while still recording the attempt in the manifest,
    * is ready to capture real frames the moment a physical webcam is plugged
      in (no code change needed).

Backend: uses OpenCV (cv2) if available. If cv2 is missing it prints an honest
note pointing at the fallback (`pip install opencv-python-headless`); there is
no still-frame fallback via sounddevice/mss because mss only captures the
SCREEN (not a camera) and sounddevice is audio-only -- capturing the screen
would be a different, privacy-heavier feature and is intentionally not done
silently here.

Usage:
  python camera_collect.py                 # run forever, 30s interval
  python camera_collect.py --interval 60   # every 60s
  python camera_collect.py --once          # single capture then exit (verify)
  python camera_collect.py --probe         # detect cameras, print, exit
  python camera_collect.py --keep-blank    # also save blank/virtual frames
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import signal
import sys
import time
from pathlib import Path

# --- paths -----------------------------------------------------------------
HERE = Path(__file__).resolve().parent          # ...\voice-input\collect
MEDIA_ROOT = HERE / "media"                      # ...\collect\media
LOG_PATH = HERE / "camera_collect.log"
DEFAULT_PAUSE_FILE = HERE / "PAUSE"

# --- optional dependency ---------------------------------------------------
try:
    import cv2  # type: ignore
    HAVE_CV2 = True
except Exception:  # pragma: no cover
    cv2 = None
    HAVE_CV2 = False

_STOP = False


def _log(msg: str) -> None:
    line = f"{dt.datetime.now().isoformat(timespec='seconds')}  {msg}"
    print(line, flush=True)
    try:
        with LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:
        pass


def _handle_sig(signum, frame):  # noqa: ARG001
    global _STOP
    _STOP = True
    _log(f"signal {signum} received -> stopping after current frame")


# --- camera detection ------------------------------------------------------
def probe_cameras(max_index: int = 6):
    """Return list of dicts describing openable camera indices and a verdict.

    verdict per index: 'real' (frame has variance), 'blank' (all-zero/flat),
    'unreadable' (opened but no frame).
    """
    results = []
    if not HAVE_CV2:
        return results
    # CAP_DSHOW is the reliable backend on Windows; fall back to default.
    backends = []
    if hasattr(cv2, "CAP_DSHOW"):
        backends.append(cv2.CAP_DSHOW)
    backends.append(0)  # default/auto
    seen = set()
    for idx in range(max_index):
        for backend in backends:
            try:
                cap = cv2.VideoCapture(idx, backend)
            except Exception:
                continue
            if not cap.isOpened():
                cap.release()
                continue
            ok, frame = cap.read()
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) if cap else 0
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) if cap else 0
            cap.release()
            if idx in seen:
                break
            seen.add(idx)
            if not ok or frame is None:
                results.append({"index": idx, "verdict": "unreadable",
                                 "width": w, "height": h})
                break
            verdict = classify_frame(frame)
            results.append({
                "index": idx,
                "verdict": verdict,
                "width": int(frame.shape[1]),
                "height": int(frame.shape[0]),
            })
            break  # one working backend per index is enough
    return results


def classify_frame(frame) -> str:
    """'real' if the frame has real pixel variance, else 'blank'."""
    try:
        import numpy as np  # cv2 pulls numpy in
        f = np.asarray(frame)
        if f.size == 0:
            return "blank"
        # All-zero (virtual cam) or essentially flat -> blank.
        if float(f.std()) < 1.0 and float(f.max()) - float(f.min()) < 2:
            return "blank"
        return "real"
    except Exception:
        return "real"  # if we can't analyze, don't drop a possibly-real frame


# --- capture loop ----------------------------------------------------------
def open_first_camera(max_index: int = 6):
    """Open the first camera that yields a readable frame. Returns (cap, idx)."""
    if not HAVE_CV2:
        return None, -1
    backends = []
    if hasattr(cv2, "CAP_DSHOW"):
        backends.append(cv2.CAP_DSHOW)
    backends.append(0)
    for idx in range(max_index):
        for backend in backends:
            try:
                cap = cv2.VideoCapture(idx, backend)
            except Exception:
                continue
            if cap.isOpened():
                ok, frame = cap.read()
                if ok and frame is not None:
                    return cap, idx
            cap.release()
    return None, -1


def day_dir(now: dt.datetime) -> Path:
    d = MEDIA_ROOT / now.strftime("%Y-%m-%d")
    d.mkdir(parents=True, exist_ok=True)
    return d


def append_manifest(day: Path, record: dict) -> None:
    mpath = day / "manifest.jsonl"
    with mpath.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def capture_once(keep_blank: bool = False) -> dict:
    """Capture a single frame. Returns the manifest record."""
    now = dt.datetime.now()
    rec = {
        "ts": now.isoformat(timespec="seconds"),
        "saved": False,
        "file": None,
        "verdict": "no-camera",
        "camera_index": -1,
        "note": "",
    }
    if not HAVE_CV2:
        rec["verdict"] = "no-cv2"
        rec["note"] = ("OpenCV not installed; run "
                       "`pip install opencv-python-headless`")
        return rec

    cap, idx = open_first_camera()
    if cap is None:
        rec["note"] = "no openable camera detected"
        return rec
    try:
        ok, frame = cap.read()
    finally:
        cap.release()

    rec["camera_index"] = idx
    if not ok or frame is None:
        rec["verdict"] = "unreadable"
        rec["note"] = "camera opened but returned no frame"
        return rec

    verdict = classify_frame(frame)
    rec["verdict"] = verdict
    rec["width"] = int(frame.shape[1])
    rec["height"] = int(frame.shape[0])

    if verdict == "blank" and not keep_blank:
        rec["note"] = ("blank/virtual frame (likely Windows Virtual Camera "
                       "Device) - skipped; pass --keep-blank to save anyway")
        return rec

    day = day_dir(now)
    fname = now.strftime("%H-%M-%S") + (".blank.jpg" if verdict == "blank"
                                        else ".jpg")
    fpath = day / fname
    try:
        ok_w = cv2.imwrite(str(fpath), frame)
    except Exception as exc:  # pragma: no cover
        rec["note"] = f"imwrite failed: {exc}"
        return rec
    if ok_w:
        rec["saved"] = True
        rec["file"] = str(fpath)
        if verdict == "blank":
            rec["note"] = "blank frame saved (--keep-blank)"
    else:
        rec["note"] = "imwrite returned False"
    return rec


def run_loop(interval: float, keep_blank: bool, pause_file: Path) -> None:
    signal.signal(signal.SIGINT, _handle_sig)
    try:
        signal.signal(signal.SIGTERM, _handle_sig)
    except Exception:
        pass
    _log(f"camera_collect started | interval={interval}s | media={MEDIA_ROOT} "
         f"| cv2={'yes' if HAVE_CV2 else 'NO'}")
    cams = probe_cameras()
    _log(f"camera probe: {cams or 'none'}")
    if not any(c.get("verdict") == "real" for c in cams):
        _log("HONEST: no REAL camera found (only blank/virtual or none). "
             "Will keep trying every interval and capture for real once a "
             "physical webcam is plugged in.")
    while not _STOP:
        if pause_file.exists():
            _log("PAUSE file present -> skipping capture")
        else:
            rec = capture_once(keep_blank=keep_blank)
            day = day_dir(dt.datetime.now())
            append_manifest(day, rec)
            tag = "SAVED" if rec["saved"] else "skip"
            _log(f"{tag} verdict={rec['verdict']} "
                 f"idx={rec['camera_index']} {rec.get('note','')}".rstrip())
        # sleep in small slices so SIGTERM is responsive
        slept = 0.0
        while slept < interval and not _STOP:
            step = min(0.5, interval - slept)
            time.sleep(step)
            slept += step
    _log("camera_collect stopped")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="24/7 camera frame collector")
    ap.add_argument("--interval", type=float, default=30.0,
                    help="seconds between captures (default 30)")
    ap.add_argument("--once", action="store_true",
                    help="capture a single frame and exit (verify)")
    ap.add_argument("--probe", action="store_true",
                    help="detect cameras, print result, exit")
    ap.add_argument("--keep-blank", action="store_true",
                    help="also save blank/virtual-camera frames")
    ap.add_argument("--pause-file", default=str(DEFAULT_PAUSE_FILE),
                    help="path to a pause sentinel file")
    args = ap.parse_args(argv)

    MEDIA_ROOT.mkdir(parents=True, exist_ok=True)

    if args.probe:
        cams = probe_cameras()
        out = {
            "have_cv2": HAVE_CV2,
            "cameras": cams,
            "real_camera_present": any(c.get("verdict") == "real"
                                       for c in cams),
        }
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return 0

    if args.once:
        rec = capture_once(keep_blank=args.keep_blank)
        day = day_dir(dt.datetime.now())
        append_manifest(day, rec)
        print(json.dumps(rec, indent=2, ensure_ascii=False))
        return 0

    run_loop(args.interval, args.keep_blank, Path(args.pause_file))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
