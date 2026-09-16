#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""almido_remote.py -- remote_build: compile and run on the FLEET, not on this PC.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

WHY THIS EXISTS. This PC has no working C toolchain -- the 07:31 council post records it
plainly: "MSVC/msys64 gcc BROKEN". ALMIDO's brain is a CODER; a coder that cannot compile
is guessing. eran4 has gcc 13.3, cmake 3.28.3 and nvcc CUDA 13.0 sitting idle (MEASURED
2026-09-11 08:34), and it is already ALMIDO's own box. So the compiler moves, not the code.

It also keeps a standing rule intact: heavy work does not run on the PC, because the PC is
where Iddo's microphone lives and a render starving KESHEV is a scar this workspace already
carries (2026-09-03).

    almido_remote  -->  almido_gate.gate("command", ...)   <- THE gate (policy + STOP + audit)
                   -->  tar + scp + ssh                    <- the transport, argv, never a shell

WHAT IT REFUSES, before the gate is even asked:
  * any command that names systemd/systemctl, docker, sudo, su, crontab, reboot, shutdown,
    a package manager, or ssh/scp onward (no pivoting from the build box)
  * ANYTHING that mentions ~/eran or /home/*/eran*  -- ERAN lives on this fleet. A build
    script must not be able to touch the organism, its snapshots, or its services.
  * a source tree that is missing, too big, or contains a path that escapes its own root
  * a build name that is not a plain token (it becomes a directory name on a live box)

WHAT IT IMPOSES on the remote side, always:
  * the work happens in ~/almido-build/<name>/ and nowhere else
  * `nice -n 10` -- a build never outbids ERAN or DARWISH for CPU
  * `timeout <N>` on the far side as well as a local timeout, so a runaway compile dies on
    the box rather than living on after this process gives up
  * PATH gains /usr/local/cuda/bin, because nvcc is not on the default PATH there

TRANSPORT. rsync is NOT installed on this PC (measured), so the tree goes as a tar.gz made
by Python's own tarfile, copied with scp, and unpacked with tar on the far side. No shell
pipeline anywhere: every step is one argv list.

Run:  python almido_remote.py selftest      (compiles hello.c and a .cu on eran4)
Test: python -m pytest tests/test_almido_remote.py
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
_HOME = Path(os.path.expanduser("~"))
_TOTZAREI_CLAUDE = "\u05ea\u05d5\u05e6\u05e8\u05d9 \u05e7\u05dc\u05d5\u05d3"
_HARNESS_NAME = "Perplexity-Computer-Use-Harness"

HARNESS_CANDIDATES = [Path(p) for p in (
    os.environ.get("ALMIDO_RB_HARNESS", ""),
    os.environ.get("ALMIDO_CU_HARNESS", ""),
    _HOME / "Desktop" / _TOTZAREI_CLAUDE / _HARNESS_NAME,
    _HOME / "Desktop" / "_Organized" / _TOTZAREI_CLAUDE / _HARNESS_NAME,
    _HOME / "Desktop" / "_Organized" / "Docs" / _HARNESS_NAME,
    _HOME / "Desktop" / _HARNESS_NAME,
    Path(r"D:\CLAUDE") / _HARNESS_NAME,
) if str(p)]

BUILD_HOST = os.environ.get("ALMIDO_BUILD_HOST", "eran4")
REMOTE_ROOT = os.environ.get("ALMIDO_BUILD_ROOT", "~/almido-build")
REMOTE_PATH = "/usr/local/cuda/bin:/usr/local/bin:/usr/bin:/bin"
NICE = int(os.environ.get("ALMIDO_BUILD_NICE", "10") or 10)
MAX_SECONDS = min(1800, int(os.environ.get("ALMIDO_BUILD_TIMEOUT", "600") or 600))
MAX_TREE_BYTES = int(os.environ.get("ALMIDO_BUILD_MAX_BYTES", str(200 * 1024 * 1024)))
MAX_TREE_FILES = int(os.environ.get("ALMIDO_BUILD_MAX_FILES", "5000") or 5000)
SSH_CONNECT_TIMEOUT = 10

_LOADED: dict = {"gate": None, "harness": None, "tried": [], "errors": []}


# ------------------------------------------------------------------ the gate, by path
def _load_module(name: str, path: Path):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError("no loader for %s" % path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _load() -> dict:
    if _LOADED["gate"] is not None or _LOADED["errors"]:
        return _LOADED
    for cand in HARNESS_CANDIDATES:
        _LOADED["tried"].append(str(cand))
        if not (cand / "almido_gate.py").is_file():
            continue
        try:
            _LOADED["gate"] = _load_module("almido_rb_gate", cand / "almido_gate.py")
            _LOADED["harness"] = cand
        except Exception as exc:
            _LOADED["errors"].append("%s: %s: %s" % (cand, type(exc).__name__, exc))
            continue
        return _LOADED
    if not _LOADED["errors"]:
        _LOADED["errors"].append("almido_gate.py found in none of: " + "; ".join(_LOADED["tried"]))
    return _LOADED


def _audit_direct(kind: str, detail: str, verdict: str, reason: str) -> None:
    gate = _load()["gate"]
    writer = getattr(gate, "_audit", None) if gate is not None else None
    if writer is None:
        return
    try:
        writer(kind, detail, verdict, reason)
    except Exception:
        pass


def _refuse(detail: str, reason: str) -> dict:
    _audit_direct("command", "remote_build:" + str(detail)[:160], "BLOCK", reason)
    return {"ok": False, "verdict": "BLOCK", "reason": reason, "performed": False,
            "detail": detail}


# ------------------------------------------------------------------ the fences
# ERAN lives on this fleet. Everything that could reach the organism, the services, the
# container runtime, or another machine is refused BEFORE the gate is consulted -- and the
# refusal is on the raw text, so an obfuscated variant fails the readability test too.
_FORBIDDEN = (
    (r"\bsystemctl\b|\bsystemd\b|\bjournalctl\b|\bloginctl\b",
     "systemd is off limits: the fleet's services are Iddo's, not a build's"),
    (r"\bdocker\b|\bpodman\b|\bnerdctl\b|\bctr\b",
     "the container runtime is off limits -- the 480B pipeline lives in it"),
    (r"\bsudo\b|\bsu\b\s|\bdoas\b|\bpkexec\b",
     "a build does not need to be root, so it never asks"),
    (r"~/eran|/home/[^/\s]+/eran|\beran_life\b|\bdarwish_life\b|\beranb-|\bdmidi-",
     "ERAN and DARWISH live on this fleet. A build script never touches the organism, "
     "its snapshots, or its services."),
    (r"\breboot\b|\bshutdown\b|\bhalt\b|\bpoweroff\b|\binit\s+\d",
     "nothing here restarts a machine"),
    (r"\bapt(-get)?\b|\bdpkg\b|\byum\b|\bdnf\b|\bsnap\s+install\b",
     "installing packages on a live box is a human decision"),
    (r"\bssh\b|\bscp\b|\brsync\b|\bsftp\b|\bnc\s|\bncat\b|\bcurl\b\s+[^|]*\|\s*(ba)?sh",
     "no pivoting off the build box, and no curl-pipe-shell"),
    (r"\bcrontab\b|\bat\s+now\b|\bsystemd-run\b",
     "nothing schedules itself to run later"),
    (r"\brm\s+-[rRf]*[rf][rRf]*\s+/(\s|$)|\brm\s+-[rRf]*\s+~(\s|/|$)",
     "a recursive delete of / or of the home directory is never a build step"),
    (r"\bmkfs\b|\bdd\s+if=.*of=/dev/|\bfdisk\b|\bparted\b",
     "nothing here writes to a block device"),
    (r"\bkill(all)?\b|\bpkill\b",
     "a build does not kill processes it did not start"),
    (r":\(\)\s*\{.*\};:", "fork bomb"),
)

_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")

# Directories that are never shipped -- a .git tree turns a 2 KB hello into 80 MB, and
# venvs and node_modules are worse.
_SKIP_DIRS = {".git", ".hg", ".svn", "__pycache__", "node_modules", ".venv", "venv",
              ".pytest_cache", ".mypy_cache", "build", "dist", ".idea", ".vs"}


def check_command(command: str) -> str:
    """Return the reason this command is refused, or '' if it may be put to the gate."""
    low = " " + str(command or "").lower() + " "
    if not low.strip():
        return "no command given"
    for pattern, reason in _FORBIDDEN:
        if re.search(pattern, low):
            return "REFUSED (%s): %s" % (re.search(pattern, low).group(0).strip(), reason)
    return ""


# ------------------------------------------------------------------ the transport
def _run(cmd: list, timeout: float, stdin_bytes: bytes = None) -> tuple:
    """ONE subprocess, argv, shell=False, always with a timeout. Never raises."""
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=timeout, input=stdin_bytes,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired:
        return -9, "", "timed out after %.0fs: %s" % (timeout, " ".join(cmd[:4]))
    except FileNotFoundError:
        return -1, "", "%s not found on PATH" % cmd[0]
    except Exception as exc:
        return -2, "", "%s: %s" % (type(exc).__name__, exc)
    return (p.returncode,
            p.stdout.decode("utf-8", "replace"),
            p.stderr.decode("utf-8", "replace"))


def _ssh(remote_cmd: str, timeout: float) -> tuple:
    """Run ONE line on the build host. The line is passed as a single argv element, so the
    local shell never sees it; the REMOTE shell does, which is what `make && ./a.out` needs
    -- and is exactly why check_command() ran first."""
    return _run(["ssh", "-o", "BatchMode=yes",
                 "-o", "ConnectTimeout=%d" % SSH_CONNECT_TIMEOUT,
                 "-o", "StrictHostKeyChecking=accept-new",
                 BUILD_HOST, remote_cmd], timeout)


def _pack(src: Path, tar_path: Path) -> dict:
    """tar.gz the source tree, skipping the noise, refusing anything that escapes its root."""
    total, count = 0, 0
    root = src.resolve()
    with tarfile.open(tar_path, "w:gz") as tf:
        for path in sorted(root.rglob("*")):
            rel_parts = path.relative_to(root).parts
            if any(p in _SKIP_DIRS for p in rel_parts):
                continue
            if path.is_symlink():
                # A symlink in a tree being shipped to a live box can point at /etc.
                return {"ok": False, "reason": "refusing to ship the symlink %s" % path}
            if path.is_dir():
                continue
            try:
                size = path.stat().st_size
            except OSError:
                continue
            total += size
            count += 1
            if total > MAX_TREE_BYTES:
                return {"ok": False, "reason": "the tree is over %d bytes -- a build input, "
                                               "not a data set" % MAX_TREE_BYTES}
            if count > MAX_TREE_FILES:
                return {"ok": False, "reason": "the tree has over %d files" % MAX_TREE_FILES}
            tf.add(str(path), arcname="/".join(rel_parts))
    return {"ok": True, "files": count, "bytes": total, "tar_bytes": tar_path.stat().st_size}


# ------------------------------------------------------------------ the door
def status() -> dict:
    """MEASURED: is the build host reachable, and what does it actually have on it?"""
    loaded = _load()
    gate = loaded["gate"]
    out = {"i_am": "almido_remote", "build_host": BUILD_HOST, "remote_root": REMOTE_ROOT,
           "gate_loaded": gate is not None,
           "gate_file": getattr(gate, "__file__", None),
           "audit_log": str(getattr(gate, "AUDIT_LOG", "")) if gate else None,
           "errors": loaded["errors"] or None,
           "nice": NICE, "max_seconds": MAX_SECONDS,
           "max_tree": "%d bytes / %d files" % (MAX_TREE_BYTES, MAX_TREE_FILES),
           "transport": "python tarfile -> scp -> tar on the far side (rsync is NOT "
                        "installed on this PC)",
           "refuses": [r for _p, r in _FORBIDDEN]}
    if gate is not None:
        try:
            out["stopped"] = bool(gate.is_stopped())
        except Exception as exc:
            out["stopped"] = "unreadable: %s" % exc
    rc, sout, serr = _ssh(
        "export PATH=%s:$PATH; echo HOST=$(hostname); gcc --version|head -1; "
        "cmake --version|head -1; nvcc --version|tail -1; python3 --version; "
        "df -h ~ | tail -1" % REMOTE_PATH, 25)
    out["reachable"] = rc == 0
    out["toolchain"] = [ln for ln in sout.splitlines() if ln.strip()] if rc == 0 else None
    if rc != 0:
        out["error"] = (serr or "rc=%d" % rc)[:300]
    out["verdict"] = ("ready" if (rc == 0 and gate is not None and out.get("stopped") is False)
                      else ("STOPPED" if out.get("stopped") else
                            ("NO GATE" if gate is None else "build host unreachable")))
    return out


def build(source_dir: str, name: str = "", command: str = "make",
          artifacts: list = None, timeout: int = 0, keep_remote: bool = True) -> dict:
    r"""Ship `source_dir` to the build host, run `command` in it, bring the answer back.

    Returns stdout, stderr and the real exit code -- never a summary of them. A build that
    failed must LOOK failed to the model that called it, or the model will carry on writing
    code against a compiler error it never saw."""
    t0 = time.time()
    src = Path(source_dir).expanduser()
    timeout = min(MAX_SECONDS, int(timeout or MAX_SECONDS))
    name = (name or src.name or "build").strip()

    if not _NAME_RE.match(name):
        return _refuse(name, "the build name becomes a directory on a live box: it must be "
                             "a plain token ([A-Za-z0-9._-], <=64 chars)")
    if not src.is_dir():
        return _refuse(str(src), "%s is not a directory" % src)
    bad = check_command(command)
    if bad:
        return _refuse(command, bad)
    for art in (artifacts or []):
        # THE HOLE THIS CLOSES, found 2026-09-11 09:12 by looking at eran4 rather than at the
        # suite: the character-class alone accepted "../../secret", because ".." is made
        # entirely of characters the class allows. The path then went straight into an scp
        # source, i.e. an artifact could be fetched from OUTSIDE the build directory. The
        # segment check is the actual fence; the character class only narrows what a segment
        # may be made of.
        parts = str(art).split("/")
        if any(p in ("", ".", "..") for p in parts) or not re.match(
                r"^[A-Za-z0-9_.*?\[\]-]+(/[A-Za-z0-9_.*?\[\]-]+)*$", str(art)):
            return _refuse(str(art), "an artifact is a relative path INSIDE the build dir: "
                                     "no leading '/', no '..' segment, no empty segment")

    loaded = _load()
    gate = loaded["gate"]
    if gate is None:
        return {"ok": False, "verdict": "BLOCK", "performed": False,
                "reason": "GATE UNAVAILABLE, so nothing is built: "
                          + "; ".join(loaded["errors"])[:400]}
    try:
        if gate.is_stopped():
            return _refuse(command, "STOP file present (%s)" % gate.STOP_FILE)
    except Exception as exc:
        return _refuse(command, "could not read the STOP file: %s" % exc)

    detail = "%s on %s: %s" % (name, BUILD_HOST, command)
    try:
        verdict, reason = gate.gate("command", "remote_build " + detail)
    except Exception as exc:
        return _refuse(detail, "gate raised %s: %s" % (type(exc).__name__, exc))
    if verdict != "ALLOW":
        return {"ok": False, "verdict": verdict, "reason": reason, "performed": False,
                "detail": detail,
                "note": "CONFIRM and BLOCK both stop the build. Ask Iddo."}

    remote_dir = "%s/%s" % (REMOTE_ROOT, name)
    out = {"ok": False, "verdict": verdict, "name": name, "host": BUILD_HOST,
           "remote_dir": remote_dir, "command": command,
           "ts": datetime.now().astimezone().isoformat(timespec="seconds")}

    tmp = Path(tempfile.mkdtemp(prefix="almido-build-"))
    try:
        tar_path = tmp / ("%s.tar.gz" % name)
        packed = _pack(src, tar_path)
        if not packed.get("ok"):
            return _refuse(str(src), packed["reason"])
        out["packed"] = packed

        rc, _o, err = _ssh("rm -rf %s && mkdir -p %s" % (remote_dir, remote_dir), 30)
        if rc != 0:
            out["reason"] = "could not prepare %s on %s: %s" % (remote_dir, BUILD_HOST, err[:300])
            return out
        rc, _o, err = _run(["scp", "-o", "BatchMode=yes",
                            "-o", "ConnectTimeout=%d" % SSH_CONNECT_TIMEOUT,
                            str(tar_path), "%s:%s/_src.tar.gz" % (BUILD_HOST, remote_dir)], 120)
        if rc != 0:
            out["reason"] = "scp failed: %s" % err[:300]
            return out
        rc, _o, err = _ssh("cd %s && tar -xzf _src.tar.gz && rm -f _src.tar.gz" % remote_dir, 60)
        if rc != 0:
            out["reason"] = "could not unpack on %s: %s" % (BUILD_HOST, err[:300])
            return out

        # nice + timeout on the FAR side too: a runaway compile must die on the box, not
        # merely stop being watched from here.
        line = ("cd %s && export PATH=%s:$PATH && nice -n %d timeout %d bash -lc %s"
                % (remote_dir, REMOTE_PATH, NICE, timeout, _q(command)))
        t1 = time.time()
        rc, sout, serr = _ssh(line, timeout + 30)
        out["exit_code"] = rc
        out["stdout"] = sout[-20000:]
        out["stderr"] = serr[-20000:]
        out["build_seconds"] = round(time.time() - t1, 2)
        if rc == 124:
            out["reason"] = "the build hit the %ds timeout on %s and was killed there" % (
                timeout, BUILD_HOST)
        out["ok"] = rc == 0

        if artifacts:
            # SYMLINK ASYMMETRY (WAVE A1 review finding #4, documented not fixed): _pack()
            # above refuses to SHIP a symlink from the local tree to the box (it could point
            # at /etc). There is no matching check here on the way BACK -- if `command` left
            # a symlink at `remote_dir/<art>` pointing outside remote_dir (e.g. at a dotfile
            # or key on BUILD_HOST), this scp follows it and copies whatever it points to.
            # Accepted as-is: `command` already ran on BUILD_HOST with exactly this scope
            # (it passed check_command() and the gate, and runs as the build user), so a
            # symlinked artifact discloses nothing the command could not already read and
            # print to stdout/stderr directly -- it is not a NEW privilege, just a second
            # route to one the command already had. Revisit if BUILD_HOST is ever shared
            # with a user/process this door should not be able to read as.
            got, missing = [], []
            dest = Path(os.environ.get("ALMIDO_BUILD_OUT", str(HERE / "workspace" / "builds"))) / name
            dest.mkdir(parents=True, exist_ok=True)
            for art in artifacts:
                local = dest / Path(str(art)).name
                rc2, _o2, err2 = _run(["scp", "-o", "BatchMode=yes",
                                       "-o", "ConnectTimeout=%d" % SSH_CONNECT_TIMEOUT,
                                       "%s:%s/%s" % (BUILD_HOST, remote_dir, art),
                                       str(local)], 120)
                if rc2 == 0 and local.exists():
                    got.append({"artifact": str(art), "local": str(local),
                                "bytes": local.stat().st_size})
                else:
                    missing.append({"artifact": str(art), "error": (err2 or "rc=%d" % rc2)[:200]})
            out["artifacts"] = got
            if missing:
                out["artifacts_missing"] = missing
            out["artifacts_dir"] = str(dest)

        if not keep_remote:
            _ssh("rm -rf %s" % remote_dir, 30)
            out["remote_cleaned"] = True
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    out["elapsed_s"] = round(time.time() - t0, 2)
    _audit_direct("command", "remote_build:%s rc=%s" % (detail, out.get("exit_code")),
                  "ALLOW" if out["ok"] else "BLOCK",
                  "built on %s" % BUILD_HOST if out["ok"] else "build failed on %s" % BUILD_HOST)
    return out


def _q(s: str) -> str:
    return "'" + str(s).replace("'", "'\\''") + "'"


# ------------------------------------------------------------------ the self-test
HELLO_C = """#include <stdio.h>
int main(void){ printf("ALMIDO remote_build: hello from %s\\n", "eran4"); return 0; }
"""

HELLO_CU = """#include <cstdio>
__global__ void k(int *o){ *o = 42; }
int main(){ printf("ALMIDO nvcc: compiled, arch ok\\n"); return 0; }
"""


def selftest(with_cuda: bool = True) -> dict:
    """Compile and RUN a hello on the build host, then compile a .cu with nvcc.

    This is the acceptance test for this tool, kept next to the tool so it can never drift
    away from it. It proves the whole chain -- pack, copy, unpack, compile, run, read the
    output back -- with output nobody can fake: the binary's own printf."""
    res = {"ts": datetime.now().astimezone().isoformat(timespec="seconds")}
    tmp = Path(tempfile.mkdtemp(prefix="almido-selftest-"))
    try:
        (tmp / "hello.c").write_text(HELLO_C, encoding="utf-8")
        r = build(str(tmp), "selftest-hello", "gcc -O2 -o hello hello.c && ./hello",
                  artifacts=["hello"], timeout=120)
        res["hello_c"] = {"ok": bool(r.get("ok")) and "hello from" in (r.get("stdout") or ""),
                          "exit_code": r.get("exit_code"),
                          "stdout": (r.get("stdout") or "").strip()[:300],
                          "stderr": (r.get("stderr") or "").strip()[:300],
                          "artifacts": r.get("artifacts"),
                          "reason": r.get("reason")}
        if with_cuda:
            cu = Path(tempfile.mkdtemp(prefix="almido-selftest-cu-"))
            try:
                (cu / "k.cu").write_text(HELLO_CU, encoding="utf-8")
                r2 = build(str(cu), "selftest-cuda", "nvcc -o k k.cu && echo NVCC_EXIT=$?",
                           artifacts=["k"], timeout=300)
                res["cuda"] = {"ok": bool(r2.get("ok")),
                               "exit_code": r2.get("exit_code"),
                               "stdout": (r2.get("stdout") or "").strip()[:300],
                               "stderr": (r2.get("stderr") or "").strip()[:400],
                               "artifacts": r2.get("artifacts"),
                               "reason": r2.get("reason")}
            finally:
                shutil.rmtree(cu, ignore_errors=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    parts = ["hello.c=%s" % ("VERIFIED" if res.get("hello_c", {}).get("ok") else "BROKEN")]
    if with_cuda:
        parts.append("nvcc=%s" % ("VERIFIED" if res.get("cuda", {}).get("ok") else "BROKEN"))
    res["summary"] = "; ".join(parts)
    res["ok"] = all(p.endswith("VERIFIED") for p in parts)
    return res


def _cli(argv: list) -> int:
    cmd = (argv[1] if len(argv) > 1 else "status").lower()
    if cmd == "status":
        print(json.dumps(status(), ensure_ascii=False, indent=1, default=str))
    elif cmd == "selftest":
        print(json.dumps(selftest(), ensure_ascii=False, indent=1, default=str))
    else:
        print("usage: almido_remote.py [status|selftest]", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli(sys.argv))
