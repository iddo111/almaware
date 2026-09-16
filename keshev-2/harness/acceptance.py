"""KESHEV 2 acceptance harness — replay A's baseline, report honestly.

Replays the ACCEPTANCE BASELINE table of
D:\\CLAUDE\\mic-rebuild\\INSIGHTS-FOR-KESHEV2.md section 7 (KESHEV A,
measured 2026-08-17, live session 24ca194b) and reports KESHEV 2 against it
PER CRITERION. Three honest verdict classes:

  MEASURED     a real number produced tonight, next to A's number
  UNMEASURED-TONIGHT   cannot be measured without audio capture / a live
               session / a full dictation day — says exactly why
  N/A          the criterion is about A's live deployment, not comparable

Never opens an audio device. The decode round-trip uses A's CANARY wavs
(synthetic System.Speech phrases, tools/make_canary_wavs.ps1 — no privacy
content) read from disk and POSTed through K2's OWN SttClient to the real
eran1 server. That is a true end-to-end measurement of K2's client code
against A's 407ms baseline, minus only the microphone itself.

Run:  python harness/acceptance.py            (writes ACCEPTANCE-<date>.md)
"""
from __future__ import annotations

import datetime as _dt
import re
import statistics
import subprocess
import sys
import time
import wave
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from k2 import sttclient  # noqa: E402

A_REPO = Path(r"D:\CLAUDE\mic-rebuild")
CANARY_DIR = A_REPO / "tools" / "replay" / "wavs" / "canary"
TOKEN_PATH = A_REPO / "state" / "stt-token"
SERVER_URL = "http://<lan-ip>:8737"

# canary reference words, from tools/privacy_canaries.py (verified against
# state/reports/canary-20260812.json — every phrase decoded with its
# intended rare words on 2026-08-12)
CANARY_WORDS = {
    "canary1.wav": ("quixotic", "zeppelin", "marmalade"),
    "canary2.wav": ("porcupine", "saxophone", "dirigible"),
    "canary3.wav": ("chrysanthemum", "tambourine", "dusk"),
    "canary4.wav": ("telescope", "turquoise", "armadillo"),
    # not "seventeen": the server (correctly) normalizes it to "17" and a
    # naive word match calls a perfect decode BROKEN — measured tonight.
    # A's own rule is alphabetic words >= 8 letters; these three qualify.
    "canary5.wav": ("crocodile", "pistachio", "cupcakes"),
}

# KESHEV A's baseline — INSIGHTS-FOR-KESHEV2.md section 7, verbatim.
A_BASELINE = [
    ("test suite", "878 tests, 0 failures, 19 skips, ~177s"),
    ("lint gates", "6/6 clean + 6/6 self-test fire"),
    ("DGX decode round-trip (2.4s he wav)", "407ms wall / 399ms server"),
    ("client p50/p95 decode (live)", "387-388ms / 720-758ms"),
    ("client/worker RSS, worker VRAM", "68 / 825 / 537 MB"),
    ("dropped capture frames", "0"),
    ("server canary age / uptime", "<300s / 2.9 days"),
    ("watchdog verdict on live journal", "HEALTHY seg=57 decode=58 typed=3"),
    ("real-he guard regression", "CER 0.0000 n=40, 0 guard-dropped"),
    ("Hebrew decode quality (fixtures)", "CER 0.000"),
]


def run_suite() -> tuple[str, str]:
    t0 = time.perf_counter()
    proc = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests",
         "-t", "."],
        cwd=str(REPO), capture_output=True, text=True, timeout=600)
    wall = time.perf_counter() - t0
    tail = proc.stderr.strip().splitlines()
    ran = next((ln for ln in tail if ln.startswith("Ran ")), "Ran ? tests")
    m = re.search(r"Ran (\d+) tests", ran)
    n = m.group(1) if m else "?"
    ok = tail[-1].strip() if tail else "?"
    failures = "0 failures" if ok == "OK" else ok
    return (f"{n} tests, {failures}, {wall:.0f}s",
            "MEASURED" if proc.returncode == 0 else "BROKEN")


def run_lint() -> tuple[str, str]:
    clean = subprocess.run([sys.executable, "tools/lint.py"], cwd=str(REPO),
                           capture_output=True, text=True)
    st = subprocess.run([sys.executable, "tools/lint.py", "--self-test"],
                        cwd=str(REPO), capture_output=True, text=True)
    n_pass = clean.stdout.count(": PASS")
    n_fire = st.stdout.count(": FIRES")
    verdict = ("MEASURED" if clean.returncode == 0 and st.returncode == 0
               else "BROKEN")
    return f"{n_pass}/6 clean + {n_fire}/6 self-test fire", verdict


def read_canary_pcm(path: Path) -> tuple[bytes, int]:
    with wave.open(str(path), "rb") as w:
        assert w.getframerate() == 16000 and w.getnchannels() == 1 \
            and w.getsampwidth() == 2, f"{path.name}: not 16k mono s16le"
        pcm = w.readframes(w.getnframes())
        dur_ms = int(w.getnframes() / 16.0)
    return pcm, dur_ms


def run_decode_roundtrip() -> tuple[str, str]:
    if not CANARY_DIR.is_dir():
        return "canary wavs absent", "UNMEASURED-TONIGHT"
    try:
        token = sttclient.load_token(TOKEN_PATH)
    except sttclient.SttAuthError as exc:
        return f"token unavailable ({exc})", "UNMEASURED-TONIGHT"
    client = sttclient.SttClient(SERVER_URL, token, default_hint="he")
    session = "beefcafe"
    walls, hits, total = [], 0, 0
    for i, (name, words) in enumerate(sorted(CANARY_WORDS.items()), 1):
        path = CANARY_DIR / name
        if not path.exists():
            continue
        pcm, dur_ms = read_canary_pcm(path)
        rid = sttclient.make_request_id(session, i)
        t0 = time.perf_counter()
        try:
            res = client.transcribe(pcm, request_id=rid,
                                    duration_ms=dur_ms, lang_hint="en")
        except sttclient.SttError as exc:
            return f"decode failed: {exc}", "BROKEN"
        walls.append((time.perf_counter() - t0) * 1000)
        low = res.text.lower()
        total += len(words)
        hits += sum(1 for w in words if w in low)
    if not walls:
        return "no canary wavs found", "UNMEASURED-TONIGHT"
    p50 = statistics.median(walls)
    return (f"{len(walls)} canaries via K2 SttClient: wall p50 "
            f"{p50:.0f}ms (min {min(walls):.0f} max {max(walls):.0f}), "
            f"rare-word hits {hits}/{total}",
            "MEASURED" if hits == total else "BROKEN")


def run_probe() -> tuple[str, str]:
    try:
        token = sttclient.load_token(TOKEN_PATH)
    except sttclient.SttAuthError as exc:
        return f"token unavailable ({exc})", "UNMEASURED-TONIGHT"
    p = sttclient.SttClient(SERVER_URL, token).probe()
    if not p.healthy:
        return f"unhealthy: {p.reason}", "BROKEN"
    return (f"healthy, canary_age {p.canary_age_s:.0f}s, server p50 "
            f"{p.decode_p50_ms}ms p95 {p.decode_p95_ms}ms"), "MEASURED"


UNMEASURED = {
    "client p50/p95 decode (live)":
        "needs live capture; K2 has no capture module (A holds the mic)",
    "client/worker RSS, worker VRAM":
        "needs a running capture+worker session; K2 is shadow-only tonight",
    "dropped capture frames":
        "no capture module exists tonight — by design (rival interlock)",
    "watchdog verdict on live journal":
        "K2 has no live dictation session to judge",
    "real-he guard regression":
        "needs A's labeled he fixture set + K2's guard stack (guard stack "
        "not built tonight: textguard/langpolicy are next-night scope)",
    "Hebrew decode quality (fixtures)":
        "same fixture dependency; canary round-trip (en) measured instead",
}


def main() -> int:
    rows: list[tuple[str, str, str, str]] = []
    print("KESHEV 2 acceptance vs KESHEV A baseline — measuring...")

    suite_val, suite_v = run_suite()
    lint_val, lint_v = run_lint()
    rt_val, rt_v = run_decode_roundtrip()
    probe_val, probe_v = run_probe()

    tonight = {
        "test suite": (suite_val, suite_v),
        "lint gates": (lint_val, lint_v),
        "DGX decode round-trip (2.4s he wav)": (rt_val, rt_v),
        "server canary age / uptime": (probe_val, probe_v),
    }

    for name, a_value in A_BASELINE:
        if name in tonight:
            k2_value, verdict = tonight[name]
        else:
            k2_value, verdict = UNMEASURED[name], "UNMEASURED-TONIGHT"
        rows.append((name, a_value, k2_value, verdict))

    date = _dt.date.today().strftime("%Y%m%d")
    out = REPO / "harness" / f"ACCEPTANCE-{date}.md"
    lines = [
        "# KESHEV 2 vs KESHEV A — acceptance report " + date,
        "",
        "> KESHEV A stays king of the microphone until every row below is",
        "> MEASURED and K2 beats or matches it. UNMEASURED-TONIGHT rows say",
        "> exactly what they are waiting for. `health: ok` counts for",
        "> nothing (criterion 16 is the only final gate).",
        "",
        "| criterion | KESHEV A (2026-08-17) | KESHEV 2 tonight | verdict |",
        "|---|---|---|---|",
    ]
    for name, a, k, v in rows:
        lines.append(f"| {name} | {a} | {k} | {v} |")
    lines += [
        "",
        "Notes:",
        "- decode round-trip uses A's synthetic English canary wavs through",
        "  K2's OWN SttClient against the real eran1:8737 — true client",
        "  code path, no microphone. A's 407ms row was one 2.4s Hebrew wav;",
        "  numbers are comparable in magnitude, not identical in kind.",
        "- UIPI/typing round-trip additionally unmeasured tonight: running",
        "  a SendInput selftest beside the live mic risks focus disturbance",
        "  (A's selftest pattern is inherited and runs at the cutover trial).",
        "",
        "*Real, not demo. Proof, honest. לזכרה של עלמה ז\"ל.*",
    ]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")

    width = max(len(r[0]) for r in rows)
    for name, a, k, v in rows:
        print(f"  {name:<{width}}  [{v}]")
        print(f"    {'A':>2}: {a}")
        print(f"    K2: {k}")
    print(f"\nreport -> {out}")
    broken = [r for r in rows if r[3] == "BROKEN"]
    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main())
