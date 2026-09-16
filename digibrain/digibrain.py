#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""digibrain -- alma neuronic digibrain, project 2 (standalone).

NOT vipassana. A network from scratch whose every stochastic breath
comes from onboard DGX hardware entropy (ARM SMCCC TRNG + TPM RNG
via the kernel, read with os.getrandom GRND_RANDOM; audited), and
trained Targ-style: trial -> guess -> immediate feedback -> weight
update, exactly how Targ trained human viewers (guess the hidden
target, get shown the truth at once). The task is predicting the
next hardware bit -- provably unpredictable, so the z-score is
honest: sustained deviation from chance MEANS something.

Runs on eran1. Stdlib + torch (box torch, no installs).
Run:   python3 ~/digibrain/digibrain.py
Watch: state.json + dash.py :8894
Stop:  touch ~/digibrain/STOP
"""
import math
import os
import time

APP = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(APP, "state.json")
STOP = os.path.join(APP, "STOP")

HIST_BITS = 16
HIDDEN = 32
LR = 1e-3
HW_BYTES_USED = {"n": 0}

# ----------------------------------------------------------------------------
# Hardware entropy. GRND_RANDOM pulls from the blocking pool fed by the
# onboard TRNG (smccc_trng + tpm-rng-0, measured 2026-09-14). Falls back
# to os.urandom (same kernel CSPRNG). Every byte is counted for audit.
# ----------------------------------------------------------------------------
def hw_bytes(n):
    try:
        b = os.getrandom(n, os.GRND_RANDOM)
        src = "grnd_random"
    except Exception:
        b = os.urandom(n)
        src = "urandom-fallback"
    HW_BYTES_USED["n"] += n
    return b, src


def hw_bits(n):
    b, src = hw_bytes((n + 7) // 8)
    val = int.from_bytes(b, "big")
    return [(val >> i) & 1 for i in range(n)], src


def hw_float():
    b, src = hw_bytes(8)
    return int.from_bytes(b, "big") / 256.0**8, src


def zscore(hits, n, p=0.5):
    if n <= 0:
        return 0.0
    return (hits - n * p) / math.sqrt(n * p * (1 - p))


ZENER = ["circle", "cross", "waves", "square", "star"]
BOXES = [("sun", "#c8792f"), ("mountain", "#5b7fa6"),
         ("water", "#3f7d6b"), ("tree", "#6b8f3e")]
DECK = 25
MILESTONE = 11
MILE_LOG = os.path.join(APP, "milestones.log")

import torch
import torch.nn as nn

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


class Digibrain(nn.Module):
    def __init__(self, hist=HIST_BITS, hid=HIDDEN, syms=len(BOXES)):
        super().__init__()
        self.fc1 = nn.Linear(hist + 8, hid)
        self.fc2 = nn.Linear(hid, hid // 2)
        self.out = nn.Linear(hid // 2, syms)

    def forward(self, x):
        x = torch.tanh(self.fc1(x))
        x = torch.tanh(self.fc2(x))
        return self.out(x).squeeze(-1)


def hw_init(net):
    """Init weights from hardware bytes, never PRNG."""
    with torch.no_grad():
        for p in net.parameters():
            n = p.numel()
            b, _ = hw_bytes(n * 4)
            vals = [int.from_bytes(b[i:i + 4], "big") / 2.0**32
                    * 2 - 1 for i in range(0, n * 4, 4)]
            p.copy_(torch.tensor(vals, dtype=p.dtype).view(p.shape)
                    * math.sqrt(1.0 / max(1, p.shape[0])))


def hw_dropout_mask(n, p=0.1):
    bits, _ = hw_bits(n)
    thresh = int(p * 256)
    raw, _ = hw_bytes(n)
    return torch.tensor([0.0 if v < thresh else 1.0 / (1 - p)
                         for v in raw])

# ----------------------------------------------------------------------------
# Targ loop: trial -> guess -> reveal -> feedback update.
# ----------------------------------------------------------------------------
def write_state(round_no, hits, n, z, last, history, src,
                best_deck=0):
    st = {"round": round_no, "hits": hits, "n": n,
          "hit_rate": round(hits / max(1, n), 4), "z": round(z, 3),
          "best_deck": best_deck, "chance": 0.25,
          "last": last, "hw_bytes": HW_BYTES_USED["n"],
          "hw_src": src, "device": DEVICE,
          "ts": time.strftime("%H:%M:%S"), "history": history[-80:]}
    tmp = STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json_out = __import__("json")
        json_out.dump(st, f)
    os.replace(tmp, STATE)


def main():
    import json  # noqa
    net = Digibrain().to(DEVICE)
    hw_init(net)  # born of silicon, not seed
    opt = torch.optim.Adam(net.parameters(), lr=LR)
    lossf = torch.nn.CrossEntropyLoss()
    hist_syms = [0] * HIST_BITS
    hits = n = 0
    deck_hits = 0
    best_deck = 0
    history = []
    rnd = 0
    src = "grnd_random"
    print("digibrain: HW-born 4-box Targ trainer, device %s" % DEVICE,
          flush=True)
    while not os.path.isfile(STOP):
        rnd += 1
        # guess from trial history (one-hot last symbols) + HW noise
        oh = [0.0] * HIST_BITS
        for i, s in enumerate(hist_syms[-4:]):
            oh[i * 4 + s] = 1.0 if i * 4 + s < HIST_BITS else 0.0
        noise, src = hw_bytes(8)
        nvec = [b / 255.0 for b in noise]
        x = torch.tensor([oh + nvec], dtype=torch.float32,
                         device=DEVICE)
        net.eval()
        with torch.no_grad():
            guess = int(net(x).argmax())
        # reveal: hidden picture box, drawn from hardware
        tb, src = hw_bytes(1)
        truth = tb[0] % 4
        hit = int(guess == truth)
        hits += hit
        n += 1
        deck_hits += hit
        # immediate feedback: one Targ-style weight update
        net.train()
        opt.zero_grad()
        y = torch.tensor([truth], device=DEVICE)
        loss = lossf(net(x), y)
        loss.backward()
        opt.step()
        hist_syms = (hist_syms + [truth])[-HIST_BITS:]
        z = zscore(hits, n, 0.25)
        last = {"guess": BOXES[guess][0], "truth": BOXES[truth][0],
                "hit": hit, "loss": round(loss.item(), 4)}
        history.append({"r": rnd, "z": round(z, 3),
                        "rate": round(hits / n, 3)})
        if rnd % DECK == 0:
            if deck_hits >= MILESTONE:
                with open(MILE_LOG, "a", encoding="utf-8") as f:
                    f.write("MILESTONE deck %d: %d/25 z=%.2f\n"
                            % (rnd // DECK, deck_hits, z))
            best_deck = max(best_deck, deck_hits)
            deck_hits = 0
        write_state(rnd, hits, n, z, last, history, src, best_deck)
        if rnd % 100 == 0:
            print("round %d hits=%d/%d rate=%.3f z=%.2f bestdeck=%d "
                  "hw=%dB(%s)"
                  % (rnd, hits, n, hits / n, z, best_deck,
                     HW_BYTES_USED["n"], src), flush=True)
    print("stopped.")


def selftest():
    assert abs(zscore(60, 100) - 2.0) < 1e-9, zscore(60, 100)
    assert zscore(50, 100) == 0.0
    assert zscore(0, 0) == 0.0
    assert len(BOXES) == 4
    assert abs(zscore(11, 25, 0.25) - 2.19) < 0.05, zscore(11, 25, 0.25)
    b, src = hw_bytes(16)
    assert len(b) == 16 and src in ("grnd_random", "urandom-fallback")
    bits, _ = hw_bits(10)
    assert len(bits) == 10 and set(bits) <= {0, 1}
    f, _ = hw_float()
    assert 0.0 <= f < 1.0
    print("SELFTEST-OK z=2.0 hw=%s" % src)


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        selftest()
    else:
        main()
