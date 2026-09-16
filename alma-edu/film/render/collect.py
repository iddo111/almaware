#!/usr/bin/env python3
"""Pull every finished 4K shot mp4 off the fleet into film/clips4k/ and check it."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import shots as S

CLIPS = Path(__file__).parent.parent / "clips4k"
NODES = ["eran1", "eran2"]


def sh(cmd: list[str]) -> str:
    return subprocess.run(cmd, capture_output=True, text=True).stdout


def main() -> None:
    CLIPS.mkdir(parents=True, exist_ok=True)
    have = set()
    for node in NODES:
        listing = sh(["ssh", "-o", "ConnectTimeout=20", node,
                      "ls ~/almido_4k/ 2>/dev/null"]).split()
        for f in listing:
            sid = f[:-4]
            if not f.endswith(".mp4") or sid in have:
                continue
            dest = CLIPS / f
            subprocess.run(["scp", "-q", f"{node}:~/almido_4k/{f}", str(dest)])
            have.add(sid)

    bad = []
    for sid in S.ALL_IDS:
        p = CLIPS / f"{sid}.mp4"
        if not p.exists():
            bad.append((sid, "MISSING"))
            continue
        out = sh(["ffprobe", "-v", "error", "-select_streams", "v:0",
                  "-show_entries", "stream=width,height,nb_frames",
                  "-show_entries", "format=duration", "-of", "json", str(p)])
        d = json.loads(out or "{}")
        st = (d.get("streams") or [{}])[0]
        dur = float(d.get("format", {}).get("duration", 0) or 0)
        ok = st.get("width") == 3840 and st.get("height") == 2160 and dur > 1.5
        print(f"  {sid}: {st.get('width')}x{st.get('height')} "
              f"{st.get('nb_frames')}f {dur:.2f}s {'ok' if ok else 'BAD'}")
        if not ok:
            bad.append((sid, f"{st.get('width')}x{st.get('height')} {dur:.2f}s"))

    if bad:
        print("\nNOT READY:", bad)
        sys.exit(1)
    print(f"\nall {len(S.ALL_IDS)} shots present at 3840x2160")


if __name__ == "__main__":
    main()
