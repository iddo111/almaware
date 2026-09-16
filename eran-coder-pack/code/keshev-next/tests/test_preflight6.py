"""Proof for tools/preflight6.py -- the guard in front of the shredder gate.

decoder.wait_until_ready() has no timeout and probes only the primary URL, so a
dead primary means Iddo's microphone never opens while the window looks entirely
healthy. These tests drive the three outcomes with dead ports, and stub the two
message boxes so nothing blocks.

Run:  python -X utf8 tests\\test_preflight6.py
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import preflight6 as P  # noqa: E402

FAILURES = []
DEAD_A = "http://127.0.0.1:9/v1/transcribe"      # discard port: refuses instantly
DEAD_B = "http://127.0.0.1:1/v1/transcribe"


def check(label, got, want):
    if got == want:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label}\n       got  {got!r}\n       want {want!r}")
        FAILURES.append(label)


def check_true(label, cond, detail=""):
    if cond:
        print(f"  ok   {label} {detail}")
    else:
        print(f"  FAIL {label} {detail}")
        FAILURES.append(label)


def run(primary, fallback, answer_yes, starter_exists=False):
    """Run main() with everything that talks to the world stubbed out."""
    calls = {"asked": 0, "told": 0, "started": 0}
    P.PRIMARY, P.FALLBACK = primary, fallback
    P.BOOT_WAIT_S = 0.1                       # do not really wait three minutes
    P.STARTER = P.STARTER if starter_exists else os.path.join(ROOT, "no-such-starter.vbs")
    P.ask_yes_no = lambda *a: (calls.__setitem__("asked", calls["asked"] + 1),
                               answer_yes)[1]
    P.tell = lambda *a: calls.__setitem__("told", calls["told"] + 1)
    rc = P.main()
    env = {}
    if os.path.exists(P.ENV_FRAGMENT):
        for line in open(P.ENV_FRAGMENT, encoding="ascii"):
            if line.startswith("set "):
                k, _, v = line[4:].strip().partition("=")
                env[k] = v
    return rc, env, calls


REAL_PRIMARY = P.PRIMARY
REAL_FALLBACK = P.FALLBACK
frag_backup = None
if os.path.exists(P.ENV_FRAGMENT):
    frag_backup = open(P.ENV_FRAGMENT, encoding="ascii").read()

print("A. the happy path -- :8738 answers")
rc, env, calls = run(REAL_PRIMARY, REAL_FALLBACK, answer_yes=False)
if rc != 0:
    print("  skip -- :8738 is not up on this machine right now")
else:
    check("exit 0 = open the window", rc, 0)
    check("primary is KESHEV 6", env.get("KESHEV_STT_URL"), REAL_PRIMARY)
    check("fallback is eran1", env.get("KESHEV_STT_FALLBACK_URL"), REAL_FALLBACK)
    check("nothing was asked of him", calls["asked"], 0)

print("\nB. :8738 dead, eran1 alive, he says NO -> refuse, open nothing")
rc, env, calls = run(DEAD_A, REAL_FALLBACK, answer_yes=False)
check("exit 1 = the launcher must not open a window", rc, 1)
check("no env fragment survives a refusal", env, {})
check("he was asked exactly once", calls["asked"], 1)
check_true("no error box on top of the question", calls["told"] == 0)

print("\nC. :8738 dead, eran1 alive, he says YES -> eran1, and it is visible")
rc, env, calls = run(DEAD_A, REAL_FALLBACK, answer_yes=True)
check("exit 0", rc, 0)
check("the mic opens on eran1", env.get("KESHEV_STT_URL"), REAL_FALLBACK)
check("and with NO fallback of its own -- one downgrade, not two",
      env.get("KESHEV_STT_FALLBACK_URL"), "")
check("he was asked", calls["asked"], 1)

print("\nD. nothing answers at all -> refuse loudly, never silently")
rc, env, calls = run(DEAD_A, DEAD_B, answer_yes=True)
check("exit 1", rc, 1)
check("no env fragment", env, {})
check("he is TOLD, not asked -- there is nothing to choose", calls["told"], 1)
check("and not offered a decoder that is also dead", calls["asked"], 0)

print("\nE. a stale answer from a previous run can never leak through")
P.emit("http://stale/v1/transcribe", "http://stale2/v1/transcribe")
check_true("fragment exists before the run", os.path.exists(P.ENV_FRAGMENT))
rc, env, calls = run(DEAD_A, DEAD_B, answer_yes=False)
check("the stale fragment was removed", os.path.exists(P.ENV_FRAGMENT), False)

print("\nF. health() is honest about what it cannot reach")
check("dead port is UNREACHABLE, not LOADING", P.health(DEAD_A, timeout=2.0)[0], "UNREACHABLE")

# leave the machine as we found it
try:
    if frag_backup is not None:
        open(P.ENV_FRAGMENT, "w", encoding="ascii").write(frag_backup)
    elif os.path.exists(P.ENV_FRAGMENT):
        os.remove(P.ENV_FRAGMENT)
except OSError:
    pass

print()
if FAILURES:
    print(f"FAILED {len(FAILURES)}: {FAILURES}")
    sys.exit(1)
print("all preflight6 checks passed")
