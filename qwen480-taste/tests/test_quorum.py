# לזכרה של עלמה ז״ל
"""Tests for coder_quorum.py — the ALMAWARE Coder <-> QUORUM bridge.

Everything here talks to a FAKE QUORUM built in-process with stdlib
http.server on an ephemeral loopback port. Nothing here ever touches the real
QUORUM on :8099, starts a real debate, or reaches a real model — per the
ONE HARNESS split, this slice owns coder_quorum.py only.
"""
from __future__ import annotations

import http.server
import json
import os
import sys
import threading
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import coder_quorum as cq


# ── fake QUORUM server ────────────────────────────────────────────────────────

FAKE_MODELS = {
    "ok": True,
    "models": [
        {"id": "gpt-oss-120b", "health": {"state": "up"}},
        {"id": "glm-5.2", "health": {"state": "down"}},
        {"id": "claude", "health": {"state": "installed"}},
        {"id": "alma:nemotron", "health": {"state": "up"}},
        {"id": "ollama-local:qwen2.5-coder:7b", "health": {"state": "up"}},
        {"id": "no-health-field"},
    ],
}

# (event, data) sequences the fake /debate replies with, keyed by topic —
# shaped like real quorum/shakla.py frames (plan -> status -> delta -> done,
# always ending in "done" even when an "error" frame appeared earlier).
_HAPPY = [
    ("plan", {"agents": [{"model": "a"}, {"model": "b"}], "rounds": 1,
              "form": "shakla-vetarya"}),
    ("status", {"agent": "shakla", "round": 0, "state": "round-start", "label": "עמדות"}),
    ("delta", {"agent": "0:a", "model": "a", "round": 0, "text": "hi "}),
    ("delta", {"agent": "0:a", "model": "a", "round": 0, "text": "there"}),
    ("status", {"agent": "synth", "model": "a", "state": "writing"}),
    ("delta", {"agent": "synth", "model": "a", "text": "conclusion"}),
    ("done", {"topic": "hello world", "synth_model": "a", "synthesis": "conclusion",
              "transcript": [{"round": 0, "model": "a", "text": "hi there"}],
              "live": True, "elapsed": 0.2}),
]

_ERR = [
    ("plan", {"agents": [{"model": "a"}, {"model": "b"}], "rounds": 1}),
    ("status", {"agent": "shakla", "round": 0, "state": "round-start"}),
    ("error", {"agent": "shakla", "error": "backend", "note": "boom"}),
    ("done", {"topic": "ERR", "synth_model": "", "synthesis": "",
              "transcript": [], "live": False, "elapsed": 0.1}),
]

# 1.5s between frames — enough that a cancel issued right after the first
# frame proves it stopped the stream early rather than merely finishing fast.
_SLOW_DELAY = 1.5
_SLOW = [
    ("plan", {"agents": [{"model": "a"}, {"model": "b"}], "rounds": 1}),
    ("status", {"agent": "shakla", "round": 0, "state": "round-start"}),
    ("delta", {"agent": "0:a", "model": "a", "round": 0, "text": "slow…"}),
    ("status", {"agent": "shakla", "round": 0, "state": "done"}),
    ("done", {"topic": "SLOW", "synth_model": "a", "synthesis": "ok",
              "transcript": [], "live": True, "elapsed": 6.0}),
]


class _FakeQuorumHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):  # keep pytest output clean
        pass

    def _sse_open(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True

    def _sse(self, event, data) -> bool:
        frame = ("event: %s\ndata: %s\n\n" % (event, json.dumps(data, ensure_ascii=False))).encode("utf-8")
        try:
            self.wfile.write(frame)
            self.wfile.flush()
            return True
        except Exception:
            return False

    def do_GET(self):
        if self.path == "/api/models":
            body = json.dumps(FAKE_MODELS, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(n) if n else b"{}"
        try:
            d = json.loads(raw or b"{}")
        except Exception:
            d = {}
        if self.path != "/debate":
            self.send_response(404)
            self.end_headers()
            return
        topic = str(d.get("topic") or "")
        self._sse_open()
        if topic == "ERR":
            script = _ERR
        elif topic == "SLOW":
            script = _SLOW
        else:
            script = _HAPPY
        for i, (name, data) in enumerate(script):
            if not self._sse(name, data):
                return  # client disconnected (cancel()) — stop sending, like the real server would notice on its next write
            if topic == "SLOW" and i < len(script) - 1:
                time.sleep(_SLOW_DELAY)


@pytest.fixture
def fake_quorum():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _FakeQuorumHandler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    url = "http://127.0.0.1:%d" % srv.server_address[1]
    try:
        yield url
    finally:
        srv.shutdown()
        srv.server_close()
        t.join(timeout=2)


# ── seatable() ────────────────────────────────────────────────────────────────

def test_seatable_reports_up_states_only(fake_quorum):
    seats = cq.seatable(timeout=5, url=fake_quorum)
    assert seats == {
        "gpt-oss-120b": True,
        "glm-5.2": False,
        "claude": False,
        "alma:nemotron": True,
        "ollama-local:qwen2.5-coder:7b": True,
        "no-health-field": False,
    }


def test_seatable_unreachable_is_empty_not_an_exception():
    # Nothing listens on port 1 (a reserved low port) — connection refused.
    seats = cq.seatable(timeout=1, url="http://127.0.0.1:1")
    assert seats == {}


def test_seatable_garbage_response_is_empty_not_an_exception():
    class _Garbage(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            body = b"not json"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Garbage)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        url = "http://127.0.0.1:%d" % srv.server_address[1]
        assert cq.seatable(timeout=3, url=url) == {}
    finally:
        srv.shutdown()
        srv.server_close()
        t.join(timeout=2)


# ── map_brain_to_quorum() ─────────────────────────────────────────────────────

def test_map_brain_exact_id_match():
    assert cq.map_brain_to_quorum("gpt-oss-120b", {"gpt-oss-120b": True}) == "gpt-oss-120b"


def test_map_brain_falls_back_to_alma_alias_when_direct_id_is_down():
    seats = {"gpt-oss-120b": False, "alma:gptoss120b": True}
    assert cq.map_brain_to_quorum("gpt-oss-120b", seats) == "alma:gptoss120b"


def test_map_brain_nemotron_alias():
    seats = {"alma:nemotron": True}
    assert cq.map_brain_to_quorum("nvidia/nemotron-3-super-120b-a12b", seats) == "alma:nemotron"


def test_map_brain_pc_ollama_seat_matches_only_its_exact_tag():
    # callers pass the brain's MODEL string (coder_desktop / taste), never its id
    seats = {"ollama-local:qwen2.5-coder:7b": True, "gpt-oss-120b": True}
    assert cq.map_brain_to_quorum("qwen2.5-coder:7b", seats) == "ollama-local:qwen2.5-coder:7b"


def test_map_brain_pc_ollama_never_borrows_a_different_local_model():
    # measured live 2026-09-15: DictaLM was the first ollama-local seat -- not Qwen2.5-Coder
    seats = {"ollama-local:aminadaven/dictalm2.0-instruct:q4_k_m": True, "ollama-local": True}
    assert cq.map_brain_to_quorum("qwen2.5-coder:7b", seats) is None
    assert cq.map_brain_to_quorum("pc-local", seats) is None   # a brain id is not a model


def test_map_brain_pc_ollama_none_when_its_seat_is_down():
    seats = {"gpt-oss-120b": True, "ollama-local:qwen2.5-coder:7b": False}
    assert cq.map_brain_to_quorum("qwen2.5-coder:7b", seats) is None


def test_map_brain_kimi_alias():
    assert cq.map_brain_to_quorum("moonshotai/kimi-k3", {"nvidia-kimi-k3": True}) == "nvidia-kimi-k3"
    assert cq.map_brain_to_quorum("moonshotai/kimi-k3", {"nvidia-kimi-k3": False}) is None


def test_map_brain_real_brains_by_model_string():
    import coder_brains
    seats = {"gpt-oss-120b": True, "alma:nemotron": True, "nvidia-kimi-k3": True}
    got = {b["model"]: cq.map_brain_to_quorum(b["model"], seats) for b in coder_brains.all_brains()}
    assert got["moonshotai/kimi-k3"] == "nvidia-kimi-k3"
    assert got["gpt-oss-120b"] == "gpt-oss-120b"
    assert got["nvidia/nemotron-3-super-120b-a12b"] == "alma:nemotron"


def test_is_pc_local_seat():
    for s in ("ollama-local", "ollama-local:qwen2.5:latest", "ollama:qwen2.5-coder:7b"):
        assert cq.is_pc_local_seat(s)
    for s in ("gpt-oss-120b", "nvidia-kimi-k3", "ollama-localx", None, ""):
        assert not cq.is_pc_local_seat(s)


# ── debate budget (review fix: a fixed 900 s cut real debates short) ─────────

def test_quorum_limits_are_read_from_quorum_config(tmp_path):
    cfg = tmp_path / "config.py"
    cfg.write_text("import os\nPER_TURN_TIMEOUT = 333.0     # s\nSYNTH_TIMEOUT = 44\nX = 1\n",
                   encoding="utf-8")
    assert cq.quorum_limits(str(cfg)) == {"PER_TURN_TIMEOUT": 333.0, "SYNTH_TIMEOUT": 44.0}


def test_quorum_limits_fall_back_when_config_is_missing(tmp_path):
    assert cq.quorum_limits(str(tmp_path / "nope.py")) == {"PER_TURN_TIMEOUT": 200.0,
                                                           "SYNTH_TIMEOUT": 220.0}


def test_debate_budget_covers_quorums_own_worst_case():
    lim = {"PER_TURN_TIMEOUT": 200.0, "SYNTH_TIMEOUT": 220.0}
    assert cq.debate_budget_s(2, 2, lim) >= 2 * 3 * 200 + 220
    assert cq.debate_budget_s(6, 3, lim) >= 6 * 4 * 200 + 220
    assert cq.debate_budget_s(2, 1, lim) > 900


def test_quorum_run_default_timeout_is_sized_from_the_request():
    assert cq.QuorumRun("t", ["a", "b", "c"], rounds=2).timeout == cq.debate_budget_s(3, 2)
    assert cq.QuorumRun("t", ["a", "b"], rounds=1, timeout=10).timeout == 10.0


def test_seatable_timeout_constant_is_not_the_old_5s():
    assert cq.SEATABLE_TIMEOUT_S >= 20


def test_map_brain_never_guesses_a_family_resemblance():
    # coder's z-ai/glm-5.3-flash must NOT silently borrow QUORUM's glm-5.2 seat
    # (different size, different door) just because the names look related.
    assert cq.map_brain_to_quorum("z-ai/glm-5.3-flash", {"glm-5.2": True}) is None


def test_map_brain_none_when_nothing_seated():
    assert cq.map_brain_to_quorum("qwen-coder-dgx4:latest", {}) is None
    assert cq.map_brain_to_quorum("", {"gpt-oss-120b": True}) is None


# ── QuorumRun ─────────────────────────────────────────────────────────────────

def test_cancel_race_during_select_reports_cancelled_not_attributeerror(fake_quorum, monkeypatch):
    run = cq.QuorumRun("hello world", ["a", "b"], rounds=1, url=fake_quorum, timeout=10)
    me = threading.get_ident()
    real_select = cq.select.select

    def racing_select(r, w, x, timeout=None):
        if threading.get_ident() != me:          # the fake server's own selector
            return real_select(r, w, x, timeout)
        run.cancel()                             # resp.close() -> resp.fp is None
        return real_select(r, w, x, timeout)     # resp.fileno() -> AttributeError

    monkeypatch.setattr(cq.select, "select", racing_select)
    assert run.run(lambda n, d: None) == {"error": "cancelled"}


def test_quorum_run_happy_path_forwards_every_event_in_order(fake_quorum):
    events = []
    run = cq.QuorumRun("hello world", ["a", "b"], rounds=1, url=fake_quorum, timeout=10)
    result = run.run(lambda name, data: events.append((name, data)))

    assert [n for n, _ in events] == [n for n, _ in _HAPPY]
    assert result == _HAPPY[-1][1]           # run() returns the "done" frame's data verbatim
    assert result["live"] is True
    assert result["synth_model"] == "a"


def test_quorum_run_surfaces_error_then_still_returns_the_done_payload(fake_quorum):
    events = []
    run = cq.QuorumRun("ERR", ["a", "b"], rounds=1, url=fake_quorum, timeout=10)
    result = run.run(lambda name, data: events.append((name, data)))

    names = [n for n, _ in events]
    assert "error" in names
    assert names[-1] == "done"               # shakla's own contract: error is always followed by done
    assert result["live"] is False
    assert result == events[-1][1]


def test_quorum_run_callback_exceptions_do_not_kill_the_stream(fake_quorum):
    seen = []

    def flaky(name, data):
        seen.append(name)
        if name == "delta":
            raise RuntimeError("a broken UI slot")

    run = cq.QuorumRun("hello world", ["a", "b"], rounds=1, url=fake_quorum, timeout=10)
    result = run.run(flaky)   # must not raise, despite the callback throwing on every delta
    assert seen[-1] == "done"
    assert result["live"] is True


def test_quorum_run_cancel_stops_the_stream_promptly(fake_quorum):
    events = []
    got_first = threading.Event()

    def on_event(name, data):
        events.append((name, data))
        if name == "plan":
            got_first.set()

    run = cq.QuorumRun("SLOW", ["a", "b"], rounds=1, url=fake_quorum, timeout=30)
    result_holder = {}

    def _drive():
        result_holder["result"] = run.run(on_event)

    t = threading.Thread(target=_drive, daemon=True)
    t0 = time.monotonic()
    t.start()
    assert got_first.wait(timeout=5), "never even received the first SSE frame"

    run.cancel()
    t.join(timeout=5)
    elapsed = time.monotonic() - t0

    assert not t.is_alive(), "run() did not return after cancel()"
    # Undisturbed, this script takes 4*1.5s = 6s to reach "done"; a prompt
    # cancel must return in a small fraction of that.
    assert elapsed < 5.0, "cancel() took too long to take effect (%.1fs)" % elapsed
    assert len(events) < len(_SLOW), "received the full stream despite cancelling early"
    assert result_holder["result"].get("error") == "cancelled"


def test_quorum_run_cancel_before_start_is_a_clean_no_op(fake_quorum):
    run = cq.QuorumRun("hello world", ["a", "b"], rounds=1, url=fake_quorum, timeout=10)
    run.cancel()
    result = run.run(lambda name, data: None)
    assert result == {"error": "cancelled"}


def test_quorum_run_unreachable_server_reports_error_not_exception():
    run = cq.QuorumRun("hi", ["a", "b"], rounds=1, url="http://127.0.0.1:1", timeout=3)
    events = []
    result = run.run(lambda name, data: events.append((name, data)))
    assert events and events[0][0] == "error"
    assert "error" in result
