"""lint.py — the laws as grep. Exit 0 = clean, 1 = a law is broken.

Six gates, one per law that must stay greppable (A's tools/lint.py lineage):
  G1 no audio OUTPUT call site anywhere (Sacred Audio).
  G2 no Bluetooth mic name escapes _NEVER_MIC's shadow (lawbook only).
  G3 no clipboard code (typer law: we type, never paste-with-restore).
  G4 no `bash` invocation (ADDENDUM #3: WSL is broken on this PC).
  G5 journal.event() in app/ uses only VOCAB names (closed vocabulary).
  G6 no audio-library import outside main.py (capture stays injectable).

Run:  python tools/lint.py        (--self-test proves every gate CAN fire)
"""
from __future__ import annotations

import ast
import io
import pathlib
import re
import sys
import tokenize

ROOT = pathlib.Path(__file__).resolve().parents[1]
APP = ROOT / "app"
sys.path.insert(0, str(ROOT))
from app.journal import VOCAB  # noqa: E402 — the closed vocabulary, one import


def code_only(src: str) -> str:
    """Source with comments and docstrings removed — the laws bind CODE;
    a docstring explaining why clipboard code is forbidden must not trip
    the clipboard gate (it did, twice, tonight)."""
    out: list[str] = []
    prev_end = (1, 0)
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(src).readline))
    except tokenize.TokenizeError:
        return src
    doc_starts: set[int] = set()
    try:
        tree = ast.parse(src)
        for node in ast.walk(tree):
            body = getattr(node, "body", None)
            if not isinstance(body, list):     # ast.Lambda.body is a node
                continue
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                doc_starts.add(body[0].lineno)
    except SyntaxError:
        pass
    for tok in tokens:
        if tok.type == tokenize.COMMENT:
            continue
        if tok.type == tokenize.STRING and tok.start[0] in doc_starts:
            continue
        out.append(tok.string)
    return " ".join(out)

AUDIO_OUT = re.compile(
    r"winsound|playsound|PlaySound|Beep\(|MessageBeep|pyaudio\.PyAudio\(\)\.open\([^)]*output",
    re.I)
CLIPBOARD = re.compile(r"clipboard|OpenClipboard|SetClipboardData|pyperclip", re.I)
BASH = re.compile(r"[\"'](?:bash|wsl)(?:\.exe)?[\"']", re.I)
AUDIO_IMPORT = re.compile(r"^\s*(?:import|from)\s+(?:sounddevice|pyaudio)\b", re.M)
NEVER_NAMES = re.compile(r"WH-1000|Hands-Free|AirPods", re.I)


def py_files() -> list[pathlib.Path]:
    return [p for p in APP.rglob("*.py")]


def fail(gate: str, path: pathlib.Path, detail: str) -> str:
    return f"{gate} BROKEN {path.relative_to(ROOT)}: {detail}"


def g1_no_audio_output(files) -> list[str]:
    return [fail("G1", p, m.group(0))
            for p in files
            for m in [AUDIO_OUT.search(code_only(p.read_text(encoding="utf-8")))] if m]


def g2_never_mic_only_in_lawbook(files) -> list[str]:
    out = []
    for p in files:
        if p.name == "lawbook.py":
            continue
        if NEVER_NAMES.search(code_only(p.read_text(encoding="utf-8"))):
            out.append(fail("G2", p, "a forbidden-device name outside lawbook"))
    return out


def g3_no_clipboard(files) -> list[str]:
    return [fail("G3", p, m.group(0))
            for p in files
            for m in [CLIPBOARD.search(code_only(p.read_text(encoding="utf-8")))] if m]


def g4_no_bash(files) -> list[str]:
    return [fail("G4", p, m.group(0))
            for p in files
            for m in [BASH.search(code_only(p.read_text(encoding="utf-8")))] if m]


def g5_journal_vocab(files) -> list[str]:
    out = []
    for p in files:
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "event"
                    and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)):
                name = node.args[0].value
                if name not in VOCAB:
                    out.append(fail("G5", p, f"event {name!r} not in VOCAB"))
    return out


def g6_audio_import_only_in_main(files) -> list[str]:
    return [fail("G6", p, "audio library imported outside main.py")
            for p in files
            if p.name != "main.py"
            and AUDIO_IMPORT.search(p.read_text(encoding="utf-8"))]


GATES = (g1_no_audio_output, g2_never_mic_only_in_lawbook, g3_no_clipboard,
         g4_no_bash, g5_journal_vocab, g6_audio_import_only_in_main)


def self_test() -> int:
    """Every gate must fire on a poisoned fixture — a lint that cannot fail
    is species #1 wearing a lint costume."""
    import tempfile
    poison = {
        "g1.py": "import winsound\n",
        "g2.py": "x = 'WH-1000XM4'\n",
        "g3.py": "import pyperclip\n",
        "g4.py": "cmd = ['bash', '-lc']\n",
        "g5.py": "j.event('MADE_UP_EVENT', x=1)\n",
        "g6.py": "import sounddevice\n",
    }
    with tempfile.TemporaryDirectory() as td:
        d = pathlib.Path(td)
        files = []
        for name, src in poison.items():
            f = d / name
            f.write_text(src, encoding="utf-8")
            files.append(f)
        global ROOT
        old_root = ROOT
        ROOT = d.parent  # so relative_to works
        try:
            fired = [bool(g([f])) for g, f in zip(GATES, files)]
        finally:
            ROOT = old_root
    if all(fired):
        print("SELF-TEST PASS — all 6 gates fire on poison")
        return 0
    print(f"SELF-TEST FAIL — gates fired: {fired}")
    return 1


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    files = py_files()
    problems: list[str] = []
    for gate in GATES:
        problems.extend(gate(files))
    if problems:
        print("\n".join(problems))
        return 1
    print(f"LINT PASS — 6 gates clean over {len(files)} app files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
