"""Proof for tools/preflight6.py -- the guard in front of the shredder gate.

HERMETIC REWRITE, 2026-09-15 (broken-windows W7). The previous version set
P.PRIMARY / P.FALLBACK, which preflight6.py no longer defines, and it ran
main() and emit() against the REAL state folder. emit() writes
state\\decoder.json, and app/decoder.py re-reads that file on every segment.
Its case E wrote "http://stale/v1/transcribe" there, so running the old
test, or just letting pytest collect it, could move Iddo's live mic onto a
decoder that does not exist.

What this version does instead:
  * The two files main()/emit() write (ENV_FRAGMENT, DECODER_JSON) and the PC
    starter it launches (STARTER) point into a fresh tempfile.mkdtemp() BEFORE
    anything runs.
  * A hard guard re-checks, before every main() and at the moment of every
    emit(), that both write targets sit inside that temp folder. It also
    refuses anything under the live D:\\CLAUDE\\keshev-next\\state, anything
    under this tree's own state\\, and any folder shaped like keshev-next\\state
    (a decoy or a copy). Pure path arithmetic: it never opens the live files.
    Cases L and M exercise the guard on a decoy, never on the live folder.
  * health(), wait_ready(), start_pc_server(), ask_yes_no() and tell() are
    stubbed. Nothing reaches the network, no GPU server starts and no message
    box appears. Only case K calls the real health(), on a refused local port.
  * Nothing runs at import time, so `pytest tests/` collection is safe too.

Order under test (preflight6.main as of 2026-09-15):
  eran2:8739 (ERAN2) -> eran1:8739 (DGX) -> PC:8738 (PC, started only here)
  -> eran1:8737 (OLD, only as a question)

Run:  python -X utf8 tests\\test_preflight6.py     (or: pytest tests\\test_preflight6.py)
"""

import hashlib
import json
import os
import shutil
import sys
import tempfile

sys.dont_write_bytecode = True           # leave no .pyc behind in tools\

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import preflight6 as P  # noqa: E402

LIVE_STATE = r"D:\CLAUDE\keshev-next\state"   # the folder the running engine reads
DEAD = "http://127.0.0.1:9/v1/transcribe"     # discard port: refuses instantly

REAL = {name: getattr(P, name) for name in
        ("ENV_FRAGMENT", "DECODER_JSON", "STARTER", "BOOT_WAIT_S", "health",
         "wait_ready", "start_pc_server", "ask_yes_no", "tell", "emit")}

FAILURES = []
SANDBOX = None


# ---------------------------------------------------------------------------
# the guard
# ---------------------------------------------------------------------------
class HermeticError(RuntimeError):
    pass


def _norm(path):
    return os.path.normcase(os.path.realpath(os.path.abspath(path)))


def _under(path, folder):
    path, folder = _norm(path), _norm(folder)
    try:
        return os.path.commonpath([path, folder]) == folder
    except ValueError:                   # different drives
        return False


def _shaped_like_live(path):
    parts = [p.lower() for p in _norm(path).replace("\\", "/").split("/") if p]
    return any(parts[i] == "keshev-next" and parts[i + 1] == "state"
               for i in range(len(parts) - 1))


def refuse_if_live(path, sandbox):
    """Raise HermeticError unless `path` is safely inside `sandbox`."""
    if not sandbox:
        raise HermeticError("no sandbox set -- refusing %s" % path)
    if _under(path, LIVE_STATE):
        raise HermeticError("path is inside the LIVE state dir: %s" % path)
    if _under(path, os.path.join(ROOT, "state")) or \
            _under(path, os.path.join(os.path.dirname(os.path.dirname(
                os.path.abspath(P.__file__))), "state")):
        raise HermeticError("path is inside this tree's own state dir: %s" % path)
    if _shaped_like_live(path):
        raise HermeticError("path is shaped like keshev-next\\state: %s" % path)
    if _shaped_like_live(sandbox) or _under(sandbox, LIVE_STATE):
        raise HermeticError("the sandbox itself looks like a live state dir: %s" % sandbox)
    if not _under(path, sandbox):
        raise HermeticError("path is outside the sandbox %s: %s" % (sandbox, path))


def assert_hermetic():
    for name in ("ENV_FRAGMENT", "DECODER_JSON", "STARTER"):
        refuse_if_live(getattr(P, name), SANDBOX)
    for name in ("health", "wait_ready", "start_pc_server", "ask_yes_no", "tell"):
        if getattr(P, name) is REAL[name]:
            raise HermeticError("P.%s is not stubbed" % name)
    if P.emit is REAL["emit"]:
        raise HermeticError("P.emit is not wrapped by the guard")


def guarded_emit(primary, fallback):
    assert_hermetic()                    # at the moment of the write, every time
    return REAL["emit"](primary, fallback)


# ---------------------------------------------------------------------------
# the fake world
# ---------------------------------------------------------------------------
READY_DATA = {"state": "READY", "models": ["ivrit-ai/whisper-large-v3-turbo-ct2"],
              "decode_p50_ms": 1, "canary_age_s": 1}


class World:
    """now: url -> state on probe. after_wait: url -> state once wait_ready()
    has been spent on it (a slow service, or the PC server after its start)."""

    def __init__(self, now, after_wait=None, answer_yes=False):
        self.now = dict(now)
        self.after_wait = dict(after_wait or {})
        self.answer_yes = answer_yes
        self.asked = self.told = self.started = 0
        self.waited = []
        self.probed = []

    def health(self, url, timeout=None):
        self.probed.append(url)
        state = self.now.get(url, "UNREACHABLE")
        return state, (dict(READY_DATA) if state == "READY" else {})

    def wait_ready(self, url, seconds):
        self.waited.append((url, seconds))
        if url in self.after_wait:
            self.now[url] = self.after_wait[url]
        return self.health(url)

    def start_pc_server(self):
        self.started += 1

    def ask_yes_no(self, *a):
        self.asked += 1
        return self.answer_yes

    def tell(self, *a):
        self.told += 1


def install(world):
    P.health = world.health
    P.wait_ready = world.wait_ready
    P.start_pc_server = world.start_pc_server
    P.ask_yes_no = world.ask_yes_no
    P.tell = world.tell
    P.emit = guarded_emit


def point_into_sandbox():
    P.ENV_FRAGMENT = os.path.join(SANDBOX, "state", "keshev6-env.cmd")
    P.DECODER_JSON = os.path.join(SANDBOX, "state", "decoder.json")
    P.STARTER = os.path.join(SANDBOX, "no-such-starter.vbs")


def clear_outputs():
    for path in (P.ENV_FRAGMENT, P.DECODER_JSON):
        refuse_if_live(path, SANDBOX)
        if os.path.exists(path):
            os.remove(path)


def read_fragment():
    env = {}
    if os.path.exists(P.ENV_FRAGMENT):
        with open(P.ENV_FRAGMENT, encoding="ascii") as fh:
            for line in fh:
                if line.startswith("set "):
                    k, _, v = line[4:].strip().partition("=")
                    env[k] = v
    return env


def read_decoder_json():
    if not os.path.exists(P.DECODER_JSON):
        return None
    with open(P.DECODER_JSON, encoding="utf-8") as fh:
        return json.load(fh)


def run(world, clear=True):
    install(world)
    assert_hermetic()                    # before main() so much as deletes a file
    if clear:
        clear_outputs()
    rc = P.main()
    return rc, read_fragment(), read_decoder_json()


def check(label, got, want):
    if got == want:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label}\n       got  {got!r}\n       want {want!r}")
        FAILURES.append(label)


def check_true(label, cond, detail=""):
    if cond:
        print(f"  ok   {label} {detail}".rstrip())
    else:
        print(f"  FAIL {label} {detail}".rstrip())
        FAILURES.append(label)


def sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def expect_refusal(label, fn):
    try:
        fn()
    except HermeticError as exc:
        print(f"  ok   {label}  ({exc})")
        return
    print(f"  FAIL {label}  (the guard let it through)")
    FAILURES.append(label)


# ---------------------------------------------------------------------------
# the cases
# ---------------------------------------------------------------------------
def cases():
    E2, DGX, PC, OLD = P.ERAN2, P.DGX, P.PC, P.OLD
    R, U = "READY", "UNREACHABLE"

    print("A. eran2 answers, eran1 answers -> eran2, with eran1's copy as fallback")
    w = World({E2: R, DGX: R, OLD: R})
    rc, env, dj = run(w)
    check("exit 0 = open the window", rc, 0)
    check("primary is eran2", env.get("KESHEV_STT_URL"), E2)
    check("fallback is eran1's copy of the same model", env.get("KESHEV_STT_FALLBACK_URL"), DGX)
    check("decoder.json primary agrees", (dj or {}).get("primary"), E2)
    check("decoder.json fallback agrees", (dj or {}).get("fallback"), DGX)
    check("decoder.json last resort is the PC", (dj or {}).get("last_resort"), P.PC_LAST_RESORT)
    check("nothing asked, nothing told", (w.asked, w.told), (0, 0))
    check("no retry wait, no PC start", (w.waited, w.started), ([], 0))

    print("\nB. eran2 answers, eran1 dead, old model alive -> old model as fallback")
    w = World({E2: R, DGX: U, OLD: R})
    rc, env, dj = run(w)
    check("exit 0", rc, 0)
    check("primary is eran2", env.get("KESHEV_STT_URL"), E2)
    check("fallback is the old model", env.get("KESHEV_STT_FALLBACK_URL"), OLD)
    check("decoder.json fallback agrees", (dj or {}).get("fallback"), OLD)

    print("\nC. eran2 answers, no fallback alive -> eran2 with an EMPTY fallback")
    w = World({E2: R, DGX: U, OLD: U})
    rc, env, dj = run(w)
    check("exit 0", rc, 0)
    check("primary is eran2", env.get("KESHEV_STT_URL"), E2)
    check("fallback is empty, not a dead door", env.get("KESHEV_STT_FALLBACK_URL"), "")
    check("decoder.json fallback empty", (dj or {}).get("fallback"), "")

    print("\nD. eran2 LOADING, READY within its short retry -> still eran2")
    w = World({E2: "LOADING", DGX: R, OLD: R}, after_wait={E2: R})
    rc, env, dj = run(w)
    check("exit 0", rc, 0)
    check("primary is eran2", env.get("KESHEV_STT_URL"), E2)
    check("waited once, on eran2 only", [u for u, _ in w.waited], [E2])
    check_true("and briefly (a live service, not a cold boot)",
               w.waited and w.waited[0][1] <= 30, "(%ss)" % (w.waited[0][1] if w.waited else "-"))

    print("\nE. eran2 dead, eran1 alive -> eran1, old model as its fallback")
    w = World({E2: U, DGX: R, OLD: R})
    rc, env, dj = run(w)
    check("exit 0", rc, 0)
    check("primary is eran1", env.get("KESHEV_STT_URL"), DGX)
    check("fallback is the old model", env.get("KESHEV_STT_FALLBACK_URL"), OLD)
    check("decoder.json primary agrees", (dj or {}).get("primary"), DGX)
    check("eran2 got its one short retry first", [u for u, _ in w.waited], [E2])
    check("the PC was not started", w.started, 0)
    check("nothing asked", w.asked, 0)

    print("\nF. both DGX copies dead, the PC's :8738 already up -> PC, not restarted")
    w = World({E2: U, DGX: U, PC: R, OLD: R})
    rc, env, dj = run(w)
    check("exit 0", rc, 0)
    check("primary is the PC", env.get("KESHEV_STT_URL"), PC)
    check("fallback is the old model", env.get("KESHEV_STT_FALLBACK_URL"), OLD)
    check("not started again", w.started, 0)

    print("\nG. both DGX copies dead, PC down -> START it, wait the boot window, use it")
    w = World({E2: U, DGX: U, PC: U, OLD: U}, after_wait={PC: R})
    rc, env, dj = run(w)
    check("exit 0", rc, 0)
    check("started exactly once", w.started, 1)
    check("waited the full boot window on the PC",
          [x for x in w.waited if x[0] == PC], [(PC, P.BOOT_WAIT_S)])
    check("primary is the PC", env.get("KESHEV_STT_URL"), PC)
    check("fallback empty (old model dead)", env.get("KESHEV_STT_FALLBACK_URL"), "")

    print("\nH. no good copy anywhere, old model alive, he says NO -> refuse, open nothing")
    w = World({E2: U, DGX: U, PC: U, OLD: R}, answer_yes=False)
    rc, env, dj = run(w)
    check("exit 1 = the launcher must not open a window", rc, 1)
    check("no env fragment survives a refusal", env, {})
    check("no decoder.json written", dj, None)
    check("the PC rescue was tried first", w.started, 1)
    check("he was asked exactly once", w.asked, 1)
    check("no error box on top of the question", w.told, 0)

    print("\nI. same, he says YES -> old model, one downgrade and no second one")
    w = World({E2: U, DGX: U, PC: U, OLD: R}, answer_yes=True)
    rc, env, dj = run(w)
    check("exit 0", rc, 0)
    check("the mic opens on the old model", env.get("KESHEV_STT_URL"), OLD)
    check("with NO fallback of its own", env.get("KESHEV_STT_FALLBACK_URL"), "")
    check("decoder.json agrees", ((dj or {}).get("primary"), (dj or {}).get("fallback")), (OLD, ""))
    check("he was asked", w.asked, 1)

    print("\nJ. nothing answers at all -> refuse loudly, never silently")
    w = World({E2: U, DGX: U, PC: U, OLD: U}, answer_yes=True)
    rc, env, dj = run(w)
    check("exit 1", rc, 1)
    check("no env fragment", env, {})
    check("no decoder.json written", dj, None)
    check("he is TOLD, not asked", (w.told, w.asked), (1, 0))

    print("\nJ2. a stale fragment from a previous run never leaks through a refusal")
    install(World({}))
    guarded_emit("http://stale/v1/transcribe", "http://stale2/v1/transcribe")
    check_true("stale fragment exists (in the SANDBOX) before the run", os.path.exists(P.ENV_FRAGMENT))
    rc, env, dj = run(World({E2: U, DGX: U, PC: U, OLD: U}), clear=False)
    check("exit 1", rc, 1)
    check("the stale fragment was removed", os.path.exists(P.ENV_FRAGMENT), False)
    print("  note main() removes only the .cmd fragment on refusal; the old decoder.json "
          "stays (%s). Current behaviour, not asserted." % ("present" if dj else "absent"))

    print("\nK. health() is honest about what it cannot reach (real function, refused local port)")
    saved_tok = os.environ.get("KESHEV_STT_TOKEN")
    os.environ["KESHEV_STT_TOKEN"] = "test-token-not-real"   # do not read the real token file
    try:
        check("dead port is UNREACHABLE, not LOADING", REAL["health"](DEAD, timeout=2.0)[0], "UNREACHABLE")
    finally:
        if saved_tok is None:
            os.environ.pop("KESHEV_STT_TOKEN", None)
        else:
            os.environ["KESHEV_STT_TOKEN"] = saved_tok

    print("\nL. the guard refuses live and live-shaped paths (decoys only, no I/O on live files)")
    live_dj = os.path.join(LIVE_STATE, "decoder.json")
    live_env = os.path.join(LIVE_STATE, "keshev6-env.cmd")
    decoy_dir = os.path.join(SANDBOX, "decoy", "keshev-next", "state")
    os.makedirs(decoy_dir, exist_ok=True)
    decoy_dj = os.path.join(decoy_dir, "decoder.json")
    with open(decoy_dj, "w", encoding="utf-8") as fh:
        fh.write('{"decoy": true}\n')
    decoy_sha = sha(decoy_dj)
    expect_refusal("live decoder.json", lambda: refuse_if_live(live_dj, SANDBOX))
    expect_refusal("live keshev6-env.cmd", lambda: refuse_if_live(live_env, SANDBOX))
    expect_refusal("this tree's own state\\decoder.json",
                   lambda: refuse_if_live(os.path.join(ROOT, "state", "decoder.json"), SANDBOX))
    expect_refusal("decoy shaped like keshev-next\\state, even inside the sandbox",
                   lambda: refuse_if_live(decoy_dj, SANDBOX))
    expect_refusal("a path outside the sandbox",
                   lambda: refuse_if_live(os.path.join(tempfile.gettempdir(), "x.json"), SANDBOX))
    expect_refusal("a sandbox that is itself the live state dir",
                   lambda: refuse_if_live(live_dj, LIVE_STATE))
    try:
        refuse_if_live(os.path.join(SANDBOX, "state", "decoder.json"), SANDBOX)
        print("  ok   a sandbox path is accepted")
    except HermeticError as exc:
        check_true("a sandbox path is accepted", False, str(exc))

    print("\nM. the guard actually STOPS a write aimed at the decoy (emit and main)")
    P.DECODER_JSON = decoy_dj
    install(World({}))
    expect_refusal("emit() with DECODER_JSON on the decoy",
                   lambda: guarded_emit("http://decoy/v1/transcribe", ""))
    w = World({E2: R, DGX: R})
    expect_refusal("main() with DECODER_JSON on the decoy", lambda: run(w))
    check("main() never ran (nothing probed)", w.probed, [])
    check("decoy byte-for-byte unchanged", sha(decoy_dj), decoy_sha)
    point_into_sandbox()
    P.ENV_FRAGMENT = os.path.join(decoy_dir, "keshev6-env.cmd")
    expect_refusal("main() with ENV_FRAGMENT on the decoy", lambda: run(World({E2: R, DGX: R})))
    check_true("no fragment appeared in the decoy", not os.path.exists(P.ENV_FRAGMENT))
    point_into_sandbox()


def main():
    global SANDBOX
    FAILURES.clear()
    SANDBOX = tempfile.mkdtemp(prefix="preflight6-test-")
    try:
        point_into_sandbox()
        install(World({}))
        try:
            assert_hermetic()
        except HermeticError as exc:
            print("ABORT -- not hermetic, nothing was run: %s" % exc)
            return 2
        print("sandbox: %s\n" % SANDBOX)
        cases()
    finally:
        for name, value in REAL.items():
            setattr(P, name, value)
        if SANDBOX and os.path.basename(SANDBOX).startswith("preflight6-test-"):
            shutil.rmtree(SANDBOX, ignore_errors=True)
        SANDBOX = None
    print()
    if FAILURES:
        print(f"FAILED {len(FAILURES)}: {FAILURES}")
        return 1
    print("all preflight6 checks passed")
    return 0


def test_preflight6_hermetic():          # pytest entry point
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
