# -*- coding: utf-8 -*-
"""KESHEV AUTOTRAIN / keshev_model.py -- THE BUTTON. הכפתור.

> BROKEN WINDOWS LAW: test the REAL output, not a proxy.

Iddo, 2026-09-12: "וניתן להחליף אפילו בלחיצת כפתור" -- switch model version at
the press of a button.

WHAT THE BUTTON ACTUALLY MOVES
------------------------------
The live Hebrew decoder is eran1:8739 (keshev6-stt.service). Its config,
/home/eran1/keshev6/server-6.json, names ONE weights directory:

    "model": "/home/eran1/keshev6/models/ivrit-large-v3-turbo-ct2"

So a "model version" is a CTranslate2 directory, and switching versions is
repointing that path. We do NOT rewrite the config on every switch -- a config
edit is a merge conflict waiting to happen, and a half-written config is a mic
that will not start. Instead the config path becomes a SYMLINK, swapped
atomically with `mv -T`:

    models/CURRENT  ->  models/<version>/

and server-6.json names models/CURRENT once, forever.

THREE RULES THIS FILE ENFORCES
------------------------------
1. NEVER AUTO-PROMOTE. `use` refuses a version with no recorded evaluation, or
   whose evaluation did not BEAT the incumbent on the frozen set. `--force` is
   there for Iddo's own word overriding a number, and is recorded as forced.
2. THE CURRENT MODEL IS THE DEFAULT. A missing symlink, an unreadable ledger, a
   fresh install: all resolve to the incumbent, never to a candidate.
3. ROLLBACK IS ALWAYS ONE WORD. Every switch appends to versions.jsonl naming
   what it replaced, so `rollback` is exact rather than remembered -- and it is
   never gated on a number, because the way back must always be open.

IT DOES NOT RESTART THE DECODER. CTranslate2 loads weights at process start, so
a swapped symlink takes effect when the server next loads. This tool STAGES the
swap and prints the apply command rather than running it. Restarting a decoder
under a live microphone is how you take the mic away from him mid-sentence.
"""
from __future__ import annotations
import argparse, json, os, shlex, subprocess, sys, time

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HOST = "eran1"
MODELS = "/home/eran1/keshev6/models"
CURRENT = MODELS + "/CURRENT"
LEDGER = MODELS + "/versions.jsonl"
EVALS = MODELS + "/evals.jsonl"
INCUMBENT = "ivrit-large-v3-turbo-ct2"
SERVICE = "keshev6-stt"


def ssh(cmd, check=False):
    r = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", HOST, cmd],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        sys.exit("[button] %s failed: %s" % (HOST, (r.stderr or "").strip()[:300]))
    return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()


def read_jsonl(path):
    _rc, out, _e = ssh("cat " + shlex.quote(path) + " 2>/dev/null")
    rows = []
    for ln in out.splitlines():
        ln = ln.strip()
        if ln:
            try:
                rows.append(json.loads(ln))
            except Exception:
                pass
    return rows


def append_jsonl(path, obj):
    """Append one row remotely without letting its text reach the shell."""
    line = json.dumps(obj, ensure_ascii=False)
    return ssh("cat >> " + shlex.quote(path) + " <<'KESHEV_EOF'\n" + line + "\nKESHEV_EOF")


def current_version():
    """The version the live decoder will load next.

    `readlink -f` echoes the path back when nothing is there, which would report
    the version as the literal string "CURRENT" -- a name that is not a model.
    So require a REAL symlink first, and fall back to the incumbent otherwise
    (rule 2: a missing link resolves to the model that is already working)."""
    rc, out, _ = ssh("test -L " + shlex.quote(CURRENT) +
                     " && readlink -f " + shlex.quote(CURRENT) + " 2>/dev/null")
    if rc == 0 and out and os.path.basename(out) != "CURRENT":
        return os.path.basename(out)
    return INCUMBENT                       # rule 2: default is the incumbent


def list_versions():
    _rc, out, _e = ssh("ls -1 " + shlex.quote(MODELS) + " 2>/dev/null")
    return [v for v in out.splitlines()
            if v and v != "CURRENT" and not v.endswith(".jsonl")]


def best_eval(evals, version):
    rows = [e for e in evals if e.get("version") == version and e.get("wer") is not None]
    return rows[-1] if rows else None


def cmd_status(a):
    cur = current_version()
    evals = read_jsonl(EVALS)
    e = best_eval(evals, cur)
    print("KESHEV Hebrew model / המודל העברי החי")
    print("  live decoder  : %s:8739 (%s)" % (HOST, SERVICE))
    print("  CURRENT       : %s" % cur)
    if e:
        print("  its number    : WER %.4f on %s" % (e["wer"], e.get("evalset", "?")))
    else:
        print("  its number    : not recorded yet")
    print("  versions      : %s" % (", ".join(list_versions()) or "-"))
    hist = read_jsonl(LEDGER)
    if hist:
        h = hist[-1]
        print("  last switch   : %s -> %s  (%s, by %s)"
              % (h.get("from"), h.get("to"), h.get("ts"), h.get("by")))
    else:
        print("  last switch   : never -- the original model is live")
    return 0


def cmd_list(a):
    evals = read_jsonl(EVALS)
    cur = current_version()
    vs = list_versions()
    if not vs:
        print("[button] no model directories on %s:%s" % (HOST, MODELS))
        return 0
    for v in vs:
        e = best_eval(evals, v)
        print(" %s %-42s %s" % ("*" if v == cur else " ", v,
                                ("WER %.4f" % e["wer"]) if e else "no number"))
    print("\n * = live now / חי עכשיו")
    return 0


def _switch(to, why, by, force=False):
    cur = current_version()
    if to == cur:
        print("[button] %s is already live. Nothing to do." % to)
        return 0
    if to not in list_versions():
        sys.exit("[button] no such version on %s: %s" % (HOST, to))

    evals = read_jsonl(EVALS)
    e_new, e_cur = best_eval(evals, to), best_eval(evals, cur)
    if not force:
        if not e_new:
            sys.exit("[button] REFUSED: %s has no evaluation on the frozen set.\n"
                     "         Run evaluate.py first, or pass --force to override with\n"
                     "         your own word (it is recorded as forced)." % to)
        if e_cur and not (e_new["wer"] < e_cur["wer"]):
            sys.exit("[button] REFUSED: %s scored WER %.4f; live %s scores %.4f.\n"
                     "         A tie or a loss is a loss. Nothing was swapped."
                     % (to, e_new["wer"], cur, e_cur["wer"]))

    rc, _o, err = ssh("set -e; cd %s; ln -sfn %s .CURRENT.new; mv -T .CURRENT.new CURRENT"
                      % (shlex.quote(MODELS), shlex.quote(to)))
    if rc != 0:
        sys.exit("[button] swap failed, nothing changed: %s" % err[:300])

    append_jsonl(LEDGER, {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "from": cur, "to": to,
        "why": why, "by": by, "forced": bool(force),
        "wer_to": (e_new or {}).get("wer"), "wer_from": (e_cur or {}).get("wer")})

    print("[button] STAGED: %s  ->  %s" % (cur, to))
    print("[button] הוחלף. It takes effect when the decoder next loads its weights.")
    print("[button] to apply now (this restarts the decoder -- NOT done for you):")
    print("           ssh %s systemctl --user restart %s" % (HOST, SERVICE))
    print("[button] to undo:  python keshev_model.py rollback")
    return 0


def cmd_use(a):
    return _switch(a.version, a.why or "manual", a.by, force=a.force)


def cmd_rollback(a):
    hist = read_jsonl(LEDGER)
    if not hist:
        sys.exit("[button] no switch on record -- nothing to roll back to.")
    prev = hist[-1].get("from")
    if not prev:
        sys.exit("[button] the last ledger row names no previous version.")
    print("[button] rolling back to %s (live before %s)" % (prev, hist[-1].get("to")))
    return _switch(prev, "rollback", a.by, force=True)   # the way back is never gated


def cmd_record(a):
    """Record an evaluation number for a version (used by evaluate.py)."""
    append_jsonl(EVALS, {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                         "version": a.version, "wer": a.wer,
                         "evalset": a.evalset, "n": a.n, "by": a.by})
    print("[button] recorded: %s WER %.4f on %s (n=%s)" % (a.version, a.wer, a.evalset, a.n))
    return 0


def main():
    ap = argparse.ArgumentParser(description="KESHEV model switch / הכפתור")
    ap.add_argument("--by", default=os.environ.get("USERNAME") or "iddo")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help="what is live now").set_defaults(fn=cmd_status)
    sub.add_parser("list", help="every version and its number").set_defaults(fn=cmd_list)
    u = sub.add_parser("use", help="switch to a version")
    u.add_argument("version")
    u.add_argument("--why")
    u.add_argument("--force", action="store_true",
                   help="his word over the number -- recorded as forced")
    u.set_defaults(fn=cmd_use)
    sub.add_parser("rollback", help="back to the previous version").set_defaults(fn=cmd_rollback)
    r = sub.add_parser("record", help="record an eval number for a version")
    r.add_argument("version")
    r.add_argument("--wer", type=float, required=True)
    r.add_argument("--evalset", default="cafe-reserved")
    r.add_argument("--n", type=int, default=0)
    r.set_defaults(fn=cmd_record)
    a = ap.parse_args()
    sys.exit(a.fn(a) or 0)


if __name__ == "__main__":
    main()
