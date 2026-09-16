# -*- coding: utf-8 -*-
"""PROOF SO-16 -- the /wav guard used startswith(realpath(ROOT)) with no trailing
separator, so a SIBLING directory passed the prefix test: ~/throat-search-v3-evil/x.wav
reads as "inside ~/throat-search-v3". Exposure is Tailscale-only, which is why this is
minor and not serious -- but a path check that is off by one separator is still off.

    python3 proof_SO-16.py ~/eran-throat-listen.py.bak-rev-20260906   -> FAIL
    python3 proof_SO-16.py ~/eran-throat-listen.py                    -> PASS

Uses a throwaway tree under /tmp and an ephemeral localhost port. The real trees, :8845 and
pid 3252 are untouched.
"""
import os
import shutil
import sys
import tempfile
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _proof_listen as L                                           # noqa: E402

PATH = os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else "~/eran-throat-listen.py")
print("PROOF SO-16 against %s" % PATH)
mod = L.load(PATH)
checks = []

tmp = tempfile.mkdtemp(prefix="proof-so16-")
good_root = os.path.join(tmp, "throat-search-v3")
evil_root = os.path.join(tmp, "throat-search-v3-evil")
os.makedirs(os.path.join(good_root, "run", "arm"), exist_ok=True)
os.makedirs(evil_root, exist_ok=True)
human = os.path.join(tmp, "t06")
os.makedirs(human, exist_ok=True)
good_wav = os.path.join(good_root, "run", "arm", "best.wav")
evil_wav = os.path.join(evil_root, "secret.wav")
open(good_wav, "wb").write(b"RIFF....WAVEfmt ")
open(evil_wav, "wb").write(b"RIFF....WAVEstolen")

# point the code under test at the throwaway tree, whichever name it uses
if hasattr(mod, "ROOTS"):
    mod.ROOTS = [good_root]
mod.ROOT = good_root
mod.HUMAN = human

st_evil, body_evil = L.get(mod, "/wav?f=" + urllib.parse.quote(evil_wav))
st_good, body_good = L.get(mod, "/wav?f=" + urllib.parse.quote(good_wav))

checks.append(("a sibling directory is refused (throat-search-v3-evil)",
               st_evil == 404,
               "HTTP %s for %s (%d bytes)" % (st_evil, evil_wav, len(body_evil))))
checks.append(("control: a real file inside the tree is still served",
               st_good == 200 and body_good.startswith(b"RIFF"),
               "HTTP %s, %d bytes" % (st_good, len(body_good))))

shutil.rmtree(tmp, ignore_errors=True)
L.report(checks)
