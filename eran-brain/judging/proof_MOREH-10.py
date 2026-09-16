"""PROOF MOREH-10 — the blind sitting must notice when its A/B key changes under it.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

The defect: school2.py loaded the A/B key once at import and deleted it (`del _KEY`). The process on
127.0.0.1:8856 has been resident since 2026-09-05 03:50. If make_sitting_v2.py is re-run — it does
shutil.rmtree(OUT) and re-draws the pairs — the live server keeps serving /clip/<syl>/A.wav from the
OLD mapping while the KEY on disk describes the NEW one, and every verdict Iddo gives is recorded
against the wrong clip. That is exactly the shape of the 132-item mislabeled exam.

The fix: key_fingerprint() is checked on every request and every vote (503 when it no longer matches
what this process holds), and the fingerprint is stamped into each verdict row, so a mislabeled sitting
is detectable after the fact instead of believed.

NOTHING is restarted here: this proof imports the FILE, it never touches pid 12540 and never binds a
port. The fix is a net for the next start of school2.py.

    python proof_MOREH-10.py          # live school2.py     -> must PASS
    python proof_MOREH-10.py --old    # .bak-rev-20260906   -> must FAIL
"""
import atexit
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
OLD = "--old" in sys.argv
BAK = ".bak-rev-20260906"


def load(basename, name, old):
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    path = os.path.join(HERE, basename)
    if old:
        path = os.path.join(HERE, "_probe_%s_%d.py" % (name, os.getpid()))
        shutil.copyfile(os.path.join(HERE, basename + BAK), path)
        atexit.register(lambda p=path: os.path.exists(p) and os.remove(p))
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


class FakeReq(object):
    """just enough of the handler to call _stale_key() and _vote() without a socket"""
    def __init__(self, mod):
        self.sent = []
        self._mod = mod

    def _s(self, body, ctype="text/html; charset=utf-8", code=200):
        self.sent.append((code, len(body)))


def main():
    M = load("school2.py", "school2_under_test", OLD)
    print("school2 under test: %s   pairs=%d   sitting=%s" % (
        "school2.py" + BAK if OLD else "school2.py", M.N, M.SITTING))

    if not hasattr(M, "key_fingerprint") or not hasattr(M.H, "_stale_key"):
        raise AssertionError("school2.py never re-reads its KEY: the A/B mapping is loaded once at "
                             "import and `del _KEY`, so a regenerated sitting is served against the "
                             "old pairs and every verdict is mislabeled with no way to tell")
    print("key fingerprint at import: %s" % M.KEY_SHA)

    tmp = tempfile.mkdtemp(prefix="moreh-proof10-")
    key_copy = os.path.join(tmp, "KEY.json")
    shutil.copyfile(M.KEY_PATH, key_copy)
    M.KEY_PATH = key_copy
    M.LOG = os.path.join(tmp, "school2.log")          # never write the live server's log
    M.VERDICTS = os.path.join(tmp, "verdicts.jsonl")  # never write the real verdicts file
    M.KEY_SHA = M.key_fingerprint()

    h = M.H.__new__(M.H)
    h._s = FakeReq(M)._s
    h.sent = []
    h._s = lambda body, ctype="text/html; charset=utf-8", code=200: h.sent.append((code, len(body)))
    assert M.H._stale_key(h) is False, "the key matches but the page refused to serve"
    print("unchanged key -> serves normally: yes")

    # a vote lands, and carries the fingerprint
    unit = M.UNITS[0]
    M.H._vote(h, {"unit": unit, "choice": "A", "note": "proof"})
    rows = [json.loads(l) for l in io.open(M.VERDICTS, encoding="utf-8") if l.strip()]
    print("vote wrote %d rows; key_sha on the row: %s" % (len(rows), rows[0].get("key_sha")))
    assert len(rows) == 2 and rows[0].get("key_sha") == M.KEY_SHA, \
        "the verdict row does not record which key it was scored against"

    # now the sitting is regenerated under the running process
    d = json.load(io.open(key_copy, encoding="utf-8"))
    first = list(d["pairs"])[0]
    d["pairs"][first]["A"], d["pairs"][first]["B"] = d["pairs"][first]["B"], d["pairs"][first]["A"]
    json.dump(d, io.open(key_copy, "w", encoding="utf-8"), ensure_ascii=False)
    h.sent = []
    stale = M.H._stale_key(h)
    print("key swapped on disk -> _stale_key()=%r  http=%s" % (stale, [c for c, _ in h.sent]))
    assert stale is True, "the A/B mapping changed on disk and the page kept serving the old pairs"
    assert h.sent and h.sent[0][0] == 503, h.sent

    n_before = len(rows)
    h.sent = []
    M.H._vote(h, {"unit": unit, "choice": "B", "note": "must not be recorded"})
    rows2 = [json.loads(l) for l in io.open(M.VERDICTS, encoding="utf-8") if l.strip()]
    print("vote attempted against a changed key -> rows %d -> %d" % (n_before, len(rows2)))
    assert len(rows2) == n_before, "a verdict was recorded against a key this process no longer holds"

    shutil.rmtree(tmp, ignore_errors=True)
    print("PROOF MOREH-10 PASSED")


try:
    main()
except Exception as e:
    print("PROOF MOREH-10 FAILED: %s: %s" % (type(e).__name__, e))
    sys.exit(1)
