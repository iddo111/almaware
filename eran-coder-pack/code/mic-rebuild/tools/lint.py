#!/usr/bin/env python3
"""KESHEV lint gates — K0 (PHASE2-DESIGN.md sections 1, 5, 8, K0 row).

Every gate exists because of a scar in PHASE1-INQUIRY.md section 2:

  G1 except-pass        scar 17/18 — `except: pass` was silent speech loss.
  G2 initial_prompt     scar 30    — context fed back = regurgitated transcripts.
  G3 json.dump          scars 39-40 — write-on-exit config corruption; the ONLY
                                     legal json.dump call site is client/configstore.py.
  G4 *.bak* files       scar 42    — the 22-.bak swamp; LKG is the git tag, period.
  G5 torch under client scar 47    — no torch on the PC, ever.
  G6 audio output       scar 22    — Sacred Audio: no play/OutputStream call site
                                     may exist anywhere in the repo.

Exit codes: 0 = clean, 1 = violations (each printed), 2 = usage/internal error.
`--self-test` proves every gate fires on a synthetic violation (exit 0 only if
all gates fired AND a clean fixture produced zero findings).
"""
from __future__ import annotations

import argparse
import ast
import re
import sys
import tempfile
from pathlib import Path

SELF = Path(__file__).resolve()
REPO_ROOT = SELF.parent.parent

# Directories never scanned (state/ holds transcripts — git-ignored; _genizah = archives)
EXCLUDE_DIRS = {".git", "__pycache__", "state", "_genizah", ".venv", "venv", "node_modules", ".pytest_cache"}

# Token gates skip this file (it defines the patterns) — AST gates still apply to it.
TOKEN_SCAN_SKIP = {SELF}

# G2 — scar 30
RE_INITIAL_PROMPT = re.compile(r"\binitial_prompt\b")
# G6 — scar 22: sounddevice is capture-only; no output call site may exist.
RE_AUDIO_OUTPUT = re.compile(
    r"\bOutputStream\b|\bsounddevice\s*\.\s*play\b|\bsd\s*\.\s*play\b|\bwinsound\b|\bplaysound\b"
)
# G3 — the one legal json.dump call site
CONFIGSTORE_REL = Path("client") / "configstore.py"


def iter_files(root: Path, suffix: str | None = ".py"):
    for p in sorted(root.rglob("*")):
        if any(part in EXCLUDE_DIRS for part in p.relative_to(root).parts):
            continue
        if not p.is_file():
            continue
        if suffix is not None and p.suffix != suffix:
            continue
        yield p


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def _rel(root: Path, p: Path) -> str:
    try:
        return str(p.relative_to(root))
    except ValueError:
        return str(p)


# ---------------------------------------------------------------- gates

def gate_except_pass(root: Path) -> list[str]:
    """G1: an except handler whose entire body is `pass` (scar 17/18)."""
    out = []
    for p in iter_files(root):
        src = _read(p)
        try:
            tree = ast.parse(src, filename=str(p))
        except SyntaxError as e:
            out.append(f"G1 {_rel(root, p)}:{e.lineno}: file does not parse ({e.msg}) — unparseable python is a violation")
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                    out.append(f"G1 {_rel(root, p)}:{node.lineno}: except-with-bare-pass (silent drop, scar 17/18)")
    return out


def gate_initial_prompt(root: Path) -> list[str]:
    """G2: the token initial_prompt anywhere in python source (scar 30)."""
    out = []
    for p in iter_files(root):
        if p.resolve() in TOKEN_SCAN_SKIP:
            continue
        for i, line in enumerate(_read(p).splitlines(), 1):
            if RE_INITIAL_PROMPT.search(line):
                out.append(f"G2 {_rel(root, p)}:{i}: initial_prompt is banned (scar 30)")
    return out


def gate_json_dump(root: Path) -> list[str]:
    """G3: json.dump call outside client/configstore.py (scars 39-40).

    json.dumps (string form) is allowed — the ban is on the file-writing form
    that produced write-on-exit config corruption.
    """
    out = []
    allowed = (root / CONFIGSTORE_REL).resolve()
    for p in iter_files(root):
        if p.resolve() == allowed:
            continue
        try:
            tree = ast.parse(_read(p), filename=str(p))
        except SyntaxError:
            continue  # G1 already reports unparseable files
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "dump"
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "json"):
                out.append(f"G3 {_rel(root, p)}:{node.lineno}: json.dump outside configstore (scars 39-40)")
    return out


def gate_bak_files(root: Path) -> list[str]:
    """G4: any *.bak* file in the repo tree (scar 42)."""
    out = []
    for p in iter_files(root, suffix=None):
        if re.search(r"\.bak", p.name, re.IGNORECASE):
            out.append(f"G4 {_rel(root, p)}: .bak file — LKG is the git tag `lkg`, nothing else (scar 42)")
    return out


def gate_torch_client(root: Path) -> list[str]:
    """G5: any torch import under client/ (scar 47). common/ is included
    because the client imports it."""
    out = []
    for sub in ("client", "common"):
        d = root / sub
        if not d.is_dir():
            continue
        for p in iter_files(d):
            try:
                tree = ast.parse(_read(p), filename=str(p))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                mods = []
                if isinstance(node, ast.Import):
                    mods = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    mods = [node.module]
                for m in mods:
                    if m == "torch" or m.startswith("torch."):
                        out.append(f"G5 {sub}/{_rel(d, p)}:{node.lineno}: torch import on the PC (scar 47)")
    return out


def gate_audio_output(root: Path) -> list[str]:
    """G6: any audio-output call site anywhere in the repo (scar 22, Sacred Audio)."""
    out = []
    for p in iter_files(root):
        if p.resolve() in TOKEN_SCAN_SKIP:
            continue
        for i, line in enumerate(_read(p).splitlines(), 1):
            if RE_AUDIO_OUTPUT.search(line):
                out.append(f"G6 {_rel(root, p)}:{i}: audio-output call site (Sacred Audio, scar 22)")
    return out


GATES = [
    ("G1 except-pass", gate_except_pass),
    ("G2 initial_prompt", gate_initial_prompt),
    ("G3 json.dump outside configstore", gate_json_dump),
    ("G4 *.bak* files", gate_bak_files),
    ("G5 torch under client/", gate_torch_client),
    ("G6 audio output anywhere", gate_audio_output),
]


def run_all(root: Path) -> list[str]:
    findings = []
    for _, fn in GATES:
        findings.extend(fn(root))
    return findings


# ---------------------------------------------------------------- self-test

def self_test() -> int:
    """Prove each gate FIRES on a synthetic violation and stays quiet on a clean file."""
    failures = []
    with tempfile.TemporaryDirectory(prefix="keshev-lint-selftest-") as td:
        fx = Path(td)
        (fx / "client").mkdir()
        # one violation per gate — banned tokens assembled by concatenation so
        # this source file itself never contains them.
        ip = "initial" + "_prompt"
        (fx / "v1.py").write_text("try:\n    x = 1\nexcept Exception:\n    pass\n", encoding="utf-8")
        (fx / "v2.py").write_text(f"opts = {{'{ip}': ctx}}\n", encoding="utf-8")
        (fx / "v3.py").write_text("import json\njson." + "dump(cfg, fh)\n", encoding="utf-8")
        (fx / ("config.json" + ".bak-20260812")).write_text("{}", encoding="utf-8")
        (fx / "client" / "v5.py").write_text("import " + "torch\n", encoding="utf-8")
        (fx / "v6.py").write_text("stream = sd." + "play(buf)\n", encoding="utf-8")
        (fx / "clean.py").write_text(
            "import json\n\ndef ok():\n    try:\n        return json.dumps({'a': 1})\n"
            "    except ValueError as e:\n        raise RuntimeError('loud') from e\n",
            encoding="utf-8",
        )
        expect = {"G1": "v1.py", "G2": "v2.py", "G3": "v3.py", "G4": ".bak", "G5": "v5.py", "G6": "v6.py"}
        findings = run_all(fx)
        for code, needle in expect.items():
            hits = [f for f in findings if f.startswith(code) and needle in f]
            status = "FIRED" if hits else "DID NOT FIRE"
            print(f"  {code}: {status}" + (f" -> {hits[0]}" if hits else ""))
            if not hits:
                failures.append(code)
        clean_hits = [f for f in findings if "clean.py" in f]
        if clean_hits:
            failures.append("false-positive")
            print(f"  FALSE POSITIVE on clean.py: {clean_hits}")
        else:
            print("  clean.py: no findings (no false positive)")
    if failures:
        print(f"SELF-TEST FAIL: {failures}")
        return 1
    print(f"SELF-TEST PASS: {len(GATES)}/{len(GATES)} gates fire, zero false positives")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="KESHEV lint gates (K0)")
    ap.add_argument("--root", type=Path, default=REPO_ROOT, help="tree to scan (default: repo root)")
    ap.add_argument("--self-test", action="store_true", help="prove each gate fires; exit 0 only on full pass")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()

    root = args.root.resolve()
    if not root.is_dir():
        print(f"lint: not a directory: {root}", file=sys.stderr)
        return 2
    findings = run_all(root)
    if findings:
        print(f"LINT FAIL — {len(findings)} violation(s):")
        for f in findings:
            print("  " + f)
        return 1
    print(f"LINT PASS — {len(GATES)} gates clean over {root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
