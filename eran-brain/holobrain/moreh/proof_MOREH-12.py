"""PROOF MOREH-12 — a corpus that has vanished must FAIL the test suite, never skip it green.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

The defect: tests/test_organ.py began with

    pytestmark = pytest.mark.skipif(not any(os.path.isdir(r) for r in L.LESSONS), reason=...)

so if the lessons directory disappeared, every test was SKIPPED, pytest exited 0, and the organ
reported green with nothing to learn from. That is the same family as ERAN's silent starvation: an
empty input that produces no exception and no log line.

The fix: test_0_the_corpus_is_here() runs unconditionally and asserts a lessons root exists and holds
24 syllables.

How this is measured: the target test file is copied next to the real one (so its own __file__ still
finds anatomy/learn and ruler.py), pytest is run on the copy with a plugin that makes the corpus look
gone, and the exit code is read. Green on an empty corpus is the defect.

    python proof_MOREH-12.py          # live test_organ.py  -> must PASS
    python proof_MOREH-12.py --old    # .bak-rev-20260906   -> must FAIL
"""
import os
import shutil
import subprocess
import sys
import tempfile

ORGAN = os.path.dirname(os.path.abspath(__file__))
TESTS = os.path.join(ORGAN, "tests")
OLD = "--old" in sys.argv
BAK = ".bak-rev-20260906"

PLUGIN = '''# pytest plugin: make the lessons corpus look gone, before the test module is imported
import os, sys
sys.path.insert(0, os.environ["MOREH_ORGAN"])
import learn as L
_gone = os.environ["MOREH_GONE"]
L.LESSONS = [_gone]
if hasattr(L, "school_roots"):
    L.school_roots = lambda *a, **k: [_gone]
def _boom(*a, **k):
    raise FileNotFoundError("no lessons under ['%s']" % _gone)
L.load_lessons = _boom
'''


def main():
    src = os.path.join(TESTS, "test_organ.py" + (BAK if OLD else ""))
    print("test module under test: %s" % os.path.basename(src))
    tmp = tempfile.mkdtemp(prefix="moreh-proof12-")
    probe = os.path.join(TESTS, "test_organ_probe_%d.py" % os.getpid())
    open(os.path.join(tmp, "moreh_empty_plugin.py"), "w", encoding="utf-8").write(PLUGIN)
    shutil.copyfile(src, probe)
    env = dict(os.environ)
    env["PYTHONPATH"] = tmp + os.pathsep + env.get("PYTHONPATH", "")
    env["MOREH_ORGAN"] = ORGAN
    env["MOREH_GONE"] = os.path.join(tmp, "no-such-lessons")
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        r = subprocess.run([sys.executable, "-m", "pytest", probe, "-q", "-p", "moreh_empty_plugin",
                            "-p", "no:cacheprovider"],
                           cwd=ORGAN, env=env, capture_output=True, text=True, timeout=300)
    finally:
        if os.path.exists(probe):
            os.remove(probe)
        shutil.rmtree(tmp, ignore_errors=True)
    tail = [l for l in r.stdout.strip().splitlines() if l.strip()][-1:]
    print("pytest on a VANISHED corpus -> exit %d   %s" % (r.returncode, tail))
    assert "skipped" not in (tail[0] if tail else ""), (
        "the whole module was SKIPPED: pytest exits 0 and the organ reports green for a model whose "
        "corpus no longer exists")
    assert r.returncode != 0, (
        "pytest exited 0 with no corpus at all -- a missing corpus must be a failure, not a skip")
    print("a missing corpus is a FAILURE: yes")

    # and with the real corpus present the suite must still be green
    r2 = subprocess.run([sys.executable, "-m", "pytest", src if not OLD else probe, "-q",
                         "-p", "no:cacheprovider"],
                        cwd=ORGAN, capture_output=True, text=True, timeout=600) if not OLD else None
    if r2 is not None:
        print("pytest on the real corpus -> exit %d   %s" % (r2.returncode, r2.stdout.strip().splitlines()[-1:]))
        assert r2.returncode == 0, r2.stdout[-800:]
    print("PROOF MOREH-12 PASSED")


try:
    main()
except Exception as e:
    print("PROOF MOREH-12 FAILED: %s: %s" % (type(e).__name__, e))
    sys.exit(1)
