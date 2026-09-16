# -*- coding: utf-8 -*-
"""Tests for the BRAIN SWITCH (Iddo 2026-09-15 10:07-10:08: "only one model runs at a
time and I choose - easily", approved "כן").

The eran4 door (https://<tailnet-host>:8450) grows a tiny /mode API:
    GET  /mode        -> {"mode","state","detail","since","target"}
    POST /mode/coder  -> 202 switch started | 200 already ready | 409 other switch running
    POST /mode/chat   -> same shape

coder_brains.ensure_brain_mode() is the ONE client of it, shared by the desktop app
(coder_desktop.py, in a worker thread) and the tailnet twin (taste.py). These tests
drive it against a stdlib fake /mode server -- never the real door -- and cover the
PyQt-free selection/send gate (coder_brains.BrainModeGate) the desktop app uses.
"""
from __future__ import annotations

import json
import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import pytest

import coder_brains as cb

LOADING_HE = "טוען את הקודר על eran4"
LOADING_EN = "Loading the coder on eran4"


# ---------------------------------------------------------------------------
# a fake eran4 /mode door
# ---------------------------------------------------------------------------

class FakeBox:
    """State machine that behaves like the SWITCH CONTRACT. Each GET while a switch
    runs counts down `remaining`; at 0 the switch completes per `finish`."""

    def __init__(self, mode="chat", state="ready", target=None, remaining=0,
                 switch_gets=2, finish="ready", error_detail="", missing=False,
                 get_status=200, get_delay=0.0):
        self.lock = threading.Lock()
        self.mode, self.state, self.target = mode, state, target
        self.detail = ""
        self.remaining = remaining
        self.switch_gets = switch_gets
        self.finish = finish                 # "ready" | "error" | "never"
        self.error_detail = error_detail
        self.missing = missing               # the door has no /mode at all (404)
        self.get_status = get_status         # e.g. 502 like the shim today
        self.get_delay = get_delay
        self.posts = []                      # every POST target, in order
        self.started = []                    # targets of switches that really started (202)
        self.gets = 0

    def body(self):
        return {"mode": self.mode, "state": self.state, "detail": self.detail,
                "since": "2026-09-15T10:30:00+03:00", "target": self.target}

    def _complete(self):
        if self.finish == "never":
            return
        if self.finish == "error":
            self.mode, self.state, self.detail = "chat", "error", self.error_detail
        else:
            self.mode, self.state, self.detail = self.target, "ready", ""
        self.target = None

    def on_get(self):
        with self.lock:
            self.gets += 1
            if self.state == "switching":
                self.remaining -= 1
                if self.remaining <= 0:
                    self._complete()
            return self.body()

    def on_post(self, target):
        with self.lock:
            self.posts.append(target)
            if self.state == "switching":
                if self.target != target:
                    return 409, {"state": "switching", "target": self.target}
                return 202, {"state": "switching", "target": self.target}
            if self.mode == target and self.state == "ready":
                return 200, self.body()
            self.state, self.target, self.detail = "switching", target, ""
            self.remaining = self.switch_gets
            self.started.append(target)
            return 202, {"state": "switching", "target": target}


def _handler(box):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _json(self, code, obj):
            out = json.dumps(obj).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)

        def do_GET(self):
            if box.missing or self.path != "/mode":
                self._json(404, {"error": "404 page not found"})
                return
            if box.get_delay:
                time.sleep(box.get_delay)
            if box.get_status != 200:
                out = b"shim error: <urlopen error [Errno 111] Connection refused>"
                self.send_response(box.get_status)
                self.send_header("Content-Length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)
                return
            self._json(200, box.on_get())

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            if n:
                self.rfile.read(n)
            if box.missing or not self.path.startswith("/mode/"):
                self._json(404, {"error": "404 page not found"})
                return
            if box.get_status != 200:
                self.send_response(box.get_status)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            target = self.path[len("/mode/"):]
            code, obj = box.on_post(target)
            self._json(code, obj)
    return H


@pytest.fixture
def door():
    servers = []

    def make(**kw):
        box = FakeBox(**kw)
        srv = ThreadingHTTPServer(("127.0.0.1", 0), _handler(box))
        srv.daemon_threads = True
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        servers.append(srv)
        box.base = "http://127.0.0.1:%d" % srv.server_address[1]
        box.coder = {"id": "qwen-coder-dgx4", "model": "qwen-coder-dgx4:latest",
                     "door": box.base + cb.CHAT_PATH}
        return box

    yield make
    for s in servers:
        s.shutdown()
        s.server_close()


def _closed_port_base():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return "http://127.0.0.1:%d" % port


OTHER = {"id": "gpt-oss-120b", "model": "gpt-oss-120b",
         "door": "http://127.0.0.1:9/v1/chat/completions"}

FAST = {"poll_s": 0.02, "grace": 0.0}


# ---------------------------------------------------------------------------
# ensure_brain_mode -- the coder brain (wake)
# ---------------------------------------------------------------------------

def test_already_ready_coder_is_ok_and_starts_no_switch(door):
    box = door(mode="coder", state="ready")
    r = cb.ensure_brain_mode(box.coder, switch_base=box.base, **FAST)
    assert r["ok"] is True
    assert r["state"] == "ready"
    assert r["mode"] == "coder"
    assert box.started == []


def test_switching_then_ready_reports_loading_in_hebrew_and_english(door):
    box = door(mode="chat", state="ready", switch_gets=3)
    seen = []
    r = cb.ensure_brain_mode(box.coder, on_status=seen.append, switch_base=box.base, **FAST)
    assert r["ok"] is True and r["state"] == "ready" and r["mode"] == "coder"
    assert box.started == ["coder"]
    assert any(LOADING_HE in s and LOADING_EN in s for s in seen), seen
    assert LOADING_HE not in r["text"]           # the final text says ready, not loading
    assert "eran4" in r["text"]


def test_409_waits_for_the_other_switch_then_asks_again(door):
    box = door(mode="chat", state="switching", target="chat", remaining=2, switch_gets=2)
    seen = []
    r = cb.ensure_brain_mode(box.coder, on_status=seen.append, switch_base=box.base, **FAST)
    assert r["ok"] is True and r["mode"] == "coder", r
    assert box.posts == ["coder", "coder"]        # refused once (409), then accepted
    assert box.started == ["coder"]
    assert seen, "the user must be told eran4 is busy with another switch"


def test_timeout_is_a_state_not_an_exception(door):
    box = door(mode="chat", state="ready", finish="never", switch_gets=10 ** 6)
    t0 = time.monotonic()
    r = cb.ensure_brain_mode(box.coder, switch_base=box.base, timeout=0.3, **FAST)
    assert time.monotonic() - t0 < 5
    assert r["ok"] is False
    assert r["state"] == "timeout"
    assert r["text"] and any("֐" <= ch <= "׿" for ch in r["text"])   # Hebrew too


def test_switch_error_carries_the_detail_and_says_chat_mode(door):
    box = door(mode="chat", state="ready", finish="error", switch_gets=2,
               error_detail="MemAvailable 31 GiB < floor")
    r = cb.ensure_brain_mode(box.coder, switch_base=box.base, **FAST)
    assert r["ok"] is False
    assert r["state"] == "error"
    assert r["mode"] == "chat"
    assert "MemAvailable 31 GiB < floor" in r["text"]


def test_connection_refused_is_a_clear_status_never_a_raise():
    base = _closed_port_base()
    coder = {"model": "qwen-coder-dgx4:latest", "door": base + cb.CHAT_PATH}
    r = cb.ensure_brain_mode(coder, switch_base=base, **FAST)
    assert r["ok"] is False
    assert r["state"] == "unreachable"
    assert "eran4" in r["text"]


def test_5xx_on_mode_like_the_shim_today_is_unreachable(door):
    box = door(get_status=502)
    r = cb.ensure_brain_mode(box.coder, switch_base=box.base, **FAST)
    assert r["ok"] is False
    assert r["state"] == "unreachable"
    assert "502" in r["text"]


def test_door_without_a_mode_api_is_sent_to_directly(door):
    box = door(missing=True)
    r = cb.ensure_brain_mode(box.coder, switch_base=box.base, **FAST)
    assert r["ok"] is True
    assert r["state"] == "no-switch"


def test_wait_false_starts_the_switch_and_returns_at_once(door):
    box = door(mode="chat", state="ready", switch_gets=50)
    r = cb.ensure_brain_mode(box.coder, wait=False, switch_base=box.base, **FAST)
    assert r["ok"] is False
    assert r["state"] == "switching"
    assert LOADING_HE in r["text"] and LOADING_EN in r["text"]
    assert box.started == ["coder"]
    assert box.gets == 0


def test_should_stop_ends_the_wait_promptly(door):
    box = door(mode="chat", state="ready", finish="never", switch_gets=10 ** 6)
    t_stop = time.monotonic() + 0.15
    t0 = time.monotonic()
    r = cb.ensure_brain_mode(box.coder, switch_base=box.base, timeout=30,
                             should_stop=lambda: time.monotonic() > t_stop, **FAST)
    assert time.monotonic() - t0 < 3
    assert r["ok"] is False and r["state"] == "stopped"


def test_a_newer_choice_supersedes_a_wake_in_progress(door):
    box = door(mode="chat", state="ready", finish="never", switch_gets=10 ** 6)
    out = {}
    th = threading.Thread(target=lambda: out.update(cb.ensure_brain_mode(
        box.coder, switch_base=box.base, timeout=20, **FAST)))
    th.start()
    t_end = time.monotonic() + 5
    while not box.started and time.monotonic() < t_end:
        time.sleep(0.01)
    assert box.started == ["coder"]
    cb.ensure_brain_mode(OTHER, switch_base=box.base, timeout=0.5, **FAST)   # he picked GPT-OSS
    th.join(3)
    assert not th.is_alive()
    assert out["state"] == "superseded"


def test_garbage_brains_never_raise():
    for brain in ({}, {"door": "not a url"}, {"door": None, "model": None}, None):
        r = cb.ensure_brain_mode(brain, background=False, **FAST)
        assert isinstance(r, dict) and "ok" in r and "text" in r


# ---------------------------------------------------------------------------
# ensure_brain_mode -- any other brain (release eran4 back to chat, in background)
# ---------------------------------------------------------------------------

def test_other_brain_releases_a_loaded_coder(door):
    box = door(mode="coder", state="ready")
    r = cb.ensure_brain_mode(OTHER, background=False, switch_base=box.base, **FAST)
    assert r["ok"] is True
    assert box.posts == ["chat"]


def test_other_brain_does_nothing_when_eran4_is_already_chat(door):
    box = door(mode="chat", state="ready")
    r = cb.ensure_brain_mode(OTHER, background=False, switch_base=box.base, **FAST)
    assert r["ok"] is True
    assert box.posts == []


def test_other_brain_release_is_non_blocking(door):
    box = door(mode="coder", state="ready", get_delay=1.0)
    t0 = time.monotonic()
    r = cb.ensure_brain_mode(OTHER, switch_base=box.base, **FAST)
    assert time.monotonic() - t0 < 0.5
    assert r["ok"] is True
    t_end = time.monotonic() + 5
    while box.posts != ["chat"] and time.monotonic() < t_end:
        time.sleep(0.02)
    assert box.posts == ["chat"]


def test_other_brain_with_eran4_unreachable_is_still_ok():
    base = _closed_port_base()
    r = cb.ensure_brain_mode(OTHER, background=False, switch_base=base, **FAST)
    assert r["ok"] is True          # GPT-OSS lives on eran2; eran4 being down is not his problem


# ---------------------------------------------------------------------------
# which brain is behind the switch
# ---------------------------------------------------------------------------

def test_only_the_eran4_coder_door_is_behind_the_switch():
    gated = [b["id"] for b in cb.all_brains() if cb.is_switch_door(b["door"])]
    assert gated == ["qwen-coder-dgx4"]
    assert cb.is_switch_door(None) is False
    assert cb.is_switch_door("garbage") is False


# ---------------------------------------------------------------------------
# BrainModeGate -- the desktop's selection/send logic, no Qt
# ---------------------------------------------------------------------------

class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def _gate(clock=None):
    base = "https://dgx4.example:8450"
    g = cb.BrainModeGate(switch_base=base, ttl_s=300, clock=clock or Clock())
    coder = {"model": "qwen-coder-dgx4:latest", "door": base + cb.CHAT_PATH}
    return g, coder


def test_gate_selecting_the_coder_wakes_and_holds_sends_until_ready():
    g, coder = _gate()
    assert g.on_select(coder) == "wake"
    assert g.on_send(coder["door"], coder["model"]) == "hold"
    assert g.on_send(coder["door"], coder["model"], resend=True) == "hold-resend"
    ok = {"ok": True, "state": "ready", "model": coder["model"]}
    assert g.on_result(coder["door"], coder["model"], ok) == "dispatch"
    assert g.on_send(coder["door"], coder["model"]) == "send"


def test_gate_selecting_another_brain_releases_and_never_holds():
    g, _coder = _gate()
    assert g.on_select(OTHER) == "release"
    assert g.on_send(OTHER["door"], OTHER["model"]) == "send"


def test_gate_reselecting_the_coder_re_checks_the_box():
    g, coder = _gate()
    g.mark_ready(coder["model"])
    assert g.on_send(coder["door"], coder["model"]) == "send"
    assert g.on_select(coder) == "wake"
    assert g.on_send(coder["door"], coder["model"]) == "hold"


def test_gate_ready_expires_after_ttl():
    clock = Clock()
    g, coder = _gate(clock)
    g.mark_ready(coder["model"])
    clock.t += 299
    assert g.on_send(coder["door"], coder["model"]) == "send"
    clock.t += 2
    assert g.on_send(coder["door"], coder["model"]) == "hold"


def test_gate_a_successful_coder_turn_refreshes_ready():
    clock = Clock()
    g, coder = _gate(clock)
    g.mark_ready(coder["model"])
    clock.t += 250
    g.on_turn_done(coder["door"], coder["model"])
    clock.t += 250
    assert g.on_send(coder["door"], coder["model"]) == "send"


def test_gate_failed_wake_keeps_messages_queued():
    g, coder = _gate()
    g.on_select(coder)
    for state in ("error", "timeout", "unreachable"):
        bad = {"ok": False, "state": state, "model": coder["model"]}
        assert g.on_result(coder["door"], coder["model"], bad) == "keep"
        assert g.on_send(coder["door"], coder["model"]) == "hold"


def test_gate_superseded_wake_retries_when_the_coder_is_still_picked():
    g, coder = _gate()
    sup = {"ok": False, "state": "superseded", "model": coder["model"]}
    assert g.on_result(coder["door"], coder["model"], sup) == "retry"
    assert g.on_result(OTHER["door"], OTHER["model"], sup) == "dispatch"
    stopped = {"ok": False, "state": "stopped", "model": coder["model"]}
    assert g.on_result(coder["door"], coder["model"], stopped) == "keep"


def test_gate_no_switch_door_counts_as_ready():
    g, coder = _gate()
    r = {"ok": True, "state": "no-switch", "model": coder["model"]}
    assert g.on_result(coder["door"], coder["model"], r) == "dispatch"
    assert g.on_send(coder["door"], coder["model"]) == "send"


def test_gate_turn_failed_because_coder_asleep_invalidates_and_wakes():
    g, coder = _gate()
    g.mark_ready(coder["model"])
    msg = 'HTTPError: HTTP Error 503: {"error":"coder asleep - pick Qwen3-Coder-Next in the Brain menu to wake it"}'
    assert g.on_turn_failed(coder["door"], coder["model"], msg) is True
    assert g.on_send(coder["door"], coder["model"]) == "hold"


def test_gate_other_failures_do_not_trigger_a_wake():
    g, coder = _gate()
    g.mark_ready(coder["model"])
    assert g.on_turn_failed(coder["door"], coder["model"], "timeout: read timed out") is False
    assert g.on_send(coder["door"], coder["model"]) == "send"
    assert g.on_turn_failed(OTHER["door"], OTHER["model"], "HTTP Error 503") is False


# ---------------------------------------------------------------------------
# the tailnet twin (taste.py POST /chat)
# ---------------------------------------------------------------------------

def _bomb(*a, **kw):
    raise AssertionError("the twin reached the model / history while the coder was asleep")


@pytest.fixture
def twin(monkeypatch, tmp_path):
    import taste
    srvs = []

    def start(brain):
        monkeypatch.setattr(taste, "current_brain", lambda: dict(
            brain, max_tokens=50, temperature=0.3, source="test"))
        srv = ThreadingHTTPServer(("127.0.0.1", 0), taste.Handler)
        srv.daemon_threads = True
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        srvs.append(srv)
        return "http://127.0.0.1:%d" % srv.server_address[1]

    yield taste, start
    for s in srvs:
        s.shutdown()
        s.server_close()


def _chat(url, text="שלום"):
    req = urllib.request.Request(url + "/chat", data=json.dumps({"message": text}).encode("utf-8"),
                                 method="POST", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.status, json.loads(r.read().decode("utf-8"))


def test_twin_asleep_coder_returns_the_loading_text_and_never_calls_the_model(door, twin, monkeypatch):
    taste, start = twin
    box = door(mode="chat", state="ready", switch_gets=50)
    monkeypatch.setattr(cb, "SWITCH_DOOR_BASE", box.base)
    for name in ("call_model", "append_history", "build_context", "load_history"):
        monkeypatch.setattr(taste, name, _bomb)
    url = start({"door": box.coder["door"], "model": box.coder["model"]})
    code, j = _chat(url)
    assert code == 200
    assert LOADING_HE in j["reply"] and LOADING_EN in j["reply"]
    assert j["mode"]["state"] == "switching"
    assert box.started == ["coder"]


def test_twin_unreachable_coder_door_says_so(twin, monkeypatch):
    taste, start = twin
    base = _closed_port_base()
    monkeypatch.setattr(cb, "SWITCH_DOOR_BASE", base)
    for name in ("call_model", "append_history", "build_context", "load_history"):
        monkeypatch.setattr(taste, name, _bomb)
    url = start({"door": base + cb.CHAT_PATH, "model": "qwen-coder-dgx4:latest"})
    code, j = _chat(url)
    assert code == 200
    assert j["mode"]["state"] == "unreachable"
    assert "eran4" in j["reply"]


def _fake_turn(taste, monkeypatch, tmp_path, calls):
    monkeypatch.setattr(taste, "load_history", lambda: [])
    monkeypatch.setattr(taste, "build_context", lambda msg: {
        "recall": [], "standard_reqs": [], "standard_secs": [], "project": [],
        "ramchat": [], "quorum": []})
    monkeypatch.setattr(taste, "context_to_system_block", lambda ctx: "")
    monkeypatch.setattr(taste, "build_messages", lambda *a, **kw: [{"role": "user", "content": "x"}])
    monkeypatch.setattr(taste, "append_history", lambda *a, **kw: None)
    monkeypatch.setattr(taste, "CONTEXT_LOG_PATH", str(tmp_path / "ctx.jsonl"))

    def call_model(messages, **kw):
        calls.append(kw)
        return {"choices": [{"message": {"content": "pong"}}], "usage": {"completion_tokens": 1}}
    monkeypatch.setattr(taste, "call_model", call_model)


def test_twin_ready_coder_answers_normally(door, twin, monkeypatch, tmp_path):
    taste, start = twin
    box = door(mode="coder", state="ready")
    monkeypatch.setattr(cb, "SWITCH_DOOR_BASE", box.base)
    calls = []
    _fake_turn(taste, monkeypatch, tmp_path, calls)
    url = start({"door": box.coder["door"], "model": box.coder["model"]})
    code, j = _chat(url)
    assert code == 200 and j["reply"] == "pong"
    assert len(calls) == 1
    assert box.started == []


def test_twin_door_error_body_is_shown_not_an_empty_reply(twin, monkeypatch, tmp_path):
    taste, start = twin
    calls = []
    _fake_turn(taste, monkeypatch, tmp_path, calls)
    monkeypatch.setattr(taste, "call_model", lambda messages, **kw: {"error": ASLEEP})
    url = start({"door": "http://127.0.0.1:9/v1/chat/completions", "model": "gpt-oss-120b"})
    code, j = _chat(url)
    assert code == 200
    assert "coder asleep" in j["reply"]
    assert j["reply"] != "(empty reply)"


# ---------------------------------------------------------------------------
# the engine must surface the door's 503 "coder asleep" instead of "(nothing)"
# ---------------------------------------------------------------------------

ASLEEP = "coder asleep - pick Qwen3-Coder-Next in the Brain menu to wake it"


@pytest.fixture
def asleep_door():
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            if n:
                self.rfile.read(n)
            out = json.dumps({"error": ASLEEP}).encode("utf-8")
            self.send_response(503)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield "http://127.0.0.1:%d%s" % (srv.server_address[1], cb.CHAT_PATH)
    srv.shutdown()
    srv.server_close()


def test_engine_stream_surfaces_the_503_body(asleep_door):
    import coder_engine as engine
    settings = {"door": asleep_door, "model": "qwen-coder-dgx4:latest", "max_tokens": 50}
    with pytest.raises(engine.DoorError) as ei:
        engine.stream_completion([{"role": "user", "content": "hi"}], settings, lambda c: None,
                                 timeout=10)
    assert "503" in str(ei.value) and "coder asleep" in str(ei.value)


def test_engine_blocking_surfaces_an_error_body_instead_of_empty_text(asleep_door):
    import coder_engine as engine
    settings = {"door": asleep_door, "model": "qwen-coder-dgx4:latest", "max_tokens": 50}
    with pytest.raises(engine.DoorError) as ei:
        engine.blocking_completion([{"role": "user", "content": "hi"}], settings, timeout=10)
    assert "coder asleep" in str(ei.value)
    g, _coder = _gate()
    coder = {"model": "qwen-coder-dgx4:latest", "door": g.switch_base + cb.CHAT_PATH}
    g.mark_ready(coder["model"])
    assert g.on_turn_failed(coder["door"], coder["model"], "DoorError: " + str(ei.value)) is True


def test_twin_other_brain_never_touches_the_switch(door, twin, monkeypatch, tmp_path):
    taste, start = twin
    box = door(mode="coder", state="ready")
    monkeypatch.setattr(cb, "SWITCH_DOOR_BASE", box.base)
    calls = []
    _fake_turn(taste, monkeypatch, tmp_path, calls)
    url = start({"door": "http://127.0.0.1:9/v1/chat/completions", "model": "gpt-oss-120b"})
    code, j = _chat(url)
    assert code == 200 and j["reply"] == "pong"
    assert box.posts == [] and box.gets == 0
