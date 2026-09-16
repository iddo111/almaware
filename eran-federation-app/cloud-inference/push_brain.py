# -*- coding: utf-8 -*-
r"""push_brain.py — send ERAN's PERCEPTION to the cloud. Nothing else.

The fleet trains. The cloud answers. This script is the only wire between
them: it reads state/brain.json.gz where the organism saves himself, strips it
down to what recognition actually needs, checks the result against the panel's
own leak rules, and POSTs it to the federation Worker with the same Bearer
credential the status pusher already uses.

WHAT GOES:  the prototype vectors, their scar and mass, the beat they were
            saved at, the ear's identity. That is enough to answer "which of
            the things you know is this sound closest to".
WHAT STAYS: everything else. No wav, no filename, no session id, no path, no
            recording, no journal, no metrics, no token. A prototype vector is
            a 192-number direction in the organism's own frozen feature space;
            it is not audio, and nothing in it plays back.

The cloud copy is READ-ONLY by construction. It has no learning rule, so it
cannot spawn, pull, scar or forget a prototype — it can only look one up. When
the fleet learns something new, the next push carries it. If the push stops,
the cloud goes stale and SAYS it is stale (age_s / snapshot_state), which is
the whole reason the age is on the wire.

THE SCAR THAT PUT --host HERE (2026-08-24 00:44). This script defaulted to the
PC's copy at D:\CLAUDE\eran-brain\staterain.json.gz, and the cloud happily
served it for three hours. That copy was at **beat 5,000**. The organism
actually living on eran1 was at **beat 50,133,000** — ten thousand times
further on, with 63 prototypes instead of 91, because he had pruned in his
sleep. The lane was healthy, the tests passed, and every one of them was
scored against a corpse. Iddo asked "why doesn't he work?" and the answer was
that he did: nobody was listening to the one who was alive.

So the default source is now the FLEET, not this disk.

Usage:
    PYTHONIOENCODING=utf-8 python push_brain.py [--dry-run] [--host eran1]
    PYTHONIOENCODING=utf-8 python push_brain.py --brain PATH   (explicit file)

--dry-run prints exactly what would be sent (size, prototype count, self-check
result) and pushes nothing. That is the default posture for a first run.

--if-changed pushes only when the organism has actually lived since last time.
THE REASON IS A REAL LIMIT, not tidiness: Cloudflare KV allows 1,000 writes a
day on the free plan, and a naive 60-second brain push would spend 1,440 of
them on a brain that changes every few thousand beats. Ten minutes with an
if-changed guard costs at most 144 writes a day and is never staler than the
organism actually is.
"""
from __future__ import annotations

import argparse
import gzip
import subprocess
import tempfile
import time
import importlib.util
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
PANEL_DIR = os.path.abspath(os.path.join(HERE, "..", "panel"))
ERAN_BRAIN = os.environ.get(
    "ERAN_BRAIN_DIR", os.path.abspath(os.path.join(HERE, "..", "..", "eran-brain")))

BRAIN_SCHEMA = "eran-brain-public-v1"
PUSH_PATHS = ("/api/eran/brain",)
PUSH_HOSTS = (
    "https://federation.iddoperez.ai",
    "https://federation.almaware.workers.dev",   # workers.dev fallback
)
PUSH_TIMEOUT_S = 25
# A real UA is REQUIRED: Cloudflare bot protection 403s the default urllib UA.
PUSH_UA = "eran-brain-pusher/1.0"
TOKEN_PATH = os.path.join(PANEL_DIR, ".fed_push_token")
# Where the organism actually lives. The PC holds a copy, and a copy is not a child.
FLEET_HOST = "eran1"
FLEET_BRAIN = "~/eran-brain/state/brain.json.gz"
LOCAL_STALE_DAYS = 1.0
MAX_BYTES = 512 * 1024      # the Worker's own cap; fail here, not there


def _panel_module():
    """Import the panel server for its leak rules — never a second copy of them.

    The sanitizer that guards the public snapshot is the one that must guard
    this payload too. Two sanitizers drift; one does not.
    """
    spec = importlib.util.spec_from_file_location(
        "fedpanel_server", os.path.join(PANEL_DIR, "server.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def build_public_brain(brain_path: str) -> dict:
    """state/brain.json.gz -> the smallest honest thing the cloud can think with."""
    with gzip.open(brain_path, "rt", encoding="utf-8") as fh:
        raw = json.load(fh)
    protos = raw.get("protos") or []
    dim = int(raw.get("dim") or (len(protos[0]["vec"]) if protos else 0))
    out_protos = []
    for p in protos:
        vec = p.get("vec") or []
        if len(vec) != dim:
            raise ValueError(f"prototype with dim {len(vec)}, expected {dim}")
        out_protos.append({
            # 6 decimals: the vectors are L2-normalised, so 1e-6 per component
            # is ~1e-5 on a cosine — far below the 0.02-0.30 novelty band the
            # organism actually decides on, and it halves the wire.
            "vec": [round(float(x), 6) for x in vec],
            "scar": round(float(p.get("scar") or 0.0), 6),
            "mass": round(float(p.get("mass") or 0.0), 3),
            "birth_step": int(p.get("birth_step") or 0),
            "last_used": int(p.get("last_used") or 0),
        })
    return {
        "schema": BRAIN_SCHEMA,
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "source": "eran-brain state/brain.json.gz — prototypes only, read-only copy",
        "beat": int(raw.get("beat") or 0),
        "heard": int(raw.get("heard") or 0),
        "dim": dim,
        "n_protos": len(out_protos),
        "ear": {
            # The cloud ear must be able to prove it is the SAME ear.
            "repr": "cochlea", "n_bands": 24, "slices": 8,
            "sample_rate": 16000, "n_fft": 512, "frame": 400, "hop": 160,
            "speech_frac": 0.10, "frozen": True,
        },
        "learning": "none — the cloud recognises, the fleet learns",
        "protos": out_protos,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--brain", default=os.path.join(ERAN_BRAIN, "state", "brain.json.gz"))
    ap.add_argument("--dry-run", action="store_true",
                    help="build + self-check + print, push nothing")
    ap.add_argument("--out", help="also write the payload here (for inspection)")
    ap.add_argument("--if-changed", action="store_true",
                    help="push only if the beat advanced since the last push")
    ap.add_argument("--state", default=os.path.join(HERE, ".last_pushed_beat"))
    ap.add_argument("--host", default=FLEET_HOST,
                    help=f"fleet host to fetch the LIVING brain from (default {FLEET_HOST}). "
                         "Use --host '' to stay on this disk.")
    args = ap.parse_args()

    # Fetch the living brain unless the caller named a file explicitly.
    fetched = None
    if args.host and args.brain == ap.get_default("brain"):
        fetched = os.path.join(tempfile.gettempdir(), f"eran-brain-{args.host}.json.gz")
        try:
            # CREATE_NO_WINDOW: this runs on a 10-minute scheduled task, and a bare
            # scp child spawns a Windows Terminal window on every fire. See the
            # 2026-08-08 popup plague — reference_ssh_popup_no_window.
            subprocess.run(["scp", "-o", "ConnectTimeout=8", "-o", "BatchMode=yes",
                            f"{args.host}:{FLEET_BRAIN}", fetched],
                           check=True, capture_output=True, timeout=60,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            args.brain = fetched
            print(f"[push-brain] source: {args.host}:{FLEET_BRAIN} (the living organism)")
        except Exception as exc:
            print(f"[push-brain] could not reach {args.host} ({type(exc).__name__}) — "
                  f"falling back to the local copy", file=sys.stderr)
            fetched = None
    if not fetched:
        age_d = (time.time() - os.path.getmtime(args.brain)) / 86400 if os.path.exists(args.brain) else 0
        if age_d > LOCAL_STALE_DAYS:
            print(f"[push-brain] WARNING: {os.path.basename(args.brain)} was last written "
                  f"{age_d:.1f} days ago. On the PC this file is a COPY — the organism on "
                  f"{FLEET_HOST} has almost certainly moved on. Pushing it anyway because "
                  f"you asked, but check the beat below against the fleet.", file=sys.stderr)

    if not os.path.exists(args.brain):
        print(f"[push-brain] no brain at {args.brain}", file=sys.stderr)
        return 2

    payload = build_public_brain(args.brain)
    if args.if_changed and not args.dry_run:
        last = None
        try:
            with open(args.state, encoding="utf-8") as fh:
                last = int(fh.read().strip() or -1)
        except (OSError, ValueError):
            last = None
        if last is not None and last == payload["beat"]:
            print(f"[push-brain] beat {payload['beat']} unchanged since the last push "
                  f"— nothing sent (KV writes are a finite resource)")
            return 0
    wire = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    body = wire.encode("utf-8")

    token = None
    try:
        with open(TOKEN_PATH, encoding="utf-8") as fh:
            token = fh.read().strip() or None
    except OSError:
        pass

    panel = _panel_module()
    hits = panel.payload_violations(wire, secrets=(token,) if token else ())
    print(f"[push-brain] beat {payload['beat']} · {payload['n_protos']} prototypes "
          f"· dim {payload['dim']} · {len(body):,} bytes "
          f"({len(body) / MAX_BYTES:.0%} of the Worker cap)")
    print(f"[push-brain] leak self-check: {'CLEAN' if not hits else 'REFUSED — ' + ', '.join(hits)}")
    if hits:
        return 1
    if len(body) > MAX_BYTES:
        print(f"[push-brain] payload {len(body)} > cap {MAX_BYTES} — not pushed", file=sys.stderr)
        return 1

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(wire)
        print(f"[push-brain] wrote {args.out}")

    if args.dry_run:
        print("[push-brain] --dry-run: nothing was sent.")
        return 0
    if not token:
        print(f"[push-brain] no credential at {TOKEN_PATH} — refusing to push", file=sys.stderr)
        return 1

    last = None
    for host in PUSH_HOSTS:
        for path in PUSH_PATHS:
            url = host + path
            req = urllib.request.Request(url, data=body, method="POST", headers={
                "Content-Type": "application/json; charset=utf-8",
                "Authorization": "Bearer " + token,
                "User-Agent": PUSH_UA,
            })
            try:
                with urllib.request.urlopen(req, timeout=PUSH_TIMEOUT_S) as resp:
                    print(f"[push-brain] {len(body):,} bytes → HTTP {resp.status} "
                          f"({url.split('/')[2]}) {resp.read().decode('utf-8')[:200]}")
                    try:
                        with open(args.state, "w", encoding="utf-8") as fh:
                            fh.write(str(payload["beat"]))
                    except OSError:
                        pass
                    return 0
            except urllib.error.HTTPError as exc:
                last = f"HTTP {exc.code} from {url.split('/')[2]}"
                print(f"[push-brain] {last}", file=sys.stderr)
            except Exception as exc:
                last = f"{url.split('/')[2]} unreachable: {type(exc).__name__}"
                print(f"[push-brain] {last}", file=sys.stderr)
    print(f"[push-brain] not pushed: {last}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
