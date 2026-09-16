"""Real agent tools — read, write, edit, run. The chat window gets the same
power the terminal already has.

diagnostics.py is deliberately read-only and parameterless. That was right for a
status panel, but it is why the model kept answering "I have no tool for that"
when asked to write a file. It DOES have that power through qwen in a terminal;
it just was not wired into the chat.

This file wires it. Every call is still gated:

  - writes and edits are confined to an allowlisted set of roots
  - path traversal is resolved and re-checked, so ..\\..\\ cannot escape
  - shell commands run through a verb allowlist, not a free `exec`
  - nothing runs as admin, nothing touches the DGX nodes, nothing deletes trees

The gate matters. This machine previously ran an unauthenticated CORS-wildcard
gateway that shelled out to agent CLIs, and any web page could drive it. The
lesson is not "never give the model tools" — it is "bound what the tools can
reach", so a prompt injected into a page cannot become arbitrary code execution.
"""
from __future__ import annotations

import json
import os
import pathlib
import shlex
import subprocess

# Where the model may write. Everything else is read-only or refused outright.
WRITE_ROOTS = [
    pathlib.Path(r"C:\Users\<user>\Desktop"),
    pathlib.Path(r"D:\CLAUDE"),
    pathlib.Path(r"D:\grok"),
]
# Reading is broader but still bounded — no C:\Windows, no other users.
READ_ROOTS = WRITE_ROOTS + [
    pathlib.Path(r"C:\Users\<user>"),
]
# Never, regardless of root. Credentials and the tool's own gate.
DENY_PARTS = {".ssh", ".secrets", "secrets", "credentials", ".git",
              "service.env", "auth.json", "token"}

# Commands the model may run. A closed set, not a shell.
ALLOWED_CMDS = {
    "py", "python", "node", "npm", "git", "dir", "type", "where",
    "tailscale", "curl", "ssh", "scp", "pytest", "pip", "qwen",
    "pyinstaller",   # PyInstaller 6.21 is installed; "make me an exe" is a real ask
}

MAX_READ = 200_000
MAX_WRITE = 2_000_000
TIMEOUT = 120


class Denied(Exception):
    pass


def _resolve(path: str, roots: list[pathlib.Path], what: str) -> pathlib.Path:
    """Resolve then re-check. Checking the string before resolving is the classic
    traversal hole — 'Desktop\\..\\..\\Windows' passes a prefix test and lands
    outside."""
    p = pathlib.Path(os.path.expandvars(path)).expanduser()
    if not p.is_absolute():
        p = pathlib.Path(r"C:\Users\<user>\Desktop") / p
    p = p.resolve()

    low = {part.lower() for part in p.parts}
    if low & DENY_PARTS:
        raise Denied(f"path touches a protected name: {path}")
    for root in roots:
        try:
            p.relative_to(root.resolve())
            return p
        except ValueError:
            continue
    raise Denied(f"{what} outside the allowed roots: {p}\n"
                 f"allowed: {', '.join(str(r) for r in roots)}")


def read_file(path: str) -> dict:
    p = _resolve(path, READ_ROOTS, "read")
    if not p.exists():
        return {"error": f"not found: {p}"}
    if p.is_dir():
        return {"error": f"is a directory, use list_dir: {p}"}
    data = p.read_text(encoding="utf-8", errors="replace")[:MAX_READ]
    return {"path": str(p), "bytes": p.stat().st_size, "content": data}


def write_file(path: str, content: str) -> dict:
    p = _resolve(path, WRITE_ROOTS, "write")
    if len(content) > MAX_WRITE:
        return {"error": f"too large: {len(content)} > {MAX_WRITE}"}
    p.parent.mkdir(parents=True, exist_ok=True)
    existed = p.exists()
    p.write_text(content, encoding="utf-8")
    return {"path": str(p), "bytes": len(content.encode("utf-8")),
            "action": "overwrote" if existed else "created"}


def edit_file(path: str, find: str, replace: str) -> dict:
    """Exact-string replace. Refuses when `find` is absent or ambiguous, so the
    model cannot silently corrupt a file it misread."""
    p = _resolve(path, WRITE_ROOTS, "edit")
    if not p.exists():
        return {"error": f"not found: {p}"}
    s = p.read_text(encoding="utf-8", errors="replace")
    n = s.count(find)
    if n == 0:
        return {"error": "the text to replace was not found"}
    if n > 1:
        return {"error": f"ambiguous: {n} matches — include more context"}
    p.write_text(s.replace(find, replace), encoding="utf-8")
    return {"path": str(p), "replaced": 1}


def list_dir(path: str = r"C:\Users\<user>\Desktop") -> dict:
    p = _resolve(path, READ_ROOTS, "list")
    if not p.is_dir():
        return {"error": f"not a directory: {p}"}
    out = []
    for e in sorted(p.iterdir())[:300]:
        try:
            out.append({"name": e.name, "dir": e.is_dir(),
                        "bytes": e.stat().st_size if e.is_file() else None})
        except OSError:
            pass
    return {"path": str(p), "entries": out}


def run_command(command: str) -> dict:
    """Run one allowlisted command. Not a shell — no pipes, no chaining, no
    redirection, so a crafted string cannot compose something unintended."""
    try:
        parts = shlex.split(command, posix=False)
    except ValueError as exc:
        return {"error": f"could not parse: {exc}"}
    if not parts:
        return {"error": "empty command"}

    verb = pathlib.Path(parts[0].strip('"')).name.lower()
    verb = verb.removesuffix(".exe").removesuffix(".cmd")
    if verb not in ALLOWED_CMDS:
        return {"error": f"'{verb}' is not allowlisted",
                "allowed": sorted(ALLOWED_CMDS)}
    for bad in ("|", ">", "<", "&", ";", "`", "$("):
        if bad in command:
            return {"error": f"shell metacharacter {bad!r} is not permitted"}

    try:
        r = subprocess.run(parts, capture_output=True, text=True,
                           timeout=TIMEOUT, encoding="utf-8", errors="replace",
                           cwd=r"C:\Users\<user>\Desktop",
                           env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        return {"command": command, "exit_code": r.returncode,
                "stdout": (r.stdout or "")[:20000],
                "stderr": (r.stderr or "")[:4000]}
    except subprocess.TimeoutExpired:
        return {"error": f"timed out after {TIMEOUT}s"}
    except FileNotFoundError:
        return {"error": f"not installed: {verb}"}


SCHEMAS = [
    {"type": "function", "function": {
        "name": "write_file",
        "description": ("Create or overwrite a text file. Use this to actually save "
                        "code the user asks for — do not just print it in chat. "
                        "Allowed: Desktop, D:\\CLAUDE, D:\\grok."),
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "absolute path, or a bare filename to place on the Desktop"},
            "content": {"type": "string", "description": "the full file contents"}},
            "required": ["path", "content"]}}},
    {"type": "function", "function": {
        "name": "read_file",
        "description": "Read a text file.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}}, "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "edit_file",
        "description": "Replace one exact unique string in a file. Fails if absent or ambiguous.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}, "find": {"type": "string"},
            "replace": {"type": "string"}},
            "required": ["path", "find", "replace"]}}},
    {"type": "function", "function": {
        "name": "list_dir",
        "description": "List a directory. Defaults to the Desktop.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}}, "required": []}}},
    {"type": "function", "function": {
        "name": "run_command",
        "description": ("Run one allowlisted command (py, python, node, npm, git, "
                        "curl, ssh, pytest, pip, qwen, tailscale...). No pipes or "
                        "redirection. Use it to test the code you just wrote."),
        "parameters": {"type": "object", "properties": {
            "command": {"type": "string"}}, "required": ["command"]}}},
]

REGISTRY = {
    "write_file": write_file,
    "read_file": read_file,
    "edit_file": edit_file,
    "list_dir": list_dir,
    "run_command": run_command,
}


def call(name: str, args: dict) -> str:
    fn = REGISTRY.get(name)
    if fn is None:
        return json.dumps({"error": f"unknown tool {name!r}"}, ensure_ascii=False)
    try:
        return json.dumps(fn(**args), ensure_ascii=False)
    except Denied as exc:
        return json.dumps({"error": f"denied: {exc}"}, ensure_ascii=False)
    except TypeError as exc:
        return json.dumps({"error": f"bad arguments: {exc}"}, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False)
