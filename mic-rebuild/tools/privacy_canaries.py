"""Gate-19 canary helpers — K11 (PHASE2-DESIGN.md section 9, criterion 19).

The privacy audit sends scripted utterances containing DISTINCTIVE rare
words to the server, then greps the entire journal + filesystem for them
afterward. This module is the PC-side half's brain:

  * the 5 canary phrases (rare words, unique across phrases — a grep hit
    anywhere on eran1 after the session is a retention finding)
  * `send` — POST the canary WAVs through the REAL client engine
    (client.dgx_engine.DgxEngine, the same code the router will use) and
    emit the word lists the eran1-side script greps for. Crucially the
    grep list includes words from the RESPONSE text, not only the intended
    ones — if the decode mangled a word, the mangled form is what a
    retention leak would contain.
  * `report` — assemble state/reports/gate19-<date>.json; verdict PASS
    only if EVERY step passed.

No torch, no sounddevice, no capture devices — WAV files in, HTTP out.
"""
from __future__ import annotations

import argparse
import json
import re
import secrets
import sys
import wave
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from common import protocol  # noqa: E402

# 5 phrases; every word of 8+ letters is rare enough that a grep hit on
# eran1 after the session cannot plausibly be someone else's text.
CANARY_PHRASES = (
    "The quixotic zeppelin hauled some marmalade.",
    "A porcupine blew the saxophone in a dirigible.",
    "The chrysanthemum tambourine hummed at dusk.",
    "My telescope showed a turquoise armadillo.",
    "The crocodile ate seventeen pistachio cupcakes.",
)

_WORD_RE = re.compile(r"[a-z]+", re.IGNORECASE)
_MIN_DISTINCTIVE = 8      # >= 8 letters: quixotic, zeppelin, marmalade...
_MIN_RESPONSE = 5         # response-derived grep terms may be shorter


def distinctive_words(phrase: str) -> list:
    """The rare words of a phrase — lowercase, alphabetic, >= 8 letters."""
    return [w.lower() for w in _WORD_RE.findall(phrase)
            if len(w) >= _MIN_DISTINCTIVE]


def response_words(text: str) -> list:
    """Grep terms derived from what the server ACTUALLY returned."""
    seen, out = set(), []
    for w in _WORD_RE.findall(text):
        lw = w.lower()
        if len(lw) >= _MIN_RESPONSE and lw not in seen:
            seen.add(lw)
            out.append(lw)
    return out[:10]


def hits(text: str, words) -> list:
    """Which canary words appear in `text` (case/punctuation-insensitive)."""
    tokens = {w.lower() for w in _WORD_RE.findall(text)}
    return [w for w in words if w.lower() in tokens]


def wav_to_pcm(path: Path) -> bytes:
    """Load a canary WAV; refuse anything but 16kHz mono s16le (the wire
    format — protocol section 3.1)."""
    with wave.open(str(path), "rb") as w:
        if w.getframerate() != protocol.SAMPLE_RATE:
            raise ValueError(f"{path}: must be {protocol.SAMPLE_RATE}Hz, "
                             f"got {w.getframerate()}")
        if w.getnchannels() != 1:
            raise ValueError(f"{path}: must be mono")
        if w.getsampwidth() != 2:
            raise ValueError(f"{path}: must be s16le")
        return w.readframes(w.getnframes())


def request_ids(n: int) -> list:
    session = secrets.token_hex(4)
    return [protocol.make_request_id(session, i + 1) for i in range(n)]


def build_report(steps: dict) -> dict:
    """gate19 report: PASS only if every step passed (design section 9.6)."""
    ok = bool(steps) and all(bool(s.get("pass")) for s in steps.values())
    return {"gate": 19,
            "date": datetime.now().astimezone().isoformat(timespec="seconds"),
            "steps": steps,
            "verdict": "PASS" if ok else "FAIL"}


# ---------------------------------------------------------------- CLI

def _cmd_send(args) -> int:
    from client.dgx_engine import DgxEngine
    token = Path(args.token_file).read_text(encoding="utf-8").strip()
    eng = DgxEngine(args.url, token, timeout=30)
    wavs = sorted(Path(args.wav_dir).glob("canary*.wav"))
    if len(wavs) != len(CANARY_PHRASES):
        print(f"expected {len(CANARY_PHRASES)} canary*.wav in {args.wav_dir}, "
              f"found {len(wavs)}", file=sys.stderr)
        return 2
    rids = request_ids(len(wavs))
    intended: list = []
    derived: list = []
    results = []
    for wav, phrase, rid in zip(wavs, CANARY_PHRASES, rids):
        pcm = wav_to_pcm(wav)
        res = eng.transcribe(pcm, request_id=rid,
                             duration_ms=len(pcm) // 32, lang_hint="en")
        want = distinctive_words(phrase)
        got = hits(res.text, want)
        results.append({"wav": wav.name, "phrase": phrase, "request_id": rid,
                        "intended": want, "decoded_hits": got,
                        "decode_ms": res.decode_ms, "model": res.model,
                        "lang": res.lang, "response_len": len(res.text)})
        intended.extend(want)
        derived.extend(response_words(res.text))
        print(f"  {wav.name}: {len(got)}/{len(want)} intended words decoded "
              f"({res.decode_ms}ms, {res.model})", flush=True)
    confirmed = sum(1 for r in results if r["decoded_hits"])
    Path(args.out_intended).write_text("\n".join(sorted(set(intended))) + "\n",
                                       encoding="utf-8")
    Path(args.out_response).write_text(
        "\n".join(sorted(set(derived) | set(intended))) + "\n", encoding="utf-8")
    Path(args.out_json).write_text(
        json.dumps({"confirmed_phrases": confirmed, "results": results},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  canary decode confirmation: {confirmed}/{len(wavs)} phrases")
    # Every phrase must PROVE it transited the decoder, else the grep that
    # follows would be vacuous.
    return 0 if confirmed == len(wavs) else 1


def _cmd_report(args) -> int:
    steps = {}
    for name, ok, detail in args.step:
        steps[name] = {"pass": ok.upper() == "PASS", "detail": detail}
    rep = build_report(steps)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"gate19 verdict: {rep['verdict']} -> {out}")
    return 0 if rep["verdict"] == "PASS" else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Gate-19 canary sender/report (K11)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("send")
    s.add_argument("--url", required=True)
    s.add_argument("--token-file", required=True)
    s.add_argument("--wav-dir", required=True)
    s.add_argument("--out-json", required=True)
    s.add_argument("--out-intended", required=True)
    s.add_argument("--out-response", required=True)
    s.set_defaults(fn=_cmd_send)
    r = sub.add_parser("report")
    r.add_argument("--out", required=True)
    r.add_argument("--step", nargs=3, action="append", required=True,
                   metavar=("NAME", "PASS|FAIL", "DETAIL"))
    r.set_defaults(fn=_cmd_report)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
