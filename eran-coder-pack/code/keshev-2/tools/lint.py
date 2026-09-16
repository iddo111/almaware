"""KESHEV 2 lint gates — every gate must be able to FIRE (--self-test).

Raw material: qwen3-coder-next-fp8's draft (harness/drafts/), reviewed and
reworked by the lead: gates now take an explicit file list (the draft
monkeypatched its own module for self-test), the Windows path-separator
endswith bug is gone (the draft's exemption check used forward slashes and
would have flagged configstore/interlock themselves), and G6 no longer
flags every '\\a' byte in the repo. Kept: the AST shape for G1 and the
regex families for G2/G4/G5/G6. See WORKERS-LOG.md.

THE SELF-TEST LAW (guard species: "written, wired, structurally unable to
fire"): `python tools/lint.py --self-test` feeds each gate a minimal
violation and FAILS unless every gate catches it. A lint gate that cannot
fire is not shipped. Plain runs exit non-zero on any violation.

Production surface tonight: k2/ only. harness/ is build tooling (it talks
to the 4D router; it is not the mic), tests/ are tests.

stdlib only.
"""
from __future__ import annotations

import ast
import re
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PRODUCTION_DIRS = ("k2",)

# The rival's mutex name, split so this file does not itself trip G5's
# string scan (the scan exempts only k2/interlock.py and this tool).
_RIVAL = "ALMAWARE_KESHEV" + "_SINGLE"
_G5_EXEMPT = ("interlock.py",)


def production_files(repo: Path = REPO) -> list[Path]:
    out: list[Path] = []
    for d in PRODUCTION_DIRS:
        base = repo / d
        if base.is_dir():
            out.extend(p for p in base.rglob("*.py")
                       if "__pycache__" not in p.parts)
    return sorted(out)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _lineno(source: str, pos: int) -> int:
    return source.count("\n", 0, pos) + 1


# ------------------------------------------------------------------ gates
# Every gate: (files) -> list of "path:line: message" strings.


def g1_no_silent_except(files: list[Path]) -> list[str]:
    """`except:` / `except Exception:` / `except BaseException:` whose body
    is only pass/.../continue — the CUDA_DLL_SKIPPED law: record, never
    swallow."""
    bad: list[str] = []
    for f in files:
        try:
            tree = ast.parse(_read(f), filename=str(f))
        except SyntaxError as exc:
            bad.append(f"{f}:{exc.lineno}: unparseable ({exc.msg})")
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            wide = node.type is None or (
                isinstance(node.type, ast.Name)
                and node.type.id in ("Exception", "BaseException"))
            if not wide:
                continue
            silent = all(
                isinstance(s, (ast.Pass, ast.Continue))
                or (isinstance(s, ast.Expr)
                    and isinstance(s.value, ast.Constant)
                    and s.value.value is ...)
                for s in node.body)
            if silent:
                bad.append(f"{f}:{node.lineno}: silent wide except "
                           f"(record it or narrow it)")
    return bad


_G2_FORBIDDEN = ("sounddevice", "pyaudio", "soundcard", "winsound",
                 "playsound", "pygame")


def g2_no_audio_capture(files: list[Path]) -> list[str]:
    """No audio libraries in production AT ALL tonight — KESHEV A holds the
    mic; this build must be structurally unable to open a device."""
    bad: list[str] = []
    for f in files:
        try:
            tree = ast.parse(_read(f), filename=str(f))
        except SyntaxError:
            continue                      # g1 reports unparseable files
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for n in names:
                root = n.split(".")[0]
                if root in _G2_FORBIDDEN:
                    bad.append(f"{f}:{node.lineno}: audio import {n!r} "
                               f"(no capture code in this build)")
    return bad


def g3_config_writes_only_in_configstore(files: list[Path]) -> list[str]:
    """Only k2/configstore.py may write config files (scar 39/42)."""
    bad: list[str] = []
    write_re = re.compile(
        r"""(json\.dump\s*\(|open\s*\([^)]*['"]w b?['"]|open\s*\([^)]*mode\s*=\s*['"]w)""".replace("w b?", "wb?"))
    config_re = re.compile(r"""['"][^'"]*config[^'"]*['"]""", re.IGNORECASE)
    for f in files:
        if f.name == "configstore.py":
            continue
        src = _read(f)
        for m in write_re.finditer(src):
            window = src[max(0, m.start() - 120): m.end() + 120]
            if config_re.search(window):
                bad.append(f"{f}:{_lineno(src, m.start())}: config write "
                           f"outside configstore")
    return bad


_G4_FORBIDDEN = ("torch", "tensorflow", "jax")


def g4_no_torch(files: list[Path]) -> list[str]:
    """No AI torch on the PC. Ever (standing law)."""
    bad: list[str] = []
    for f in files:
        try:
            tree = ast.parse(_read(f), filename=str(f))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for n in names:
                if n.split(".")[0] in _G4_FORBIDDEN:
                    bad.append(f"{f}:{node.lineno}: forbidden import {n!r}")
    return bad


def g5_no_createmutex_on_rival(files: list[Path]) -> list[str]:
    """A's mutex name may appear only in k2/interlock.py, and CreateMutexW
    near it is forbidden EVERYWHERE — creating A's name squats it and
    blocks A's next start (D-002). OpenMutexW is the only legal probe."""
    bad: list[str] = []
    for f in files:
        src = _read(f)
        for m in re.finditer(re.escape(_RIVAL), src):
            line = _lineno(src, m.start())
            if f.name not in _G5_EXEMPT:
                bad.append(f"{f}:{line}: rival mutex name outside interlock")
            window = src[max(0, m.start() - 300): m.start() + 300]
            if "CreateMutexW" in window:
                bad.append(f"{f}:{line}: CreateMutexW near the rival's "
                           f"mutex name — squatting A's name is forbidden")
    return bad


def g6_no_audio_output(files: list[Path]) -> list[str]:
    """Sacred Audio: no beep, no bell, no sound call sites, anywhere."""
    bad: list[str] = []
    call_re = re.compile(
        r"(winsound\.(Beep|PlaySound|MessageBeep)|MessageBeep\s*\(|"
        r"Console\.Beep|\\a)")
    for f in files:
        src = _read(f)
        for m in call_re.finditer(src):
            bad.append(f"{f}:{_lineno(src, m.start())}: audio output call "
                       f"site ({m.group(0)!r}) — Sacred Audio")
    return bad


GATES = {
    "G1-silent-except": g1_no_silent_except,
    "G2-audio-capture": g2_no_audio_capture,
    "G3-config-writes": g3_config_writes_only_in_configstore,
    "G4-torch": g4_no_torch,
    "G5-rival-mutex": g5_no_createmutex_on_rival,
    "G6-audio-output": g6_no_audio_output,
}

# Minimal violation per gate — the self-test feeds these and every gate
# must FIRE. Adding a gate without a firing sample is a build failure.
_SELF_TEST_SAMPLES = {
    "G1-silent-except": "try:\n    x = 1\nexcept Exception:\n    pass\n",
    "G2-audio-capture": "import sounddevice\n",
    "G3-config-writes": (
        "import json\n"
        "json.dump({}, open('config/k2.json', 'w'))\n"),
    "G4-torch": "import torch\n",
    "G5-rival-mutex": (
        "import ctypes\n"
        f"ctypes.windll.kernel32.CreateMutexW(None, True, "
        f"'Global\\\\{_RIVAL}')\n"),
    "G6-audio-output": "import winsound\nwinsound.Beep(440, 100)\n",
}


def run(files: list[Path] | None = None) -> dict[str, list[str]]:
    files = production_files() if files is None else files
    return {name: gate(files) for name, gate in GATES.items()}


def self_test() -> dict[str, bool]:
    """Each gate gets ONE temp file containing its violation and must
    return at least one finding for it. True = the gate fired."""
    fired: dict[str, bool] = {}
    with tempfile.TemporaryDirectory(prefix="k2lint-") as td:
        for name, gate in GATES.items():
            sample = Path(td) / f"sample_{name.split('-')[0].lower()}.py"
            sample.write_text(_SELF_TEST_SAMPLES[name], encoding="utf-8")
            fired[name] = bool(gate([sample]))
    return fired


def main(argv: list[str]) -> int:
    if "--self-test" in argv:
        fired = self_test()
        ok = True
        for name, hit in fired.items():
            print(f"  {name}: {'FIRES' if hit else 'CANNOT FIRE'}")
            ok = ok and hit
        print(f"self-test: {'6/6 gates fire' if ok else 'DEAD GATE FOUND'}")
        return 0 if ok else 2

    results = run()
    ok = True
    for name, violations in results.items():
        status = "PASS" if not violations else "FAIL"
        print(f"  {name}: {status}")
        for v in violations:
            print(f"    {v}")
            ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
