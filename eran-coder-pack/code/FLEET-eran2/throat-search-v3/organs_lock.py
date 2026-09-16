# -*- coding: utf-8 -*-
"""organs_lock.py -- the CORTEX-FREEZE LAW made executable.

ORGANS.lock pins every organ the v3 campaign judges and speaks with:
Ear v3 (spec hash + carfac SHA + patch + calibration + targets cache +
package sources), Mouth v2 (every source file + the per-box compiled C
core), the geometry authority, and the cortex slot (Judge B pending).

`verify()` recomputes every hash live and REFUSES on any mismatch --
run_worker.py calls it before touching the search. Retraining or editing
an organ mid-campaign therefore kills every worker at its next start
instead of silently moving the goalposts. Escape hatch = Iddo's explicit
order -> close the v3 books, open v4 fresh (plan Phase 3, CORTEX-FREEZE
LAW).

The compiled libvoc_eran.so is per-HOST (each box runs gcc itself), so
the lock stores {hostname: sha256} and each box verifies its own entry.
The bit-parity battery (validate/v_parity.py, max|diff| must be 0.0) is
what proves the per-box binaries equivalent; the lock proves nobody
swapped one afterwards.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import socket
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
EAR_DIR = os.path.expanduser("~/ear-v3")
MOUTH_DIR = os.path.expanduser("~/mouth-v2")
LOCK_PATH = os.path.join(_HERE, "ORGANS.lock")

for p in (EAR_DIR, MOUTH_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

MOUTH_FILES = ("mouth2.py", "glottis.py", "tract_core.py", "geometry.py",
               "fastcore.py", "voc_eran.c")
EAR_PKG_FILES = ("features.py", "judge.py", "calib.py", "pitch.py",
                 "carfac_wrap.py", "__init__.py")
SO_NAME = "libvoc_eran.so"


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _live_state():
    """Hash every organ as it exists on THIS box right now."""
    from ear3 import features as F
    st = {
        "ear3": {
            "spec_hash": F.spec_hash(),
            "carfac_sha": F.CARFAC_SHA,
            "patch_id": F.PATCH_ID,
            "calib_sha256": sha256_file(os.path.join(EAR_DIR,
                                                     "ear3-calib.json")),
            "targets_cache_sha256": sha256_file(
                os.path.join(EAR_DIR, "targets-cache", "ear3-t06.json")),
            "pkg_sha256": {n: sha256_file(os.path.join(EAR_DIR, "ear3", n))
                           for n in EAR_PKG_FILES},
        },
        "cortex": "none-v0 (Judge B pending)",
        "mouth2": {n: sha256_file(os.path.join(MOUTH_DIR, n))
                   for n in MOUTH_FILES},
        "geometry": "story-bunton-child-60mo",
    }
    so = os.path.join(MOUTH_DIR, SO_NAME)
    st["libvoc_local"] = sha256_file(so) if os.path.exists(so) else None
    return st


def build(extra_hosts=None):
    """Write ORGANS.lock from the live state of this box. Run ONCE at
    campaign prep; per-box .so entries are added with add_host()."""
    st = _live_state()
    lock = {
        "built_utc": datetime.datetime.now(datetime.timezone.utc)
        .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "built_on": socket.gethostname(),
        "ear3": st["ear3"],
        "cortex": st["cortex"],
        "mouth2": st["mouth2"],
        "geometry": st["geometry"],
        "libvoc_sha256": {socket.gethostname(): st["libvoc_local"]},
    }
    if extra_hosts:
        lock["libvoc_sha256"].update(extra_hosts)
    with open(LOCK_PATH, "w", encoding="utf-8") as f:
        json.dump(lock, f, indent=1, sort_keys=True)
    return lock


def add_host():
    """Register THIS box's freshly-built .so in an existing lock
    (deploy step: gcc build.sh, parity battery, then this)."""
    with open(LOCK_PATH, encoding="utf-8") as f:
        lock = json.load(f)
    so = os.path.join(MOUTH_DIR, SO_NAME)
    lock["libvoc_sha256"][socket.gethostname()] = sha256_file(so)
    with open(LOCK_PATH, "w", encoding="utf-8") as f:
        json.dump(lock, f, indent=1, sort_keys=True)
    return lock


def verify(allow_ref_fallback=True):
    """Recompute everything, compare to the lock, REFUSE on mismatch.

    Returns (lock, backend) where backend is 'c' normally, 'ref' only
    when the local .so is genuinely absent (never when it MISmatches --
    a swapped binary is a lock violation, not a fallback)."""
    if not os.path.exists(LOCK_PATH):
        raise SystemExit("ORGANS.lock REFUSAL: no lock at %s -- run "
                         "organs_lock.build() at campaign prep" % LOCK_PATH)
    with open(LOCK_PATH, encoding="utf-8") as f:
        lock = json.load(f)
    st = _live_state()
    errs = []
    for k in ("spec_hash", "carfac_sha", "patch_id", "calib_sha256",
              "targets_cache_sha256"):
        if st["ear3"][k] != lock["ear3"].get(k):
            errs.append("ear3.%s: live %s != lock %s"
                        % (k, st["ear3"][k], lock["ear3"].get(k)))
    for n in EAR_PKG_FILES:
        if st["ear3"]["pkg_sha256"][n] != lock["ear3"]["pkg_sha256"].get(n):
            errs.append("ear3/%s hash mismatch" % n)
    for n in MOUTH_FILES:
        if st["mouth2"][n] != lock["mouth2"].get(n):
            errs.append("mouth-v2/%s hash mismatch" % n)
    if st["cortex"] != lock.get("cortex"):
        errs.append("cortex: live %r != lock %r"
                    % (st["cortex"], lock.get("cortex")))
    if st["geometry"] != lock.get("geometry"):
        errs.append("geometry: live %r != lock %r"
                    % (st["geometry"], lock.get("geometry")))

    host = socket.gethostname()
    want_so = lock.get("libvoc_sha256", {}).get(host)
    backend = "c"
    if st["libvoc_local"] is None:
        if want_so is not None or not allow_ref_fallback:
            errs.append("libvoc_eran.so missing on %s but lock expects %s"
                        % (host, want_so))
        else:
            backend = "ref"           # honest fallback: the reference IS truth
    elif want_so is None:
        errs.append("libvoc_eran.so exists on %s but host is not in the "
                    "lock -- run organs_lock.add_host() after the parity "
                    "battery passes" % host)
    elif st["libvoc_local"] != want_so:
        errs.append("libvoc_eran.so on %s: live %s != lock %s (a swapped "
                    "binary is a violation, not a fallback)"
                    % (host, st["libvoc_local"], want_so))
    if errs:
        raise SystemExit("ORGANS.lock REFUSAL (CORTEX-FREEZE LAW):\n  "
                         + "\n  ".join(errs))
    return lock, backend


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "verify"
    if cmd == "build":
        lk = build()
        print("ORGANS.lock written: ear3 spec %s..., %d mouth files, host %s"
              % (lk["ear3"]["spec_hash"][:12], len(lk["mouth2"]),
                 lk["built_on"]))
    elif cmd == "add-host":
        lk = add_host()
        print("added %s -> %s" % (socket.gethostname(),
                                  lk["libvoc_sha256"][socket.gethostname()][:16]))
    else:
        lk, be = verify()
        print("ORGANS.lock VERIFIED on %s (backend=%s, ear3 spec %s...)"
              % (socket.gethostname(), be, lk["ear3"]["spec_hash"][:12]))
