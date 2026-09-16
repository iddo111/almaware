# -*- coding: utf-8 -*-
r"""almido_mcp: the doors answer JSON-RPC over stdio, every call lands in an HMAC-CHAINED audit,
Claude is rate-limited by answers rather than attempts, QUORUM failures are errors not crashes,
initialize answers immediately, and a nine-minute debate does not deafen the server.

Every test here is hermetic (tests/conftest.py) except the three at the bottom, which spawn a
REAL server on this Windows PC and read its real bytes -- those three are the ones that would
have caught the CRLF framing and the 26-second handshake.
"""
import io
import json
import os
import subprocess
import sys
import threading
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import almido_mcp as M  # noqa: E402
from conftest import REAL  # noqa: E402

SETTINGS = os.path.join(os.path.expanduser("~"), ".qwen", "settings.json")


def _rpc(method, params=None, id_=1):
    return M.handle({"jsonrpc": "2.0", "id": id_, "method": method, "params": params or {}})


def _call(name, args=None, id_=1):
    return _rpc("tools/call", {"name": name, "arguments": args or {}}, id_)["result"]


# ------------------------------------------------------------------ the shape of the door
def test_initialize_and_tools_list():
    r = _rpc("initialize", {"protocolVersion": "2025-06-18", "clientInfo": {"name": "qwen-code", "version": "0.21"}})
    assert r["result"]["serverInfo"]["name"] == "almido"
    names = [t["name"] for t in _rpc("tools/list")["result"]["tools"]]
    # The original five, in their original order, must survive every extension.
    assert names[:5] == ["ask_claude", "quorum_status", "quorum_debate", "almido_audit_tail", "almido_whoami"]
    # 2026-09-05: the second brain (Iddo, 16:32 -- three levels of מוח שני).
    assert names[5:9] == ["brain_write", "brain_read", "brain_doors", "brain_propose_door"]
    # 2026-09-11: the eyes and the hands. Every one of these goes through almido_gate.gate().
    assert names[9:17] == ["computer_status", "computer_screen_info", "computer_screenshot",
                           "computer_click", "computer_type", "computer_key", "computer_scroll",
                           "computer_stop"]
    # 2026-09-11: verified-backup deletion. backup_verify PROVES a copy by sha256 and deletes
    # nothing; backup_delete_verified is the only destructive verb on this server and cannot
    # be reached without a receipt backup_verify really issued. See test_almido_backup.py.
    assert names[17:20] == ["backup_verify", "backup_delete_verified", "backup_status"]
    # 2026-09-11 WAVE A1: the phone hands, the fleet probe and the remote compiler. The phone
    # hands are the same family as the computer ones -- same gate, same audit, and expect_app
    # instead of expect_window.
    assert names[20:32] == ["phone_status", "phone_screenshot", "phone_ui_text", "phone_tap",
                            "phone_type", "phone_key", "phone_scroll", "phone_open",
                            "phone_back", "phone_home", "phone_shell", "phone_hebrew_probe"]
    assert names[32:] == ["fleet_probe", "remote_build", "remote_build_status",
                          "remote_build_selftest"]
    # There is no verb here that LIFTS the emergency stop, and there never may be.
    assert not [n for n in names if any(v in n for v in ("stop_release", "stop_clear", "unstop"))]
    # A model may PROPOSE a door through this server. It may never approve or install one:
    # no promote/decide/install verb is exposed here, and that is load-bearing.
    assert not [n for n in names if any(v in n for v in ("decide", "approve", "promote", "install"))]
    assert "maxLength" not in json.dumps(M.TOOLS)          # llama.cpp grammar limit


def test_every_declared_tool_has_a_body_and_answers():
    """DRIFT TEST (#18). A tool in TOOLS with no branch behind it is a door painted on a wall."""
    assert {t["name"] for t in M.TOOLS} == set(M.HANDLERS)
    for name in M.HANDLERS:
        if name.startswith("brain_"):
            continue                        # covered against the real package in test_almido_brain
        if name.startswith("computer_"):
            # Covered in test_almido_computer.py against a REDIRECTED gate. Never here:
            # calling computer_stop with empty arguments would create Iddo's real
            # ~/.iddo-harness/STOP and silently disarm every computer-use door on this
            # machine, and computer_screenshot would photograph whatever he has open.
            # [[feedback_never_test_safety_on_a_living_system]].
            continue
        result = _call(name)
        assert "unknown tool" not in result["content"][0]["text"], name


# ------------------------------------------------------------------ #13 the announce
def test_initialize_answers_in_under_a_second_with_a_slow_ramlink(monkeypatch, audit_rows):
    """The measured defect: initialize took 26.4 s because it waited for the council's lock."""
    posted = threading.Event()

    def slow_post(text):
        time.sleep(30)
        posted.set()
        return True, "posted late"

    monkeypatch.setenv("ALMIDO_ANNOUNCE", "1")
    monkeypatch.setattr(M, "ramchat_post", slow_post)
    started = time.time()
    r = _rpc("initialize", {"clientInfo": {"name": "qwen-code"}})
    elapsed = time.time() - started
    assert "serverInfo" in r["result"]
    assert elapsed < 1.0, "initialize blocked for %.1f s" % elapsed
    assert not posted.is_set(), "the post must still be in flight, not awaited"
    assert audit_rows() == [], "and the session_start row is written when the post RETURNS"


def test_announce_records_the_real_rc_not_ok_true(monkeypatch, audit_rows):
    """A row saying ok=True over a PermissionError traceback is worse than no row (#13)."""
    monkeypatch.setenv("ALMIDO_ANNOUNCE", "1")
    monkeypatch.setattr(M, "ramchat_post", lambda text: (False, "PermissionError: [WinError 5]"))
    _rpc("initialize", {"clientInfo": {"name": "qwen-code"}})
    M.STATE["announce_thread"].join(timeout=5)
    row = audit_rows()[-1]
    assert row["action"] == "tool:session_start"
    assert row["outcome"] == "error" and "WinError 5" in row["meta"]["note"]


def test_announce_happens_once_per_process(monkeypatch):
    """qwen reconnect bursts made session_start 21 of 24 rows in the live audit (#13)."""
    monkeypatch.setenv("ALMIDO_ANNOUNCE", "1")
    calls = []
    monkeypatch.setattr(M, "ramchat_post", lambda text: (calls.append(text), (True, "ok"))[1])
    for _ in range(4):
        _rpc("initialize", {"clientInfo": {"name": "qwen-code"}})
    M.STATE["announce_thread"].join(timeout=5)
    assert len(calls) == 1


def test_announce_off_says_nothing(monkeypatch):
    calls = []
    monkeypatch.setattr(M, "ramchat_post", lambda text: (calls.append(text), (True, "ok"))[1])
    _rpc("initialize", {"clientInfo": {"name": "alma-brain-doors"}})   # the #5 caller
    assert calls == [] and M.announce() is False


def test_ramchat_post_reports_a_missing_ramlink_as_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(M, "ramchat_post", REAL["ramchat_post"])
    monkeypatch.setattr(M, "RAMLINK", tmp_path / "nowhere" / "ramlink.py")
    ok, note = M.ramchat_post("hello")
    assert ok is False and "not found" in note


# ------------------------------------------------------------------ #19 the Claude budget
def test_ask_claude_calls_cli_and_audits(monkeypatch, audit_rows):
    seen = {}

    def fake_run(cmd, stdin=None, timeout=60, cwd=None):
        seen["cmd"] = cmd
        seen["stdin"] = stdin
        return 0, "תשובה קצרה", ""

    monkeypatch.setattr(M, "run", fake_run)
    r = _call("ask_claude", {"question": "מה השעה?", "context": "x=1"})
    body = json.loads(r["content"][0]["text"])
    assert body["answer"] == "תשובה קצרה" and seen["cmd"][:2] == ["claude", "-p"] and "מה השעה?" in seen["stdin"]
    row = audit_rows()[-1]
    assert row["action"] == "tool:ask_claude" and row["outcome"] == "ok" and row["actor"] == M.AUTHOR


def test_ask_claude_budget(monkeypatch):
    monkeypatch.setattr(M, "CLAUDE_MAX", 1)
    monkeypatch.setattr(M, "run", lambda *a, **k: (0, "ok", ""))
    assert "isError" not in _call("ask_claude", {"question": "a"})
    r = _call("ask_claude", {"question": "b"})
    assert r.get("isError") is True and "budget" in r["content"][0]["text"]


def test_a_failed_claude_call_does_not_spend_budget(monkeypatch):
    """A broken PATH used to eat all 20 of Iddo's calls without one answer (#19)."""
    monkeypatch.setattr(M, "CLAUDE_MAX", 3)
    monkeypatch.setattr(M, "run", lambda *a, **k: (1, "", "claude: not found"))
    for _ in range(3):
        assert _call("ask_claude", {"question": "a"}).get("isError") is True
    assert M.STATE["claude_calls"] == 0 and M.STATE["claude_failures"] == 3
    monkeypatch.setattr(M, "run", lambda *a, **k: (0, "now it works", ""))
    r = _call("ask_claude", {"question": "a"})
    # ...but it still stops trying forever: three failures at CLAUDE_MAX 3 is enough.
    assert r.get("isError") is True and "refusing to keep trying" in r["content"][0]["text"]


# ------------------------------------------------------------------ QUORUM
def test_quorum_down_is_error_not_crash(monkeypatch):
    monkeypatch.setattr(M, "http_json", REAL["http_json"])
    monkeypatch.setattr(M, "QUORUM", "http://127.0.0.1:9")          # discard port
    r = _call("quorum_status")
    assert r.get("isError") is True and "not reachable" in r["content"][0]["text"]
    r = _call("quorum_debate", {"topic": "x"})
    assert r.get("isError") is True and "two live models" in r["content"][0]["text"]


def test_a_listening_but_slow_quorum_is_not_called_down(monkeypatch):
    """QUORUM probes every model before answering /api/health. 'down' is the lie doors.py
    exists to stop, and whoami was telling it (#19)."""
    monkeypatch.setattr(M, "http_json", _boom)
    monkeypatch.setattr(M, "_tcp_open", lambda url, timeout=2.0: True)
    monkeypatch.setattr(M, "run", lambda *a, **k: (0, "claude 9.9", ""))
    assert "slow" in json.loads(_call("almido_whoami")["content"][0]["text"])["doors"]["quorum"]
    assert "slow, not down" in _call("quorum_status")["content"][0]["text"]


def _boom(*a, **k):
    raise OSError("timed out")


# ------------------------------------------------------------------ #7 quorum_debate
class _SSE(threading.Thread):
    """A real HTTP server that streams a real SSE debate, so the parser is tested on the wire."""

    def __init__(self, script, idle=0.0):
        import http.server
        super().__init__(daemon=True)
        outer = self

        class H(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_POST(self):
                self.rfile.read(int(self.headers.get("Content-Length", 0) or 0))
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()
                try:
                    for event, data in outer.script:
                        if event == "SLEEP":
                            time.sleep(data)
                            continue
                        chunk = ("event: %s\ndata: %s\n\n" % (event, json.dumps(data))).encode("utf-8")
                        self.wfile.write(b"%x\r\n%s\r\n" % (len(chunk), chunk))
                        self.wfile.flush()
                    if outer.idle:
                        time.sleep(outer.idle)
                    self.wfile.write(b"0\r\n\r\n")
                    self.wfile.flush()
                except Exception:
                    pass

            def log_message(self, *a):
                pass

        self.script = script
        self.idle = idle
        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = "http://127.0.0.1:%d" % self.srv.server_address[1]

    def run(self):
        self.srv.serve_forever()

    def stop(self):
        self.srv.shutdown()


@pytest.fixture()
def sse():
    made = []

    def _make(script, idle=0.0):
        s = _SSE(script, idle)
        s.start()
        made.append(s)
        return s
    yield _make
    for s in made:
        s.stop()


def test_debate_collects_deltas_synthesis_and_stops_on_done(monkeypatch, sse):
    server = sse([("status", {"text": "round 1"}),
                  ("delta", {"agent": "claude", "text": "קושיא"}),
                  ("delta", {"agent": "grok", "text": "תירוץ"}),
                  ("delta", {"agent": "claude", "text": " ועוד"}),
                  ("synth", {"text": "מסקנה: כן"}),
                  ("done", {})],
                 idle=30)                      # it keeps the socket open AFTER done on purpose
    monkeypatch.setattr(M, "QUORUM", server.url)
    started = time.time()
    body = json.loads(_call("quorum_debate", {"topic": "t", "models": ["claude", "grok"],
                                              "timeout": 30})["content"][0]["text"])
    assert body["turns"] == {"claude": "קושיא ועוד", "grok": "תירוץ"}
    assert body["synthesis"] == "מסקנה: כן" and body["status"] == ["round 1"]
    assert body["completed"] is True and body["timed_out"] is False
    assert time.time() - started < 10, "'done' must end the read, not the socket closing"


def test_an_error_event_makes_the_debate_an_error(monkeypatch, sse):
    """Before this, a failed debate returned partial turns with isError absent (#7)."""
    server = sse([("delta", {"agent": "claude", "text": "half a thought"}),
                  ("error", {"error": "grok died mid-round"}),
                  ("done", {})])
    monkeypatch.setattr(M, "QUORUM", server.url)
    r = _call("quorum_debate", {"topic": "t", "models": ["claude", "grok"], "timeout": 30})
    assert r.get("isError") is True
    body = json.loads(r["content"][0]["text"])
    assert body["errors"] == ["grok died mid-round"]
    assert body["turns"]["claude"] == "half a thought", "the partial transcript is still returned"


def test_a_stalled_stream_hits_the_deadline_instead_of_holding_the_door(monkeypatch, sse):
    """The wall clock used to be checked only AFTER a line arrived, so silence held it open."""
    server = sse([("status", {"text": "thinking"})], idle=60)
    monkeypatch.setattr(M, "QUORUM", server.url)
    monkeypatch.setattr(M, "DEBATE_READ_SLICE", 0.5)
    started = time.time()
    r = _call("quorum_debate", {"topic": "t", "models": ["a", "b"], "timeout": 5})
    elapsed = time.time() - started
    assert r.get("isError") is True
    body = json.loads(r["content"][0]["text"])
    assert body["timed_out"] is True and body["status"] == ["thinking"]
    assert 4 < elapsed < 12, "gave up after %.1f s" % elapsed


def test_a_read_timeout_does_not_lose_the_next_event(monkeypatch, sse):
    """The per-read slice must be a heartbeat, not a truncation: data after it still arrives."""
    server = sse([("status", {"text": "slow model"}), ("SLEEP", 1.5),
                  ("delta", {"agent": "a", "text": "arrived late"}), ("done", {})])
    monkeypatch.setattr(M, "QUORUM", server.url)
    monkeypatch.setattr(M, "DEBATE_READ_SLICE", 0.3)
    body = json.loads(_call("quorum_debate", {"topic": "t", "models": ["a", "b"],
                                              "timeout": 30})["content"][0]["text"])
    assert body["turns"] == {"a": "arrived late"} and body["completed"] is True


def test_the_debate_timeout_is_capped_below_the_clients(monkeypatch, sse):
    """qwen-code gives up at 600 s. An answer at 600 s is an answer nobody receives (#7)."""
    server = sse([("done", {})])
    monkeypatch.setattr(M, "QUORUM", server.url)
    for asked, want in ((None, 540.0), (99999, 570.0), (0.1, 5.0), (12, 12.0)):
        args = {"topic": "t", "models": ["a", "b"]}
        if asked is not None:
            args["timeout"] = asked
        body = json.loads(_call("quorum_debate", args)["content"][0]["text"])
        assert body["timeout_s"] == want, (asked, body["timeout_s"])


# ------------------------------------------------------------------ #4 the audit
def test_the_default_audit_is_not_the_harnesss_own_chain():
    r"""ALMIDO appending its own schema to ~/.iddo-harness/audit.jsonl BROKE that HMAC chain at
    line 33 on 2026-09-03. The default must never point there again."""
    default = M.DEFAULT_AUDIT
    assert default != M.LIVE_HARNESS_AUDIT
    assert "iddo-harness" in str(default) and default.name == "almido-audit.jsonl"
    # ...and even if someone sets ALMIDO_AUDIT to the live chain, we refuse to write into it.
    saved = M.AUDIT
    try:
        M.AUDIT = M.LIVE_HARNESS_AUDIT
        assert M._audit_target() != M.LIVE_HARNESS_AUDIT
    finally:
        M.AUDIT = saved


def test_every_row_is_hmac_chained_and_verifies(monkeypatch, audit_rows, tmp_path):
    monkeypatch.setattr(M, "run", lambda *a, **k: (0, "answer", ""))
    _call("ask_claude", {"question": "a"})
    _call("almido_whoami")
    _call("nope")
    rows = audit_rows()
    assert [r["action"] for r in rows] == ["tool:ask_claude", "tool:almido_whoami", "tool:nope"]
    assert [r["outcome"] for r in rows] == ["ok", "ok", "error"]
    assert all(r["meta"]["door"] == "almido_mcp" and r["prev"] is not None for r in rows)
    assert rows[1]["prev"] == rows[0]["hmac"], "row 2 must chain onto row 1"
    ok, bad, why = M._HARNESS["verify"](tmp_path / "almido-audit.jsonl", M._audit_log().key)
    assert ok, "chain broken at line %s: %s" % (bad, why)


def test_a_failure_row_carries_its_reason(audit_rows):
    """audit(name, args, not isError) with note '' recorded that something failed and not why."""
    _call("brain_write", {"scope": "model", "id": "x", "kind": "learned", "text": "t", "source": " "})
    row = audit_rows()[-1]
    assert row["outcome"] == "error" and "PROVENANCE" in row["meta"]["note"]


def test_audit_tail_seeks_instead_of_reading_the_whole_file(tmp_path):
    """It used to read the entire file into memory to hand back 20 lines (#19)."""
    big = tmp_path / "big.jsonl"
    big.write_text("".join("line %06d\n" % i for i in range(200000)), encoding="utf-8")
    assert big.stat().st_size > 2_000_000
    assert M._tail_lines(big, 3) == ["line 199997", "line 199998", "line 199999"]
    assert M._tail_lines(big, 200)[0] == "line 199800"
    # ...and asking for the impossible reads a bounded window, not 2.6 MB.
    assert 0 < len(M._tail_lines(big, 100000)) < 30000


def test_audit_tail_returns_the_last_rows_through_the_door(tmp_path):
    (tmp_path / "almido-audit.jsonl").write_text(
        "".join("line %04d\n" % i for i in range(5000)), encoding="utf-8")
    text = _call("almido_audit_tail", {"n": 3})["content"][0]["text"]
    assert text.splitlines() == ["line 4997", "line 4998", "line 4999"]
    assert "no audit yet" not in text


def test_the_hmac_key_is_really_ACLd_to_this_user(monkeypatch, tmp_path):
    r"""os.chmod(0600) is a NO-OP on Windows -- which is how ~/.iddo-harness/audit.key ended up
    readable by SYSTEM and Administrators. This runs the harness's real icacls path once."""
    assert M.harness_audit_class() is not None
    fs = M._HARNESS.get("file_security")
    assert fs is not None, "no file_security in %s" % M._HARNESS.get("repo")
    # Loaded by PATH, not by `import agent.file_security` -- that name resolves to the
    # pip-installed PR-4 copy on this machine, whose verbs are called something else.
    assert "iddo-harness" in fs.__file__ and hasattr(fs, "restrict_private_file")
    monkeypatch.setenv("ALMIDO_SECURE_KEY", "1")
    M._AUDITLOG.update(log=None, path=None)
    _call("nope")
    key = tmp_path / "almido-audit.key"
    assert key.is_file()
    assert M.audit_state()["key_restricted"] is True
    assert fs.private_file_permissions_ok(key), "the ACL did not actually take"


def test_an_unreachable_harness_falls_back_to_a_SEPARATE_unsigned_file(monkeypatch, tmp_path):
    """If the gate's code is gone, rows still land -- but never inside a chained file."""
    monkeypatch.setitem(M._HARNESS, "cls", None)
    monkeypatch.setitem(M._HARNESS, "error", "test: no harness")
    M._AUDITLOG.update(log=None, path=None)
    _call("nope")
    assert not (tmp_path / "almido-audit.jsonl").exists()
    rows = [json.loads(ln) for ln in (tmp_path / "almido-audit-unsigned.jsonl").read_text(encoding="utf-8").splitlines()]
    assert rows[-1]["unsigned"] is True and rows[-1]["action"] == "tool:nope"
    assert "no audit yet" not in _call("almido_audit_tail")["content"][0]["text"]


# ------------------------------------------------------------------ protocol / plumbing
def test_unknown_method_and_tool():
    assert _rpc("nope")["error"]["code"] == -32601
    assert _call("nope")["isError"] is True
    assert M.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


def test_a_bad_CLAUDE_MAX_env_does_not_kill_the_process(monkeypatch):
    """int(os.environ[...]) at import turned a typo into a door that never opens (#19)."""
    monkeypatch.setenv("ALMIDO_CLAUDE_MAX", "twenty")
    assert M._env_int("ALMIDO_CLAUDE_MAX", 20) == 20
    monkeypatch.setenv("ALMIDO_CLAUDE_MAX", "7")
    assert M._env_int("ALMIDO_CLAUDE_MAX", 20) == 7


def test_stdio_roundtrip(monkeypatch):
    monkeypatch.setattr(M, "run", lambda *a, **k: (0, "claude 9.9", ""))
    monkeypatch.setattr(M, "DRAIN_SECONDS", 10.0)
    inp = io.StringIO('{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}\n'
                      '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"almido_whoami"}}\n'
                      'not json\n')
    out = io.StringIO()
    monkeypatch.setattr(sys, "stdin", inp)
    monkeypatch.setattr(sys, "stdout", out)
    M.main()
    # tools/call answers from a worker thread, so match by id -- never by arrival order.
    lines = {json.loads(l).get("id"): json.loads(l) for l in out.getvalue().splitlines()}
    assert "serverInfo" in lines[1]["result"]
    assert "almido-qwen" in lines[2]["result"]["content"][0]["text"]
    assert lines[None]["error"]["code"] == -32700


def test_a_short_session_still_gets_its_council_line_out(monkeypatch, audit_rows):
    """The announce is a daemon thread; without a drain, a handshake-and-quit session would
    lose the post AND its audit row at process exit. #13"""
    monkeypatch.setenv("ALMIDO_ANNOUNCE", "1")
    monkeypatch.setattr(M, "ramchat_post", lambda text: (time.sleep(0.4), (True, "posted"))[1])
    monkeypatch.setattr(M, "DRAIN_SECONDS", 10.0)
    monkeypatch.setattr(sys, "stdin", io.StringIO('{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}\n'))
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    M.main()
    assert [r["action"] for r in audit_rows()] == ["tool:session_start"]


def test_ping_answers_while_a_tools_call_is_still_running(monkeypatch):
    """The single-threaded loop meant a nine-minute debate deafened the whole server (#7)."""
    release = threading.Event()
    monkeypatch.setattr(M, "run", lambda *a, **k: (release.wait(20), (0, "claude 9.9", ""))[1])
    monkeypatch.setattr(M, "DRAIN_SECONDS", 20.0)
    inp = io.StringIO('{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"almido_whoami"}}\n'
                      '{"jsonrpc":"2.0","id":2,"method":"ping"}\n')
    out = io.StringIO()
    monkeypatch.setattr(sys, "stdin", inp)
    monkeypatch.setattr(sys, "stdout", out)

    def finish():
        time.sleep(1.5)
        release.set()
    threading.Thread(target=finish, daemon=True).start()
    M.main()
    ids = [json.loads(l)["id"] for l in out.getvalue().splitlines()]
    assert ids == [2, 1], "ping must overtake the blocked tools/call, not queue behind it"


# ------------------------------------------------------------------ the real Windows server
@pytest.fixture()
def real_server():
    """Spawn the REAL almido_mcp.py the way ~/.qwen/settings.json spawns it. #18"""
    procs = []

    def _spawn(env_extra=None, args=None):
        env = dict(os.environ)
        env.update(PYTHONIOENCODING="utf-8", ALMIDO_ANNOUNCE="0")
        env.update(env_extra or {})
        cmd = args or [sys.executable, os.path.join(os.path.dirname(M.__file__), "almido_mcp.py")]
        p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, cwd=os.path.dirname(M.__file__), env=env)
        procs.append(p)
        return p
    yield _spawn
    for p in procs:
        if p.poll() is None:
            p.kill()


def test_a_real_child_answers_in_LF_not_CRLF(real_server, tmp_path):
    r"""Measured on the wire 2026-09-06: the old server ended every line with \r\n. qwen-code
    tolerates it; a strict MCP host need not (#19)."""
    p = real_server({"ALMIDO_AUDIT": str(tmp_path / "a.jsonl")})
    out, _ = p.communicate(b'{"jsonrpc":"2.0","id":1,"method":"ping"}\n', timeout=60)
    assert b"\r\n" not in out and out.endswith(b"}\n")
    assert json.loads(out.decode("utf-8"))["result"] == {}


@pytest.mark.skipif(not os.path.isfile(SETTINGS), reason="~/.qwen/settings.json absent")
def test_the_command_in_settings_json_really_handshakes(real_server, tmp_path):
    """THE integration test: the exact argv qwen-code uses, on this Windows PC, announcing
    nothing. If this fails, the body has no door however green the unit tests are."""
    spec = json.load(open(SETTINGS, encoding="utf-8"))["mcpServers"]["almido"]
    argv = [spec["command"]] + list(spec.get("args") or [])
    assert os.path.isfile(argv[0]), argv[0]
    p = real_server({"ALMIDO_AUDIT": str(tmp_path / "a.jsonl"), **(spec.get("env") or {})}, args=argv)
    started = time.time()
    request = (json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                           "params": {"protocolVersion": "2025-06-18",
                                      "clientInfo": {"name": "pytest", "version": "1"}}}) + "\n"
               + json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}) + "\n")
    out, err = p.communicate(request.encode("utf-8"), timeout=90)
    elapsed = time.time() - started
    messages = {json.loads(l)["id"]: json.loads(l) for l in out.decode("utf-8").splitlines() if l.strip()}
    assert messages[1]["result"]["serverInfo"] == {"name": "almido", "version": M.SERVER_INFO["version"]}
    assert [t["name"] for t in messages[2]["result"]["tools"]] == [t["name"] for t in M.TOOLS]
    assert elapsed < 15, "a cold handshake took %.1f s" % elapsed
    assert not (tmp_path / "a.jsonl").exists(), "ALMIDO_ANNOUNCE=0 must write no session_start row"
    assert b"Traceback" not in err


# ------------------------------------------------------------ WAVE A1 doors (2026-09-11)
# The phone hands, the fleet probe and the remote compiler. These tests are about the MCP
# LAYER -- that a refusal comes back as isError and not as a cheerful success envelope. The
# doors' own behaviour is tested in test_almido_phone / _fleet / _remote.
def test_a_phone_refusal_comes_back_as_an_error_not_a_success(monkeypatch):
    """A model that reads {"ok": false} inside a SUCCESS envelope carries on believing it
    tapped the screen. Same lesson as _cu_call, enforced again at this layer."""
    class FakePhone:
        @staticmethod
        def tap(x, y, expect_app=None):
            return {"ok": False, "reason": "the phone is not reachable over adb",
                    "verdict": "BLOCK"}
    monkeypatch.setitem(M._PH, "mod", FakePhone)
    r = M.call_tool("phone_tap", {"x": 1, "y": 1, "expect_app": "com.x"})
    assert r["isError"] is True
    assert "not reachable" in r["content"][0]["text"]


def test_a_missing_phone_module_never_pretends_to_have_tapped(monkeypatch):
    monkeypatch.setattr(M, "_PH", {"error": "ImportError: no almido_phone"})
    r = M.call_tool("phone_status", {})
    assert r["isError"] is True
    assert "Nothing was tapped" in r["content"][0]["text"]


def test_a_missing_remote_module_never_pretends_to_have_built(monkeypatch):
    monkeypatch.setattr(M, "_RB", {"error": "ImportError: no almido_remote"})
    r = M.call_tool("remote_build", {"source_dir": "D:\nope"})
    assert r["isError"] is True
    assert "Nothing was built" in r["content"][0]["text"]


def test_fleet_probe_reaches_the_real_module_and_returns_json(monkeypatch):
    class FakeFleet:
        @staticmethod
        def probe(timeout=None, budget=None, include_hosts=True):
            return {"summary": "19/19 VERIFIED", "doors": [], "hosts": [], "read_only": True}
    monkeypatch.setitem(M._FL, "mod", FakeFleet)
    r = M.call_tool("fleet_probe", {})
    assert not r.get("isError")
    assert "19/19 VERIFIED" in r["content"][0]["text"]


def test_every_new_tool_is_audited(monkeypatch, audit_rows):
    """Every tool call through this door lands in the HMAC-chained audit, refusals included.
    A hand on Iddo's phone with no row is a hand nobody can account for afterwards."""
    monkeypatch.setattr(M, "_PH", {"error": "not here"})
    M.call_tool("phone_tap", {"x": 1, "y": 1, "expect_app": "com.x"})
    rows = audit_rows()
    assert rows, "a tool call with no audit row is a hand nobody can account for"
    last = rows[-1]
    assert last["action"] == "tool:phone_tap"
    assert last["outcome"] == "error"
    assert last["meta"]["tool"] == "phone_tap"
    assert last["meta"]["note"], "a failure row with no reason is not a record"


def test_the_phone_tools_all_demand_expect_app_in_their_schema():
    """The schema is the only thing a coder model reads before it calls. If expect_app is
    optional there, the discipline is a suggestion."""
    hands = {"phone_tap", "phone_type", "phone_key", "phone_scroll", "phone_back",
             "phone_hebrew_probe"}
    for tool in M.TOOLS:
        if tool["name"] in hands:
            assert "expect_app" in (tool["inputSchema"].get("required") or []), tool["name"]


def test_no_phone_tool_offers_a_way_to_open_the_microphone():
    """AUDIO PROTECTION LAW, read off the declarations themselves: there is no verb here
    that records, plays or opens an audio app."""
    for tool in M.TOOLS:
        if not tool["name"].startswith("phone_"):
            continue
        for forbidden in ("record", "microphone", "mic ", "play audio", "volume"):
            assert forbidden not in tool["name"].lower(), tool["name"]
