# -*- coding: utf-8 -*-
r"""
sanity_check_payload.py — בדיקת ניקיון המטען הציבורי של הפדרציה
================================================================
🪟 BROKEN WINDOWS LAW: test the REAL output. This fetches the EXACT payload the
60s cloud pusher sends (GET /api/push_preview.json on the live local server) and
proves it leaks nothing:

  * literal substrings that must be absent:  D:\  C:\  D:/  C:/  192.168.  100.
    plus "token" / "ts.net" (case-insensitive), 127.0.0.1, ://, any backslash
  * the actual secret values from .fed_push_token and alma-federation's
    .alma_token must not appear (values are read, compared, never printed)
  * Hebrew transcript text: snippets of the live RAMCHAT last-5 messages must
    NOT appear in the payload (counts only are allowed)
  * structure: only registry public:true nodes are pushed, none of the
    public:false ids leak

Prints CLEAN on success (exit 0), DIRTY + reasons on failure (exit 1).
"""

import json
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

BASE = "http://127.0.0.1:8895"
PREVIEW_URL = BASE + "/api/push_preview.json"
LOCAL_URL = BASE + "/api/federation.json"
FED_TOKEN_PATH = r"D:\CLAUDE\eran-federation-app\panel\.fed_push_token"
ALMA_TOKEN_PATH = r"D:\CLAUDE\alma-federation\.alma_token"

# the acceptance list (literal substring matches) + extra belt-and-suspenders
LITERALS = ["D:\\", "C:\\", "D:/", "C:/", "192.168.", "100.", "127.0.0.1", "://", "\\"]
WORDS_CI = ["token", "ts.net"]


def fetch_text(url, timeout=40):
    req = urllib.request.Request(url, headers={"User-Agent": "sanity-check/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8")


def read_secret(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read().strip() or None
    except OSError:
        return None


def main():
    print("== sanity_check_payload — בדיקת ניקיון המטען הציבורי ==")
    failures = []

    try:
        raw = fetch_text(PREVIEW_URL)
        payload = json.loads(raw)
    except Exception as exc:
        print("[FAIL] cannot fetch %s: %s: %s" % (PREVIEW_URL, type(exc).__name__, exc))
        print("DIRTY")
        return 1

    # scan BOTH the raw wire text and a compact re-dump (escaping-independent)
    scan_text = raw + "\n" + json.dumps(payload, ensure_ascii=False)

    nodes = payload.get("nodes") or []
    print("payload: %d bytes on the wire, %d public nodes, generated_at %s"
          % (len(raw.encode("utf-8")), len(nodes), payload.get("generated_at")))
    if not nodes:
        failures.append("payload has zero nodes — nothing measured (אין צמתים)")

    # 1) forbidden literal substrings
    for lit in LITERALS:
        n = scan_text.count(lit)
        tag = "PASS" if n == 0 else "FAIL"
        print('[%s] literal %-10r — %d hits' % (tag, lit, n))
        if n:
            failures.append("literal %r found %d times" % (lit, n))

    # 2) forbidden words, case-insensitive
    low = scan_text.lower()
    for w in WORDS_CI:
        n = low.count(w)
        tag = "PASS" if n == 0 else "FAIL"
        print('[%s] word (ci) %-10r — %d hits' % (tag, w, n))
        if n:
            failures.append("word %r found %d times" % (w, n))

    # 3) secret values absent (read, compared, never printed)
    for label, path in (("FED_PUSH_TOKEN", FED_TOKEN_PATH),
                        ("alma X-Alma credential", ALMA_TOKEN_PATH)):
        sec = read_secret(path)
        if sec is None:
            print("[WARN] %s file unreadable — absence not provable" % label)
            failures.append("%s unreadable — cannot prove absence" % label)
        elif sec in scan_text:
            print("[FAIL] %s VALUE appears in payload" % label)
            failures.append("%s value leaked" % label)
        else:
            print("[PASS] %s value absent (הסוד לא במטען)" % label)

    # 4) Hebrew transcript text absent — snippets from the live local snapshot
    snippets = []
    try:
        local = json.loads(fetch_text(LOCAL_URL))
        last5 = ((local.get("ramchat") or {}).get("transcript") or {}).get("last5") or []
        for msg in last5:
            text = (msg.get("text") or "").strip()
            snip = text[:24].strip()
            if len(snip) >= 12:
                snippets.append(snip)
    except Exception as exc:
        print("[WARN] local snapshot unreadable (%s) — transcript check limited"
              % type(exc).__name__)
        failures.append("could not sample transcript text for the leak check")
    leaked = [s for s in snippets if s in scan_text]
    if leaked:
        print("[FAIL] transcript text leaked — %d of %d snippets found in payload"
              % (len(leaked), len(snippets)))
        failures.append("transcript text present in payload")
    else:
        print("[PASS] transcript text absent (אין טקסט תמלול) — %d snippets checked"
              % len(snippets))

    # 5) only public:true nodes pushed
    try:
        pub_ids = {n.get("id") for n in (local.get("nodes") or []) if n.get("public")}
        priv_ids = {n.get("id") for n in (local.get("nodes") or []) if not n.get("public")}
        pushed_ids = {n.get("id") for n in nodes}
        bad = pushed_ids & priv_ids
        unknown = pushed_ids - pub_ids - priv_ids
        if bad:
            print("[FAIL] private nodes leaked: %s" % sorted(bad))
            failures.append("public:false nodes pushed: %s" % sorted(bad))
        elif unknown:
            print("[FAIL] pushed ids not in the local registry: %s" % sorted(unknown))
            failures.append("unknown node ids pushed")
        else:
            print("[PASS] only public nodes pushed (רק צמתים ציבוריים) — %d/%d"
                  % (len(pushed_ids), len(pub_ids) + len(priv_ids)))
    except NameError:
        pass  # local snapshot fetch already failed above and was recorded

    print()
    if failures:
        print("DIRTY")
        for f in failures:
            print(" - " + f)
        return 1
    print("CLEAN")
    return 0


if __name__ == "__main__":
    sys.exit(main())
