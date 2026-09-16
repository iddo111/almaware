# -*- coding: utf-8 -*-
"""proof_K6-12 -- the repair map nobody could audit, proved over a real socket.

    python proof_K6-12.py <path-to-keshev6_server.py>

FAILS on the old file, PASSES on the fixed one. This is the END-TO-END proof:
the real _Handler, a real POST of real PCM bytes over an ephemeral loopback
port, the real lexicon.py that sits beside the server. Only the whisper engine
is a stub -- the defect is in what the server WRITES DOWN about a repair, not in
what the model heard.

The measurement behind it: /metrics said repaired=1 in 2,287 replies and
joined=0 in 6,229. So the map is nearly all dead weight -- but nothing anywhere
said WHICH entries are alive, and the only part that fires is the fuzzy pass,
the one that can silently turn a real Hebrew word into a project name.

Cases:
  A  an EXACT repair is logged, named as exact
  B  a FUZZY repair is logged, named as fuzzy, with the target it landed on
  C  the log never contains what the model produced -- only its length
     (status_line already refuses text=/transcript=; a REPAIR line must not
     smuggle the same thing in under another key)
  D  the reply is unchanged on the wire: same field names, repaired count
  E  GET /health over the socket is 503 when the canary is stale (K6-03's
     health_code reached through the real handler, not called directly)
"""
from __future__ import annotations

import importlib.util
import json
import logging
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

TARGET = Path(sys.argv[1]).resolve()
FAILS: list[str] = []

GARBLE_EXACT = "צ'רלי וחצי"      # -> צ'ינצ'ילה   (EXACT_REPAIRS)
GARBLE_FUZZY = "הולוברין"        # -> הולובריין   (FUZZY_TARGETS, ratio .94)


def check(name: str, ok: bool, detail: str = "") -> None:
    print("  %-58s %s%s" % (name, "PASS" if ok else "FAIL",
                            ("  <- " + str(detail)) if detail else ""))
    if not ok:
        FAILS.append(name)


class StubEngine:
    model_id = "stub-ivrit"

    def decode(self, audio, language="he", initial_prompt=None):
        # what the live model really produced on 2026-09-03, plus one near-miss
        return {"text": "%s ו%s" % (GARBLE_EXACT, GARBLE_FUZZY),
                "avg_logprob": -0.31, "no_speech_prob": 0.08,
                "compression_ratio": 1.4}


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="k6proof12-"))
    shutil.copy2(TARGET, tmp / "keshev6_server.py")
    lex_src = TARGET.parent / "lexicon.py"
    if not lex_src.exists():
        print("no lexicon.py beside %s -- cannot run" % TARGET)
        return 1
    shutil.copy2(lex_src, tmp / "lexicon.py")

    spec = importlib.util.spec_from_file_location("k6_under_test12",
                                                  tmp / "keshev6_server.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules["k6_under_test12"] = m
    spec.loader.exec_module(m)
    print("proof_K6-12 against %s" % TARGET)

    records: list[str] = []

    class Cap(logging.Handler):
        def emit(self, rec):
            records.append(rec.getMessage())

    logging.getLogger("keshev6").addHandler(Cap())
    logging.getLogger("keshev6").setLevel(logging.INFO)

    cfg = {"bind": ["127.0.0.1"], "port": 0, "canary_interval_s": 300,
           "canary_lock_wait_s": 5.0, "decode_wall_s": 8.0, "inflight_cap": 2,
           "use_prompt": True, "use_repair": True}
    srv = m.Keshev6Server(cfg, token="prooftoken")
    srv.engine = StubEngine()
    srv.start()
    srv.run_canary()
    srv.set_ready()
    port = srv.port

    pcm = (b"\x10\x00" * 16000)          # 1 s of quiet-but-nonzero s16le
    req = urllib.request.Request(
        "http://127.0.0.1:%d/v1/transcribe" % port, data=pcm, method="POST",
        headers={"Authorization": "Bearer prooftoken",
                 "Content-Type": "audio/x-raw",
                 "X-Request-Id": "proof12-%d" % int(time.time()),
                 "X-Lang-Hint": "he"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            code, payload = r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        code, payload = e.code, {"error": e.read()[:120].decode("utf-8", "replace")}

    check("the request is answered 200", code == 200, "code=%s %s" % (code, payload))

    repair_lines = [r for r in records if r.startswith("evt=REPAIR")]
    check("A an EXACT repair is logged and named",
          any("kind=exact" in r for r in repair_lines),
          repair_lines[0] if repair_lines else "(no REPAIR lines at all)")
    check("B a FUZZY repair is logged and named, with its target",
          any("kind=fuzzy" in r and "to=" in r for r in repair_lines),
          "; ".join(repair_lines) if repair_lines else "(no REPAIR lines at all)")
    check("B the fuzzy line carries the produced word only as a LENGTH",
          any("from_len=" in r for r in repair_lines),
          "; ".join(repair_lines) if repair_lines else "-")

    # C: privacy. What the MODEL produced must appear in no log line anywhere.
    leaked = [r for r in records if GARBLE_EXACT in r or GARBLE_FUZZY in r]
    check("C the log never contains what the model produced", not leaked,
          leaked[0] if leaked else "")

    # D: the wire contract did not move
    fields_ok = all(k in payload for k in
                    ("request_id", "text", "lang", "avg_logprob", "speech_ratio",
                     "repaired", "joined", "decode_ms", "model"))
    check("D the reply still carries every contract field", fields_ok,
          sorted(payload)[:12])
    check("D the reply reports the repair count",
          payload.get("repaired", 0) >= 2, "repaired=%r" % payload.get("repaired"))
    check("D the repaired text really was repaired",
          "צ'ינצ'ילה" in payload.get("text", "")
          and "הולובריין" in payload.get("text", ""),
          "len=%d" % len(payload.get("text", "")))

    # E: /health over the socket, with a stale canary
    srv._canary_ts = time.monotonic() - 3600.0
    hreq = urllib.request.Request("http://127.0.0.1:%d/health" % port,
                                  headers={"Authorization": "Bearer prooftoken"})
    try:
        with urllib.request.urlopen(hreq, timeout=10) as r:
            hcode = r.status
    except urllib.error.HTTPError as e:
        hcode = e.code
    check("E GET /health is 503 when the canary is an hour stale",
          hcode == 503, "got %s while state=%s" % (hcode, srv.state))

    srv.stop()
    print("\nproof_K6-12: %s" % ("PASS" if not FAILS else
                                 "FAIL (%d) -> %s" % (len(FAILS), FAILS)))
    return 0 if not FAILS else 1


if __name__ == "__main__":
    raise SystemExit(main())
