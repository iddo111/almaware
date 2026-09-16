# -*- coding: utf-8 -*-
"""doors.py: a door is reported open only because it was just PROVED open.

The two tests that matter here spawn a real stdio MCP server and start a real
HTTP server, then check that doors.py reports what those actually do -- and that
a server which refuses to answer is reported down rather than assumed up.
"""
import http.server
import json
import os
import socket
import sys
import textwrap
import threading

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import doors as D  # noqa: E402

FAKE_MCP = textwrap.dedent(
    """
    import json, sys
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        m = json.loads(raw)
        if m.get("id") is None:
            continue
        if m.get("method") == "initialize":
            r = {"protocolVersion": "2025-06-18", "capabilities": {},
                 "serverInfo": {"name": "fake", "version": "9.9"}}
        elif m.get("method") == "tools/list":
            r = {"tools": [{"name": "alpha"}, {"name": "beta"}]}
        else:
            r = {}
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": m["id"], "result": r}) + "\\n")
        sys.stdout.flush()
    """
)

DEAF_MCP = "import sys, time\nfor _ in sys.stdin:\n    time.sleep(30)\n"


def test_mcp_candidates_reads_every_config(tmp_path, monkeypatch):
    a = tmp_path / ".mcp.json"
    a.write_text(json.dumps({"mcpServers": {"one": {"command": "python", "args": ["x.py"]}}}), encoding="utf-8")
    b = tmp_path / "settings.json"
    b.write_text(json.dumps({"projects": {"p": {"mcpServers": {"two": {"command": "node"}}}}}), encoding="utf-8")
    c = tmp_path / "broken.json"
    c.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(D, "MCP_CONFIGS", [a, b, c, tmp_path / "absent.json"])
    names = sorted(x["name"] for x in D.mcp_candidates())
    assert names == ["one", "two"], "a broken or missing config must be skipped, not fatal"


def test_a_real_stdio_server_reports_its_REAL_tools(tmp_path):
    srv = tmp_path / "fake_mcp.py"
    srv.write_text(FAKE_MCP, encoding="utf-8")
    r = D.probe_stdio({"name": "fake", "declared_in": "test", "command": sys.executable,
                       "args": [str(srv)], "cwd": None, "env": {}})
    assert r["state"] == "up"
    assert r["tools"] == ["alpha", "beta"], "the tool list must come from the server, not from us"
    assert "fake 9.9" == r["detail"] or r["detail"] == ""


def test_a_server_that_does_not_answer_is_DOWN(tmp_path):
    srv = tmp_path / "deaf_mcp.py"
    srv.write_text(DEAF_MCP, encoding="utf-8")
    r = D.probe_stdio({"name": "deaf", "declared_in": "test", "command": sys.executable,
                       "args": [str(srv)], "cwd": None, "env": {}}, timeout=3)
    assert r["state"] == "down" and "no answer" in r["detail"]


def test_a_missing_command_is_a_door_that_does_not_exist():
    r = D.probe_stdio({"name": "ghost", "declared_in": "test",
                       "command": r"C:\definitely\not\here.exe", "args": [], "cwd": None, "env": {}})
    assert r["state"] == "down" and "not found" in r["detail"]


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        code = 401 if self.path.startswith("/gated") else 200
        body = b'{"real": true}'
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


@pytest.fixture()
def live_http():
    srv = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield srv.server_address[1]
    srv.shutdown()


def test_http_probe_reports_the_real_status_and_body(live_http):
    r = D.probe_http("t", "http://127.0.0.1:%d/" % live_http)
    assert r["state"] == "up" and "HTTP 200" in r["detail"] and '"real": true' in r["detail"]


def test_a_gated_service_is_UP_not_down(live_http):
    """401 means something IS answering. Calling that 'down' is the lie this module exists to stop."""
    r = D.probe_http("t", "http://127.0.0.1:%d/gated" % live_http)
    assert r["state"] == "up-gated" and r["detail"] == "HTTP 401"


def test_a_dead_port_is_down():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    r = D.probe_http("t", "http://127.0.0.1:%d/" % port, timeout=2)
    assert r["state"] == "down"


def test_a_listening_but_slow_port_is_not_called_dead():
    """QUORUM's /api/health probes every model before answering. A tight timeout
    reported it as down on 2026-09-05 while it was demonstrably serving. TCP is
    asked as a second opinion so netstat and this module cannot disagree."""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    # backlog 5, not 1: the HTTP attempt is never accepted, so with a backlog of 1
    # the follow-up TCP probe finds the queue full and the test fails on its own
    # artefact rather than on the code. Measured 2026-09-05.
    s.listen(5)                       # accepts connections, never speaks HTTP
    port = s.getsockname()[1]
    try:
        r = D.probe_http("slow", "http://127.0.0.1:%d/" % port, timeout=1.5)
        assert r["state"] == "listening-slow" and "accepts" in r["detail"]
    finally:
        s.close()


def test_listening_ports_agree_with_a_socket_we_opened_ourselves():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    s.listen(1)
    port = s.getsockname()[1]
    try:
        assert port in {p["port"] for p in D.listening_ports()}
    finally:
        s.close()


def test_doors_summary_counts_match_the_rows(tmp_path, monkeypatch):
    cfg = tmp_path / ".mcp.json"
    srv = tmp_path / "fake_mcp.py"
    srv.write_text(FAKE_MCP, encoding="utf-8")
    cfg.write_text(json.dumps({"mcpServers": {
        "good": {"command": sys.executable, "args": [str(srv)]},
        "ghost": {"command": r"C:\nope\nope.exe"}}}), encoding="utf-8")
    monkeypatch.setattr(D, "MCP_CONFIGS", [cfg])
    monkeypatch.setattr(D, "HTTP_CANDIDATES", {})
    d = D.doors(include_ports=False, include_skills=False)
    assert d["summary"]["mcp_declared"] == 2
    assert d["summary"]["mcp_answering"] == 1 and d["summary"]["mcp_up"] == ["good"]
    assert d["summary"]["mcp_tools_total"] == 2
    assert d["method"] == "probed, not declared"
    assert len(d["mcp"]) == d["summary"]["mcp_declared"]


# ---------------------------------------------------------------- Phase-2 defect #5
# A probe that changes the thing it measures is not a measurement. Until 2026-09-06 doors()
# spawned the almido MCP server that CALLS it (so every brain_doors posted a fake "session
# started" line to the council and wrote a row into the security audit), spawned servers that
# can send messages outward, and GET ERAN's live window on every call.

ENV_MCP = textwrap.dedent(
    """
    import json, os, sys
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        m = json.loads(raw)
        if m.get("id") is None:
            continue
        if m.get("method") == "tools/list":
            r = {"tools": [{"name": "%s=%s" % (k, os.environ.get(k, "<unset>"))}
                           for k in ("ALMIDO_ANNOUNCE", "ALMIDO_AUDIT", "BRAIN_DOOR_NO_SPAWN")]}
        else:
            r = {"protocolVersion": "2025-06-18", "capabilities": {},
                 "serverInfo": {"name": "envecho", "version": "1"}}
        print(json.dumps({"jsonrpc": "2.0", "id": m["id"], "result": r}), flush=True)
    """
)


def _env_candidate(tmp_path, env=None):
    srv = tmp_path / "env_mcp.py"
    srv.write_text(ENV_MCP, encoding="utf-8")
    return {"name": "envecho", "declared_in": "test", "command": sys.executable,
            "args": [str(srv)], "cwd": None, "env": env or {}}


def test_every_probed_child_is_told_to_announce_nothing(tmp_path):
    """ALMIDO_ANNOUNCE=0 and a throwaway ALMIDO_AUDIT go into every child, always."""
    r = D.probe_stdio(_env_candidate(tmp_path))
    seen = dict(t.split("=", 1) for t in r["tools"])
    assert r["state"] == "up"
    assert seen["ALMIDO_ANNOUNCE"] == "0"
    assert seen["ALMIDO_AUDIT"].endswith(".jsonl") and "alma-brain-doors" in seen["ALMIDO_AUDIT"]
    assert "~" not in seen["ALMIDO_AUDIT"] and ".iddo-harness" not in seen["ALMIDO_AUDIT"]


def test_a_config_cannot_talk_a_probed_child_into_announcing(tmp_path):
    """~/.qwen/settings.json declares almido with ALMIDO_ANNOUNCE at its default. The probe's
    environment is applied LAST so the config can never win."""
    r = D.probe_stdio(_env_candidate(tmp_path, {"ALMIDO_ANNOUNCE": "1"}))
    assert dict(t.split("=", 1) for t in r["tools"])["ALMIDO_ANNOUNCE"] == "0"


def test_a_probed_child_is_told_not_to_recurse(tmp_path, monkeypatch):
    monkeypatch.setenv("BRAIN_DOOR_NO_SPAWN", str(tmp_path / "me.py"))
    r = D.probe_stdio(_env_candidate(tmp_path))
    assert "me.py" in dict(t.split("=", 1) for t in r["tools"])["BRAIN_DOOR_NO_SPAWN"]


def test_the_server_doing_the_measuring_is_never_spawned(tmp_path, monkeypatch):
    me = tmp_path / "me.py"
    me.write_text("print(1)\n", encoding="utf-8")
    monkeypatch.setenv("BRAIN_DOOR_NO_SPAWN", str(me))
    cfg = tmp_path / ".mcp.json"
    cfg.write_text(json.dumps({"mcpServers": {
        "self": {"command": sys.executable, "args": [str(me)]},
        "other": {"command": sys.executable, "args": ["-c", "pass"]}}}), encoding="utf-8")
    monkeypatch.setattr(D, "MCP_CONFIGS", [cfg])
    monkeypatch.setattr(D, "HTTP_CANDIDATES", {})
    d = D.doors(include_ports=False, include_skills=False)
    rows = {r["name"]: r for r in d["mcp"]}
    assert rows["self"]["state"] == "skipped-self"
    assert rows["other"]["state"] != "skipped-self", "only OUR OWN script is skipped"
    assert d["summary"]["mcp_skipped"] == ["self"]


def test_message_sending_servers_are_skipped_unless_asked_for(tmp_path, monkeypatch):
    srv = tmp_path / "fake_mcp.py"
    srv.write_text(FAKE_MCP, encoding="utf-8")
    cfg = tmp_path / ".mcp.json"
    cfg.write_text(json.dumps({"mcpServers": {
        "wa-mcp": {"command": sys.executable, "args": [str(srv)]},
        "hub": {"command": sys.executable, "args": [str(srv)], "env": {"HUB_OUTBOUND_ENABLED": "1"}},
        "plain": {"command": sys.executable, "args": [str(srv)]}}}), encoding="utf-8")
    monkeypatch.setattr(D, "MCP_CONFIGS", [cfg])
    monkeypatch.setattr(D, "HTTP_CANDIDATES", {})
    d = D.doors(include_ports=False, include_skills=False)
    assert sorted(d["summary"]["mcp_skipped"]) == ["hub", "wa-mcp"]
    assert d["summary"]["mcp_up"] == ["plain"]
    d = D.doors(include_ports=False, include_skills=False, include_outbound=True)
    assert d["summary"]["mcp_skipped"] == []
    assert sorted(d["summary"]["mcp_up"]) == ["hub", "plain", "wa-mcp"]


def test_the_fleet_organisms_are_not_touched_unless_asked_for(monkeypatch):
    """eran1:8820 is ERAN's observation window, eran2:8830 his senses, eran4:8806 darwish's
    tap. Listing this PC's doors does not require reaching into a living organism."""
    probed = []
    monkeypatch.setattr(D, "HTTP_CANDIDATES", {"local": "http://127.0.0.1:9/"})
    monkeypatch.setattr(D, "FLEET_HTTP_CANDIDATES", {"eran-window": "http://<lan-ip>:8820/"})
    monkeypatch.setattr(D, "probe_http",
                        lambda n, u, timeout=1: (probed.append(n),
                                                 {"name": n, "kind": "http", "url": u,
                                                  "state": "down", "detail": "", "ms": 0})[1])
    D.doors(stdio=False, include_ports=False, include_skills=False)
    assert probed == ["local"]
    probed.clear()
    D.doors(stdio=False, include_ports=False, include_skills=False, include_fleet=True)
    assert sorted(probed) == ["eran-window", "local"]


def test_the_stdio_timeout_outlasts_desktop_commanders_startup():
    """12 s was shorter than desktop-commander's measured handshake, so a live door was
    reported down. qwen-code's own MCP discovery timeout is 30 s."""
    assert D.STDIO_TIMEOUT >= 30
