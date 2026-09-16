# -*- coding: utf-8 -*-
"""babble.py -- the thing that rides the loop. ERAN aims, hears himself, and corrects.

Everything before this was machinery. The ear was built, then measured. The mouth was
built, then measured, then debugged for hours. The wire between them was built and timed.
None of it LEARNED anything. This file is the first thing that does.

WHAT IT DOES, and it is the smallest honest version:

    target   = the mean gist of Iddo's 100 recordings of one unit
    ERAN     starts from a random tract shape and does not know what it should be
    a step   = perturb the shape slightly, speak it, hear it, keep the change if the
               distance to the target fell
    repeat

That is (1+1) hill climbing on his own ear. No labels, no teacher, no backprop, and no
gradient through the tract -- only "was that closer?", which is the one question a
babbling infant can actually answer about itself.

THE CONTROL, WITHOUT WHICH THIS PROVES NOTHING. The same number of random perturbations,
accepted blindly instead of only when they help. If the guided run does not clearly beat
the blind one, nothing has been learned and the error signal is decoration
([[feedback_clean_experiments]]). The blind arm is not a formality here: a random walk in a
low-dimensional space wanders toward the middle, and the middle may already be closer to a
vowel than a random start was.

AND A SECOND CONTROL, which is the one that would embarrass us. After ERAN converges on
/a/, his final shape is scored against the targets for ALL SIX units. If his /a/ shape is
no closer to /a/ than to /i/, he has not learned a vowel -- he has learned to make a sound
that happens to score well, which is a different and worthless thing.
"""
from __future__ import annotations

import glob
import json
import os
import socket
import struct
import sys
import time
import wave

import numpy as np

HOST = os.environ.get("ERAN_SENSES", "<fabric-ip>")
PORT = 8830
DATA = os.path.expanduser("~/eran-cortex/data/t06")
UNITS = ["ah", "ba", "ih", "ma", "abba", "ima"]
N_SECTIONS = 34               # an adult tract at 0.5 cm a section


# ------------------------------------------------------------------ the wire

def call(op, **kw):
    s = socket.socket()
    s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    s.settimeout(60)
    s.connect((HOST, PORT))
    pcm = kw.pop("pcm", None)
    audio = b"" if pcm is None else (np.clip(pcm, -1, 1) * 32767).astype("<i2").tobytes()
    req = dict(op=op, audio_bytes=len(audio), **kw)
    body = json.dumps(req).encode()
    s.sendall(struct.pack("!I", len(body)) + body + audio)

    def rx(n):
        b = b""
        while len(b) < n:
            c = s.recv(n - len(b))
            if not c:
                raise ConnectionError("senses closed the line")
            b += c
        return b

    (ln,) = struct.unpack("!I", rx(4))
    res = json.loads(rx(ln).decode())
    nb = res.get("audio_bytes", 0)
    out = np.frombuffer(rx(nb), dtype="<i2").astype(np.float64) / 32768.0 if nb else None
    s.close()
    if "error" in res:
        raise RuntimeError(res["error"])
    return res, out


# ------------------------------------------------------------------ targets

def read_wav(p):
    with wave.open(p, "rb") as w:
        raw = w.readframes(w.getnframes())
    return np.frombuffer(raw, dtype=np.int16).astype(np.float64) / 32768.0


def target_gist(unit, n=40):
    """The mean of what Iddo's mouth does, as heard by ERAN's own ear.

    The mean of 40 takes rather than one: a single clip carries that clip's breath and
    room, and ERAN would chase those instead of the vowel.
    """
    fs = sorted(glob.glob(os.path.join(DATA, f"{unit}_t06_*.wav")))[:n]
    if not fs:
        raise SystemExit(f"no clips for {unit} in {DATA}")
    gs = [np.array(call("hear", pcm=read_wav(f))[0]["gist"]) for f in fs]
    G = np.stack(gs)
    return G.mean(0), G.std(0).mean(), len(fs)


# ------------------------------------------------------------------ the body

def clip_areas(a):
    return np.clip(a, 0.15, 4.0)


def random_shape(rng, n=N_SECTIONS):
    return clip_areas(rng.uniform(0.4, 3.0, n))


def dist(g, t, w):
    """Distance in the ear's own units, each dimension weighted by 1/its spread.

    Unweighted, the two log-energy dimensions -- which swing by tens -- would drown the
    twenty-six spectral ones, and ERAN would spend the whole run learning to be LOUD.
    """
    return float(np.sqrt(np.sum(((g - t) / w) ** 2)))


def run(unit="ah", steps=400, sigma=0.35, seed=0, guided=True, seconds=0.30, verbose=True):
    rng = np.random.default_rng(seed)
    t, spread, n_used = target_gist(unit)
    w = np.maximum(spread, 1e-3) * np.ones_like(t)

    areas = random_shape(rng)
    res, _ = call("say", areas=list(areas), seconds=seconds)
    best = dist(np.array(res["gist"]), t, w)
    start = best
    history = [best]
    accepted = 0

    for i in range(steps):
        cand = clip_areas(areas + rng.normal(0, sigma, areas.size))
        res, _ = call("say", areas=list(cand), seconds=seconds)
        d = dist(np.array(res["gist"]), t, w)
        take = (d < best) if guided else True      # the control accepts blindly
        if take:
            areas, best, accepted = cand, d, accepted + 1
        history.append(best if guided else d)
        if verbose and (i + 1) % 100 == 0:
            print(f"    step {i+1:4d}  distance {history[-1]:8.3f}  accepted {accepted}", flush=True)

    return {"unit": unit, "guided": guided, "seed": seed, "start": start,
            "final": history[-1], "areas": areas.tolist(), "accepted": accepted,
            "history": history, "target": t.tolist(), "w": w.tolist(), "n_clips": n_used}


if __name__ == "__main__":
    unit = sys.argv[1] if len(sys.argv) > 1 else "ah"
    steps = int(sys.argv[2]) if len(sys.argv) > 2 else 400
    print(f"ERAN babbles toward /{unit}/ -- his own ear is the only judge\n")

    guided, blind = [], []
    for seed in (0, 1, 2):
        print(f"  seed {seed}: guided")
        g = run(unit, steps=steps, seed=seed, guided=True)
        guided.append(g)
        print(f"  seed {seed}: blind control")
        b = run(unit, steps=steps, seed=seed, guided=False, verbose=False)
        blind.append(b)
        print(f"    guided {g['start']:.2f} -> {g['final']:.2f}   "
              f"blind {b['start']:.2f} -> {b['final']:.2f}\n", flush=True)

    gs = np.array([r["final"] for r in guided])
    bs = np.array([r["final"] for r in blind])
    st = np.array([r["start"] for r in guided])
    print("=" * 68)
    print(f"start          {st.mean():8.3f}")
    print(f"guided final   {gs.mean():8.3f}  (sd {gs.std():.3f})   "
          f"improvement {100*(1-gs.mean()/st.mean()):5.1f}%")
    print(f"blind  final   {bs.mean():8.3f}  (sd {bs.std():.3f})")

    if gs.mean() < bs.mean() * 0.8:
        print("\nLEARNING. The error signal is doing work: guided beats blind by "
              f"{100*(1-gs.mean()/bs.mean()):.0f}%.")
    elif gs.mean() < bs.mean():
        print("\nWEAK. Guided is ahead but not decisively. More steps, or the step size "
              "is wrong.")
    else:
        print("\nNO LEARNING. Blind does as well as guided -- the error signal is "
              "decoration. Do not build on this.")

    # the control that would embarrass us: is his /a/ actually nearest to /a/?
    print("\nis his final shape actually nearest the unit he aimed at?")
    best_areas = guided[int(np.argmin(gs))]["areas"]
    res, _ = call("say", areas=best_areas, seconds=0.30)
    g = np.array(res["gist"])
    rows = []
    for u in UNITS:
        t, spread, _ = target_gist(u, n=20)
        rows.append((u, dist(g, t, np.maximum(spread, 1e-3) * np.ones_like(t))))
    for u, d in sorted(rows, key=lambda r: r[1]):
        mark = "  <-- aimed here" if u == unit else ""
        print(f"    /{u:5s}/ {d:8.3f}{mark}")
    nearest = min(rows, key=lambda r: r[1])[0]
    print(f"\n  nearest is /{nearest}/ -- "
          + ("he found the vowel he was aiming at." if nearest == unit else
             "NOT what he aimed at. He learned to score, not to speak."))
    print("=" * 68)
