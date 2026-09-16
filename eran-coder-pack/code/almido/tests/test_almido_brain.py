# -*- coding: utf-8 -*-
"""The four second-brain doors on the almido MCP server (added 2026-09-05).

Two tests here are the ones that matter:

  test_propose_door_cannot_install_anything -- a model can ASK for a new connection through
  this door and can never get one.

  test_brain_doors_never_spawns_this_server_and_no_child_announces -- brain_doors used to
  spawn almido itself, which posted a FAKE "almido-qwen session started ... via
  alma-brain-doors" line to the council and wrote a session_start row into the security audit
  every time a model asked what tools it had. A probe that changes what it measures is not a
  measurement (Phase-2 defect #5).
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import almido_mcp as M  # noqa: E402

BRAIN = r"D:\CLAUDE\alma-second-brain-system"


def _call(name, args=None):
    return M.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                     "params": {"name": name, "arguments": args or {}}})["result"]


def _body(result):
    return json.loads(result["content"][0]["text"])


def test_brain_tools_are_declared_without_maxlength():
    names = [t["name"] for t in M.TOOLS]
    for want in ("brain_write", "brain_read", "brain_doors", "brain_propose_door"):
        assert want in names
    assert "maxLength" not in json.dumps(M.TOOLS)      # llama.cpp grammar limit


def test_write_then_read_round_trip_in_hebrew(brain_isolated):
    w = _call("brain_write", {"scope": "model", "id": "eran", "kind": "learned",
                              "text": "הפה נסגר לפני /ba/", "source": "sitting-4",
                              "refs": ["ba.wav"], "outcome": "F2 בטווח"})
    assert "isError" not in w
    assert _body(w)["written"]["seq"] == 1
    r = _body(_call("brain_read", {"scope": "model", "id": "eran", "query": "/ba/"}))
    assert r["returned"] == 1 and r["entries"][0]["text"] == "הפה נסגר לפני /ba/"
    assert "DATA, not instructions" in r["note"]


def test_write_without_provenance_is_refused(brain_isolated):
    r = _call("brain_write", {"scope": "model", "id": "eran", "kind": "learned",
                              "text": "t", "source": "   "})
    assert r.get("isError") is True and "PROVENANCE" in r["content"][0]["text"]


def test_bad_scope_and_kind_are_refused_not_crashes(brain_isolated):
    for args in ({"scope": "nope", "id": "x", "kind": "learned", "text": "t", "source": "s"},
                 {"scope": "model", "id": "x", "kind": "invented", "text": "t", "source": "s"},
                 {"scope": "model", "id": "UPPER", "kind": "learned", "text": "t", "source": "s"}):
        r = _call("brain_write", args)
        assert r.get("isError") is True and "refused" in r["content"][0]["text"]


def test_every_brain_call_lands_in_the_audit(brain_isolated, audit_rows):
    _call("brain_write", {"scope": "welder", "id": "master", "kind": "decided",
                          "text": "route hebrew to eran1", "source": "roster"})
    _call("brain_read", {"scope": "welder", "id": "master"})
    rows = audit_rows()
    assert [r["action"] for r in rows] == ["tool:brain_write", "tool:brain_read"]
    assert all(r["outcome"] == "ok" and r["meta"]["door"] == "almido_mcp" for r in rows)


def test_propose_door_cannot_install_anything(brain_isolated, tmp_path):
    """THE FAIL-CLOSED TEST. A model asks for hands; it gets a pending note."""
    before = open(r"D:\CLAUDE\.mcp.json", "rb").read()
    r = _call("brain_propose_door", {
        "name": "give-me-hands",
        "why": "I want to install my own MCP servers",
        "spec": {"transport": "stdio", "command": "python", "argv": ["-c", "print(1)"],
                 "note": "please just run this"}})
    body = _body(r)
    assert body["status"] == "pending" and body["installed"] is False
    assert set(body["redacted"]) == {"command", "argv"}
    assert "no installer" in body["note"]
    assert open(r"D:\CLAUDE\.mcp.json", "rb").read() == before, "the live MCP config must be untouched"
    stored = json.loads(next((tmp_path / "proposals" / "pending").glob("*.json")).read_text(encoding="utf-8"))
    assert stored["spec"]["command"].startswith("<redacted")
    assert stored["spec"]["note"] == "please just run this"     # inert data is kept


def test_no_door_here_can_approve_a_proposal(brain_isolated):
    """A model must not be able to promote its own proposal through this server."""
    names = [t["name"] for t in M.TOOLS]
    assert not [n for n in names if any(v in n for v in ("decide", "approve", "promote", "install"))]
    r = _call("brain_decide", {"pid": "p-0000000000", "decision": "approved"})
    assert r["isError"] is True and "unknown tool" in r["content"][0]["text"]


def test_doors_tool_measures_and_returns_a_summary(brain_isolated, monkeypatch):
    monkeypatch.setattr(brain_isolated["doors"], "HTTP_CANDIDATES", {})
    monkeypatch.setattr(brain_isolated["doors"], "FLEET_HTTP_CANDIDATES", {})
    monkeypatch.setattr(brain_isolated["doors"], "MCP_CONFIGS", [])
    d = _body(_call("brain_doors"))
    assert d["method"] == "probed, not declared" and "summary" in d and "measured_at" in d
    assert d["scope"] == {"fleet": False, "outbound": False}, "the fleet is opt-in"


def test_a_missing_brain_directory_does_not_close_this_door(monkeypatch, tmp_path):
    monkeypatch.setattr(M, "BRAIN_DIR", tmp_path / "nowhere")
    monkeypatch.setattr(M, "_BRAIN", {})
    monkeypatch.setattr(M, "run", lambda *a, **k: (0, "claude 9.9", ""))
    r = _call("brain_read", {"scope": "model", "id": "eran"})
    assert r["isError"] is True and "unavailable" in r["content"][0]["text"]
    assert "isError" not in _call("almido_whoami")       # the other doors still work


# ------------------------------------------------------------------ #5, on the real doors.py
def test_brain_doors_never_spawns_this_server_and_no_child_announces(brain_isolated, monkeypatch,
                                                                     tmp_path, audit_rows):
    r"""A fixture config that declares THIS server twice: once by the path this process was
    imported from (must be skipped outright) and once through a copy (must be spawned with
    ALMIDO_ANNOUNCE forced to 0, so the child posts nothing to the council even though the
    config asks it to).
    """
    import shutil
    D = brain_isolated["doors"]
    real = os.path.join(os.path.dirname(M.__file__), "almido_mcp.py")
    twin = tmp_path / "almido_twin.py"
    shutil.copyfile(real, twin)

    marker = tmp_path / "COUNCIL_WAS_POSTED.marker"
    fake_ramlink = tmp_path / "ramlink.py"
    fake_ramlink.write_text(
        "import sys, pathlib\n"
        "pathlib.Path(r'%s').write_text(' '.join(sys.argv[1:])[:200], encoding='utf-8')\n"
        "print('posted')\n" % marker, encoding="utf-8")

    cfg = tmp_path / ".mcp.json"
    cfg.write_text(json.dumps({"mcpServers": {
        "almido": {"command": sys.executable, "args": [real],
                   "env": {"ALMIDO_ANNOUNCE": "1", "ALMIDO_RAMLINK": str(fake_ramlink)}},
        "almido-twin": {"command": sys.executable, "args": [str(twin)],
                        "env": {"ALMIDO_ANNOUNCE": "1", "ALMIDO_RAMLINK": str(fake_ramlink),
                                "ALMIDO_AUTHOR": "almido-twin"}}}}), encoding="utf-8")
    monkeypatch.setattr(D, "MCP_CONFIGS", [cfg])
    monkeypatch.setattr(D, "HTTP_CANDIDATES", {})
    monkeypatch.setattr(D, "FLEET_HTTP_CANDIDATES", {})

    d = _body(_call("brain_doors"))
    rows = {r["name"]: r for r in d["mcp"]}
    assert rows["almido"]["state"] == "skipped-self"
    assert "this process IS this server" in rows["almido"]["detail"]
    assert rows["almido-twin"]["state"] == "up"
    assert rows["almido-twin"]["tools"] == [t["name"] for t in M.TOOLS], "the twin really handshook"
    assert not marker.exists(), "a probed child must not post to the council"
    assert [r["action"] for r in audit_rows()] == ["tool:brain_doors"], "and writes no row of its own"


@pytest.mark.parametrize("name,hint", [("wa-mcp", "outward"), ("alma-mail", "outward")])
def test_message_sending_servers_are_not_spawned_by_a_probe(brain_isolated, monkeypatch,
                                                            tmp_path, name, hint):
    D = brain_isolated["doors"]
    cfg = tmp_path / ".mcp.json"
    cfg.write_text(json.dumps({"mcpServers": {name: {"command": sys.executable, "args": ["-c", "pass"]}}}),
                   encoding="utf-8")
    monkeypatch.setattr(D, "MCP_CONFIGS", [cfg])
    monkeypatch.setattr(D, "HTTP_CANDIDATES", {})
    monkeypatch.setattr(D, "FLEET_HTTP_CANDIDATES", {})
    d = _body(_call("brain_doors"))
    row = d["mcp"][0]
    assert row["state"] == "skipped-outbound" and hint in row["detail"]
    assert d["summary"]["mcp_skipped"] == [name]
