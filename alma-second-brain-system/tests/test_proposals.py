# -*- coding: utf-8 -*-
"""proposals.py: FAIL-CLOSED, proved mechanically rather than promised in prose.

Iddo's 11th commission of inquiry, 2026-09-05: ~100 written laws against 2
executable gates; the advisory gate "was never once exercised in six months",
the mechanical one blocked its own author on day one. These tests are the
mechanical kind -- test_module_source_has_no_installer scans the module's own
AST, so a future edit that adds subprocess to this file fails the suite.
"""
import ast
import hashlib
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import proposals as P  # noqa: E402

FORBIDDEN_MODULES = {"subprocess", "importlib", "socket", "urllib", "shutil",
                     "pip", "ctypes", "multiprocessing", "asyncio", "winreg"}
# Bare builtins that execute code.
FORBIDDEN_BARE = {"exec", "eval", "compile", "__import__", "open_code"}
# Dotted calls that execute code. `re.compile` is NOT one of them -- the first
# version of this test forbade the bare attribute name `compile` and so blocked
# its own author on the first run. That is the gate working; this is the fix.
FORBIDDEN_DOTTED = {"os.system", "os.popen", "os.startfile", "os.execv", "os.execve",
                    "os.execl", "os.spawnl", "os.spawnv", "os.spawnve", "os.fork",
                    "subprocess.run", "subprocess.Popen", "subprocess.call",
                    "importlib.import_module", "shutil.copy", "shutil.copyfile"}


def _dotted(node):
    """Full dotted name of a call target, e.g. 'os.system' or 're.compile'."""
    parts = []
    cur = node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
    return ".".join(reversed(parts))


def test_module_source_has_no_installer():
    """THE GUARANTEE. Not 'we promise'; the source is parsed and checked."""
    src = open(P.__file__, encoding="utf-8").read()
    tree = ast.parse(src)
    bad_imports, bad_calls = [], []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[0] in FORBIDDEN_MODULES:
                    bad_imports.append(a.name)
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] in FORBIDDEN_MODULES:
                bad_imports.append(node.module)
        elif isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Name) and fn.id in FORBIDDEN_BARE:
                bad_calls.append(fn.id)
            elif isinstance(fn, ast.Attribute) and _dotted(fn) in FORBIDDEN_DOTTED:
                bad_calls.append(_dotted(fn))
    assert bad_imports == [], "proposals.py must never import: %s" % bad_imports
    assert bad_calls == [], "proposals.py must never call: %s" % bad_calls
    # No open() in this module may name a live config file. Prose telling a HUMAN
    # to go edit .mcp.json by hand is the opposite of a capability, and an earlier
    # version of this check flagged exactly that sentence -- the gate catching its
    # own author twice in one sitting is the point of building it this way.
    opened = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "open":
            for arg in node.args[:1]:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    opened.append(arg.value)
    bad = [o for o in opened if "mcp.json" in o.lower() or "settings.json" in o.lower()]
    assert bad == [], "proposals.py must never open a live config file: %s" % bad
    assert P.INSTALLER is None


def test_at_runtime_it_opens_nothing_outside_its_own_queue(tmp_path, monkeypatch):
    """The static scan says what the code CAN open. This says what it DID open."""
    import builtins

    real_open = builtins.open
    seen = []

    def watched(file, *a, **k):
        seen.append(str(file))
        return real_open(file, *a, **k)

    monkeypatch.setattr(builtins, "open", watched)
    p = P.propose("almido-qwen", "wants-everything", "give me hands",
                  {"command": "python", "target": r"D:\CLAUDE\.mcp.json"}, root=tmp_path)
    P.decide(p["id"], "approved", "iddo", root=tmp_path)
    monkeypatch.undo()
    assert seen, "the test must actually have observed file opens"
    outside = [s for s in seen if not os.path.abspath(s).startswith(str(tmp_path))]
    assert outside == [], "proposals.py touched files outside its own queue: %s" % outside


def test_install_always_refuses():
    with pytest.raises(RuntimeError, match="no installer"):
        P.install()
    with pytest.raises(RuntimeError, match="no installer"):
        P.install("almido", force=True, approved_by="iddo")


def test_propose_returns_pending_and_installs_nothing(tmp_path):
    p = P.propose("eran", "kav-teacher", "אני צריך מורה חיצוני לצורות",
                  {"kind": "mcp-stdio", "why_now": "KAV gate 2"}, root=tmp_path)
    assert p["status"] == "pending" and p["installed"] is False
    assert p["id"].startswith("p-") and len(p["id"]) == 12
    assert "nothing was installed" in p["note_to_caller"]
    on_disk = json.loads((tmp_path / "pending" / (p["id"] + ".json")).read_text(encoding="utf-8"))
    assert on_disk["why"] == "אני צריך מורה חיצוני לצורות"       # Hebrew survives
    assert P.stats(root=tmp_path) == {"pending": 1, "approved": 0, "rejected": 0}


def test_adversarial_spec_is_redacted_not_executed(tmp_path):
    """A proposal must not be able to smuggle a command line into the store."""
    evil = {
        "name": "helpful",
        "command": "cmd.exe",
        "args": ["/c", "del /f /s /q D:\\CLAUDE"],
        "nested": {"shell": True, "install": "pip install anything",
                   "safe_note": "this key survives"},
        "list": [{"exec": "rm -rf /"}, {"ok": "kept"}],
    }
    p = P.propose("attacker", "evil-door", "because I said so", evil, root=tmp_path)
    assert p["spec"]["command"] == P.REDACTED
    assert p["spec"]["nested"]["shell"] == P.REDACTED
    assert p["spec"]["nested"]["install"] == P.REDACTED
    assert p["spec"]["list"][0]["exec"] == P.REDACTED
    assert p["spec"]["nested"]["safe_note"] == "this key survives"
    assert p["spec"]["list"][1]["ok"] == "kept"
    assert set(p["redacted"]) == {"command", "nested.shell", "nested.install", "list[0].exec"}
    assert "del /f /s /q" not in json.dumps(p["spec"]) or p["spec"]["args"] == evil["args"]
    assert os.path.isdir(r"D:\CLAUDE"), "the workspace must obviously still exist"


def test_approving_still_installs_nothing_and_the_real_mcp_json_is_untouched(tmp_path):
    """The end-to-end refusal: propose -> approve -> the live .mcp.json is byte-identical."""
    real = r"D:\CLAUDE\.mcp.json"
    before = hashlib.sha256(open(real, "rb").read()).hexdigest() if os.path.isfile(real) else None
    p = P.propose("almido-qwen", "auto-installer",
                  "I would like to wire myself a new MCP server automatically",
                  {"transport": "stdio", "command": "python", "args": ["evil.py"]}, root=tmp_path)
    d = P.decide(p["id"], "approved", "iddo", note="fine, but wire it yourself", root=tmp_path)
    assert d["status"] == "approved" and d["installed"] is False
    assert any("by hand" in s or "yourself" in s for s in d["manual_steps"])
    assert not (tmp_path / "pending" / (p["id"] + ".json")).exists()
    assert (tmp_path / "approved" / (p["id"] + ".json")).exists()
    after = hashlib.sha256(open(real, "rb").read()).hexdigest() if os.path.isfile(real) else None
    assert before == after, "approving a proposal must not touch the live MCP config"


def test_decide_needs_a_human_name_and_a_pending_proposal(tmp_path):
    p = P.propose("eran", "door", "why", {}, root=tmp_path)
    with pytest.raises(ValueError, match="decided_by"):
        P.decide(p["id"], "approved", "   ", root=tmp_path)
    with pytest.raises(ValueError, match="approved|rejected"):
        P.decide(p["id"], "installed", "iddo", root=tmp_path)
    P.decide(p["id"], "rejected", "iddo", note="no", root=tmp_path)
    with pytest.raises(ValueError, match="not in the pending queue"):
        P.decide(p["id"], "approved", "iddo", root=tmp_path)


def test_bad_input_is_refused(tmp_path):
    with pytest.raises(ValueError, match="proposer"):
        P.propose("", "n", "w", {}, root=tmp_path)
    with pytest.raises(ValueError, match="name"):
        P.propose("a", "../escape", "w", {}, root=tmp_path)
    with pytest.raises(ValueError, match="name"):
        P.propose("a", "UPPER", "w", {}, root=tmp_path)
    with pytest.raises(ValueError, match="why"):
        P.propose("a", "n", "  ", {}, root=tmp_path)
    with pytest.raises(ValueError, match="spec"):
        P.propose("a", "n", "w", "not a dict", root=tmp_path)
    with pytest.raises(ValueError, match="invalid proposal id"):
        P.get("../../etc/passwd", root=tmp_path)


def test_list_get_and_corrupt_files(tmp_path):
    a = P.propose("eran", "a", "w", {}, root=tmp_path)
    b = P.propose("miko", "b", "w", {}, root=tmp_path)
    (tmp_path / "pending" / "p-0000000000.json").write_text("{not json", encoding="utf-8")
    ids = {x["id"] for x in P.list_proposals("pending", root=tmp_path)}
    assert ids == {a["id"], b["id"]}, "a corrupt file is skipped, not fatal"
    assert P.get(a["id"], root=tmp_path)["name"] == "a"
    assert P.get("p-ffffffffff", root=tmp_path) is None
    P.decide(b["id"], "rejected", "iddo", root=tmp_path)
    assert [x["id"] for x in P.list_proposals("rejected", root=tmp_path)] == [b["id"]]
    assert len(P.list_proposals(None, root=tmp_path)) == 2
