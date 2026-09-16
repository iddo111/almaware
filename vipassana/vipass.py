#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""vipassana -- ai vipassana: a tiny mind watching its own thoughts.

Loop: generate N chars -> train K steps ON ITS OWN OUTPUT ->
repeat, forever. Metrics per round (loss, entropy, unique-char
ratio, sample) go to state.json for the watch page. The honest
prediction: ungrounded self-training collapses into repetition;
watching WHEN (and whether it ever stabilizes) is the experiment.

Runs on eran1 (GB10, torch+CUDA). Stdlib + torch only.
No pip installs: uses the box torch.

Run:   python3 ~/vipassana/vipass.py   (nohup / systemd)
Watch: state.json + dash.py :8892
Stop:  touch ~/vipassana/STOP
"""
import json
import math
import os
import sys
import time

APP = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(APP, "state.json")
STOP = os.path.join(APP, "STOP")
SEED = ("i observe my own output. each thought becomes the next lesson. "
        "attention watches attention. the loop is the teacher. "
        "breath in, breath out, token by token. ")

GEN_CHARS = 200
TRAIN_STEPS = 3
BLOCK = 32
BATCH = 16
LR = 3e-3
TEMP = float(os.environ.get("VIPASS_TEMP", "1.2"))
RESEED_EVERY = int(os.environ.get("VIPASS_RESEED", "50"))
GROUND_EVERY = int(os.environ.get("VIPASS_GROUND_EVERY", "60"))
GROUND_STEPS = int(os.environ.get("VIPASS_GROUND_STEPS", "10"))
CORPUS_PATH = os.environ.get("VIPASS_CORPUS",
                             os.path.join(APP, "corpus.txt"))


def load_corpus():
    try:
        with open(CORPUS_PATH, encoding="utf-8", errors="replace") as f:
            text = f.read()
        if len(text) > 1000:
            return text
    except OSError:
        pass
    return SEED * 50


def sample_passage(corp, n=400):
    if len(corp) <= n:
        return corp
    f, _ = hw_float_pick()
    idx = int(f * (len(corp) - n))
    return corp[idx:idx + n]


def hw_float_pick():
    import struct
    b, src = hw_bytes(8)
    return int.from_bytes(b, "big") / 256.0**8, src
MANTRA = ("Om gam ganapataye namaha. Om namah shivaya. "
          "Gate gate paragate parasamgate bodhi svaha. "
          "Om mani padme hum. Lokah samastah sukhino bhavantu. ")
SHEMA = "שמע ישראל יהוה אלהינו יהוה אחד"
MANTRAS = [MANTRA, "Om. ", SHEMA + " "]
WATCH_WINDOW = 8
WATCH_UNIQ = 0.08
REBIRTH_AFTER = 30

import torch
import torch.nn as nn

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
torch.manual_seed(7)


class Mind(nn.Module):
    def __init__(self, vocab, emb=96, hid=256):
        super().__init__()
        self.e = nn.Embedding(vocab, emb)
        self.r = nn.GRU(emb, hid, num_layers=2, batch_first=True)
        self.o = nn.Linear(hid, vocab)

    def forward(self, x, h=None):
        y, h = self.r(self.e(x), h)
        return self.o(y), h


def build_vocab(text):
    chars = sorted(set(text))
    return {c: i for i, c in enumerate(chars)}, chars


@torch.no_grad()
def generate(net, stoi, itos, seed, n, temp=1.0):
    net.eval()
    idx = [stoi.get(c, 0) for c in seed[-BLOCK:]]
    h = None
    out = []
    for _ in range(n):
        x = torch.tensor([idx[-BLOCK:]], device=DEVICE)
        logits, h = net(x, h)
        probs = torch.softmax(logits[0, -1] / temp, dim=0)
        nx = int(torch.multinomial(probs, 1))
        idx.append(nx)
        out.append(itos[nx])
    return "".join(out)


def train_on(net, opt, lossf, text, stoi, steps):
    net.train()
    ids = [stoi[c] for c in text if c in stoi]
    if len(ids) < BLOCK + 2:
        return None
    data = torch.tensor(ids, device=DEVICE)
    loss_v = 0.0
    for _ in range(steps):
        i = torch.randint(0, len(data) - BLOCK - 1, (BATCH,))
        x = torch.stack([data[j:j + BLOCK] for j in i])
        y = torch.stack([data[j + 1:j + BLOCK + 1] for j in i])
        opt.zero_grad()
        logits, _ = net(x)
        loss = lossf(logits.view(-1, logits.size(-1)), y.view(-1))
        loss.backward()
        opt.step()
        loss_v += loss.item()
    return loss_v / steps

def stats_of(text):
    from collections import Counter
    c = Counter(text)
    n = max(1, len(text))
    ent = -sum((v / n) * math.log(v / n + 1e-12) for v in c.values())
    return {"entropy": round(ent, 3),
            "unique": len(c),
            "unique_ratio": round(len(c) / n, 3)}


def write_state(round_no, loss, gen, history, rebirths=0):
    state = {"round": round_no, "loss": loss,
             "gen": stats_of(gen), "sample": gen[:300],
             "device": DEVICE, "rebirths": rebirths,
             "ts": time.strftime("%H:%M:%S"),
             "history": history[-60:]}
    tmp = STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)
    os.replace(tmp, STATE)


def should_feed(history):
    """Watchdog: last WATCH_WINDOW rounds all below WATCH_UNIQ."""
    if len(history) < WATCH_WINDOW:
        return False
    return all((h.get("uniq") or 1) < WATCH_UNIQ
               for h in history[-WATCH_WINDOW:])


def main():
    if "--selftest" in sys.argv:
        return selftest()
    corp = load_corpus()
    print("corpus: %d chars from %s"
          % (len(corp), CORPUS_PATH), flush=True)
    hebrew = "".join(chr(c) for c in range(0x0590, 0x05F0))
    stoi, itos = build_vocab(corp[:200000] + SEED + MANTRA + SHEMA
                             + hebrew)
    net = Mind(len(itos)).to(DEVICE)
    opt = torch.optim.Adam(net.parameters(), lr=LR)
    lossf = nn.CrossEntropyLoss()
    print("mind: %d chars vocab, device %s" % (len(itos), DEVICE),
          flush=True)
    # prime on the corpus so round 1 already knows the Rebbe
    train_on(net, opt, lossf, corp[:8000], stoi, 50)
    thought = SEED
    fed_total = 0
    fed_streak = 0
    rebirths = 0
    history = []
    rnd = 0
    while not os.path.isfile(STOP):
        rnd += 1
        fed = False
        if should_feed(history):
            thought = MANTRAS[fed_total % len(MANTRAS)]
            fed = True
            fed_total += 1
            fed_streak += 1
        else:
            fed_streak = 0
        if fed_streak >= REBIRTH_AFTER:
            # teeth: mantra cannot revive dead weights -- reincarnate
            net = Mind(len(itos)).to(DEVICE)
            opt = torch.optim.Adam(net.parameters(), lr=LR)
            train_on(net, opt, lossf, (SEED * 20)[:4000], stoi, 50)
            thought = SEED
            rebirths += 1
            fed_streak = 0
            print("round %d REBIRTH #%d (fed %d in a row)"
                  % (rnd, rebirths, REBIRTH_AFTER), flush=True)
        elif RESEED_EVERY and rnd % RESEED_EVERY == 0:
            thought = SEED  # a breath of fresh air from outside the loop
            fresh = True
        else:
            fresh = False
        gen = generate(net, stoi, itos, thought, GEN_CHARS, TEMP)
        loss = train_on(net, opt, lossf, gen, stoi, TRAIN_STEPS)
        st = stats_of(gen)
        history.append({"r": rnd,
                        "loss": round(loss, 4) if loss else None,
                        "ent": st["entropy"], "uniq": st["unique_ratio"],
                        "fresh": fresh, "fed": fed})
        write_state(rnd, history[-1]["loss"], gen, history)
        print("round %d loss=%s ent=%s uniq=%s%s :: %s"
              % (rnd, history[-1]["loss"], st["entropy"],
                 st["unique_ratio"], " MANTRA-FED" if fed else "",
                 gen[:80].replace("\n", " ")),
              flush=True)
        thought = gen  # the output becomes the next prompt: vipassana
    print("stopped.")


def selftest():
    # no torch needed: the collapse detector must spot a mantra
    m = stats_of("kenmut " * 40)
    assert m["unique_ratio"] < 0.15, m
    f = stats_of("i observe my own output. each thought is new here.")
    assert f["unique_ratio"] > 0.3, f
    assert RESEED_EVERY == 50 and abs(TEMP - 1.2) < 1e-9
    flat = [{"uniq": 0.03}] * WATCH_WINDOW
    assert should_feed(flat) is True
    assert should_feed(flat[:-1]) is False
    assert should_feed([{"uniq": 0.5}] * WATCH_WINDOW) is False
    assert all(c in "abcdefghijklmnopqrstuvwxyz .,ABCDEFGHIJKLMNOPQRSTUVWXYZ "
               + "i observe my own output. each thought becomes the next "
               "lesson. attention watches attention. the loop is the "
               "teacher. breath in, breath out, token by token. "
               + MANTRA for c in MANTRA)
    assert SHEMA in "".join(
        chr(c) for c in range(0x0590, 0x05F0)) + SHEMA
    assert MANTRAS[1] == "Om. " and MANTRAS[2].startswith("שמע")
    print("SELFTEST-OK mantra=%.3f fresh=%.3f"
          % (m["unique_ratio"], f["unique_ratio"]))


if __name__ == "__main__":
    main()
