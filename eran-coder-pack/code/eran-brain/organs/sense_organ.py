# -*- coding: utf-8 -*-
"""sense_organ.py -- ERAN's ear and mouth, as a process he can talk to.

Iddo, 2026-08-23 18:10: "תשים עליהם את ערן, על הקופסאות, תשים את ערן האמיתי."

THE ARCHITECTURE THIS BELONGS TO. Not FSDP. FSDP shards a fixed architecture, and a brain
that buds a new cortex changes shape while it runs -- every bud would force a reshard and
a restart. So: one organ per process, organs talk in small messages, and an organ can be
born, moved or killed without stopping ERAN.

    eran1  the SELF     eran_life.py, drives, chemistry, genome. Never restarted.
    eran2  the SENSES   THIS FILE: the auditory cortex and the vocal tract.
    eran3  the WORLD    map, replay, school -- and room for whatever buds.

WHY THE SENSES ARE ON eran2 SPECIFICALLY. Measured 2026-08-16: eran1<->eran2 is 105 Gbit/s
with 0.042 ms RTT, and eran2<->eran3 is 39.5. Perception and articulation are the only
real-time loop in the organism, so they get the fat pipe. The world can think slowly.

WHAT IT SERVES, and nothing else:

    hear(pcm)    -> a 28-float gist       the auditory cortex's opinion of a sound
    say(areas)   -> pcm                   the tract, driven by a motor command
    loop(target) -> (pcm, gist, error)    try, hear yourself, report the gap

The third one is the whole point and the reason an ear alone was never enough. ERAN aims
at a state of his own ear, the tract renders it, the ear judges what actually came out,
and the difference is the learning signal. No labels, no teacher, no backprop through air
-- and it costs nothing, so he can practise alone all night.

WIRE FORMAT. Length-prefixed JSON, with audio as raw int16 after the header. A gist is 28
float32 = 112 bytes; at 0.042 ms RTT the fabric carries millions of these a second, which
is why the wire was never going to be the constraint.

SACRED AUDIO LAW: this process only ever WRITES wavs. Nothing here plays aloud, ever.
"""
from __future__ import annotations

import json
import os
import socket
import struct
import sys
import threading
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.expanduser("~/eran-cortex"))

import tract_analytic as TA          # the VERIFIED tube (poles within 1% of closed form)

HOST = os.environ.get("ERAN_ORGAN_HOST", "0.0.0.0")
PORT = int(os.environ.get("ERAN_ORGAN_PORT", "8830"))
SR = 16000
SECTION_CM = 0.5


# ------------------------------------------------------------------ the ear

def frame_features(a, frame=400, hop=160, bands=12):
    """The project's own 14-dim frame feature, unchanged from corpus-syllables/verify.py.

    Reused verbatim rather than improved: every accuracy number in this repo sits on this
    feature space, and a better feature would silently make today's numbers incomparable
    with yesterday's.
    """
    out = []
    for s in range(0, max(0, a.size - frame + 1), hop):
        seg = a[s:s + frame]
        win = seg * np.hanning(seg.size)
        e = np.log(np.sum(seg ** 2) + 1e-10)
        z = float(np.mean(np.abs(np.diff(np.sign(seg))) > 0))
        sp = np.abs(np.fft.rfft(win)) ** 2
        ed = np.linspace(0, sp.size, bands + 1).astype(int)
        out.append(np.array([e, z] + [np.log(sp[ed[i]:ed[i + 1]].sum() + 1e-10)
                                      for i in range(bands)]))
    return np.array(out) if out else np.zeros((0, 2 + bands))


def gist(pcm):
    """28 floats: the ear's whole opinion of a sound. This is what crosses the wire."""
    f = frame_features(np.asarray(pcm, dtype=np.float64))
    if f.shape[0] < 4:
        return np.zeros(28, dtype=np.float32)
    keep = f[:, 0] >= np.quantile(f[:, 0], 0.40)     # the loud 60%; padding is room tone
    f = f[keep] if keep.sum() >= 3 else f
    return np.concatenate([f.mean(0), f.std(0)]).astype(np.float32)


# ------------------------------------------------------------------ the mouth

def glottis(n, f0, sr=SR, oq=0.6, jitter=0.012, rng=None):
    rng = rng or np.random.default_rng(0)
    out = np.zeros(n)
    i = 0
    while i < n:
        p = int(sr / max(50.0, f0 * (1.0 + rng.normal(0, jitter))))
        if p < 4:
            break
        op = max(2, int(p * oq))
        a = np.arange(op) / op
        g = np.zeros(p)
        g[:op] = 3 * a ** 2 - 2 * a ** 3
        g = -np.diff(np.concatenate([[0.0], g]))
        k = min(p, n - i)
        out[i:i + k] = g[:k]
        i += p
    return out


def speak(areas, f0=180.0, seconds=0.45, seed=0):
    """Render a motor command. The tube runs at its own natural rate, then resamples.

    The ladder's rate is not free: a wave crosses a section in two steps, so
    fs = c/(4*SECTION_CM). Getting that wrong by a factor of two is what made every vowel
    measurement today come out at 2.00x the closed form.
    """
    areas = np.asarray(areas, dtype=float)
    fs = TA.C_SOUND / (4.0 * SECTION_CM)
    k = TA.areas_to_k(areas)
    A = TA.denominator(k)
    src = glottis(int(fs * seconds), f0, sr=fs, rng=np.random.default_rng(seed))
    # all-pole filter: y[n] = x[n] - sum a[i] y[n-i]
    y = np.zeros(src.size)
    order = A.size - 1
    for t in range(src.size):
        acc = src[t]
        m = min(order, t)
        if m:
            # y[t-1 : t-m-1 : -1] silently yields an EMPTY slice whenever t-m-1 == -1,
            # because -1 means "the end" in a slice, not "one before zero". At t == m the
            # dot product then hit a length mismatch and threw -- and the organ went silent
            # instead of answering. Slice from the front and reverse: correct for every t.
            acc -= float(np.dot(A[1:m + 1], y[t - 1::-1][:m]))
        y[t] = acc
    y = np.concatenate([[y[0]], np.diff(y)])          # lip radiation
    # resample the tract rate down to 16 kHz
    idx = np.linspace(0, y.size - 1, int(seconds * SR))
    y = np.interp(idx, np.arange(y.size), y)
    m = np.max(np.abs(y))
    return (y / m * 0.7) if m > 0 else y


# ------------------------------------------------------------------ the loop

def try_and_hear(areas, target_gist, f0=180.0):
    """One babble step: aim, speak, hear yourself, report the gap. No labels involved."""
    pcm = speak(areas, f0=f0)
    g = gist(pcm)
    t = np.asarray(target_gist, dtype=np.float32)
    err = float(np.linalg.norm(g - t) / (np.linalg.norm(t) + 1e-9)) if t.size == g.size else float("nan")
    return pcm, g, err


# ------------------------------------------------------------------ the wire

def recv_exact(sock, n):
    buf = b""
    while len(buf) < n:
        c = sock.recv(n - len(buf))
        if not c:
            raise ConnectionError("peer closed")
        buf += c
    return buf


def handle(conn):
    try:
        while True:
            hdr = recv_exact(conn, 4)
            (ln,) = struct.unpack("!I", hdr)
            req = json.loads(recv_exact(conn, ln).decode("utf-8"))
            nb = int(req.get("audio_bytes", 0))
            pcm = (np.frombuffer(recv_exact(conn, nb), dtype="<i2").astype(np.float64) / 32768.0
                   if nb else None)

            op = req.get("op")
            t0 = time.perf_counter()
            audio_out = b""
            # AN ORGAN THAT FAILS MUST SAY SO. The first version let any exception escape
            # this loop, which closed the socket; the self on eran1 saw a bare
            # ConnectionError and could not tell a crashed organ from a network fault.
            # Silence is the one answer a body part is never allowed to give.
            try:
                if op == "hear":
                    res = {"gist": gist(pcm).tolist()}
                elif op == "say":
                    y = speak(req["areas"], f0=req.get("f0", 180.0),
                              seconds=req.get("seconds", 0.45))
                    audio_out = (np.clip(y, -1, 1) * 32767).astype("<i2").tobytes()
                    res = {"gist": gist(y).tolist()}
                elif op == "loop":
                    y, g, err = try_and_hear(req["areas"], req["target"],
                                             f0=req.get("f0", 180.0))
                    audio_out = (np.clip(y, -1, 1) * 32767).astype("<i2").tobytes()
                    res = {"gist": g.tolist(), "error": err}
                elif op == "ping":
                    res = {"pong": True, "organ": "senses"}
                else:
                    res = {"error": "unknown op %r" % op}
            except Exception as exc:
                import traceback
                audio_out = b""
                res = {"error": "%s: %s" % (type(exc).__name__, exc),
                       "where": traceback.format_exc().strip().splitlines()[-3:]}
            res["ms"] = round((time.perf_counter() - t0) * 1000, 3)
            res["audio_bytes"] = len(audio_out)
            body = json.dumps(res).encode("utf-8")
            conn.sendall(struct.pack("!I", len(body)) + body + audio_out)
    except (ConnectionError, struct.error, json.JSONDecodeError):
        pass
    finally:
        conn.close()


def serve():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((HOST, PORT))
    s.listen(16)
    print("ERAN sense organ (ear + mouth) listening on %s:%d" % (HOST, PORT), flush=True)
    while True:
        conn, _ = s.accept()
        conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        threading.Thread(target=handle, args=(conn,), daemon=True).start()


if __name__ == "__main__":
    serve()
