# -*- coding: utf-8 -*-
"""Tests for coder_room.py -- the addressed-room library (RoomStore, ask_brain,
ask_claude, ask_muse, address()) built for the 2026-09-15 harness-swarm task.

Nothing here touches the real RAMCHAT files, starts a real conversation, or
spawns the real `claude` binary:
  - RamchatStore / ask_muse are exercised against a stdlib fake that mimics
    ramlink.py's own API surface (get_transcript/put_transcript/get_queue/
    put_queue/Lock/now_iso) instead of importing the real module.
  - ask_brain / address() (for a brain target) talk to a fake OpenAI-shaped
    door built in-process with http.server on an ephemeral loopback port.
  - ask_claude / address() (for the 'claude' target) use an injected fake
    runner instead of subprocess-ing the real CLI.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import pytest

import coder_room as room


# ---------------------------------------------------------------------------
# address() when the store itself fails (review fix 2026-09-15)
# ---------------------------------------------------------------------------

class _FlakyStore(room.MemoryStore):
    """MemoryStore whose post() fails on the listed call numbers (1-based), the
    way RamchatStore.post fails when another agent holds ramlink's lock."""

    def __init__(self, fail_on):
        super().__init__()
        self.fail_on = set(fail_on)
        self.calls = 0

    def post(self, who, text):
        self.calls += 1
        if self.calls in self.fail_on:
            raise TimeoutError("ramlink lock held too long")
        super().post(who, text)


def test_address_keeps_going_when_a_reply_cannot_be_posted():
    store = _FlakyStore(fail_on={2})          # call 1 = Iddo's line, call 2 = first reply
    got = room.address(store, "hi", ["nope-1", "nope-2"], brains={})   # no network
    assert [w for w, _ in got] == ["nope-1@coder", "nope-2@coder"]
    assert got[0][1].startswith("[room error] reply not posted (TimeoutError")
    assert [r["who"] for r in store.read(10)] == [room.IDDO, "nope-2@coder"]


def test_address_raises_only_when_iddos_own_line_cannot_be_posted():
    store = _FlakyStore(fail_on={1})
    with pytest.raises(TimeoutError):
        room.address(store, "hi", ["nope-1"], brains={})
    assert store.read(10) == []


# ---------------------------------------------------------------------------
# Fake muse queue -- same surface as ramlink.py, backed by memory only
# ---------------------------------------------------------------------------

class _FakeLock:
    def __init__(self, *a, **kw):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeRamlink:
    """A stdlib fake of ramlink.py's Python API -- get_transcript/put_transcript
    (the room) and get_queue/put_queue (the work queue Muse is fed through),
    plus Lock and now_iso. Never touches disk."""

    Lock = _FakeLock

    def __init__(self):
        self.msgs = []
        self.shared = {"mission": "test"}
        self.queue = []
        self.put_queue_result = (True, None)

    def get_transcript(self):
        return list(self.msgs), dict(self.shared), "fake"

    def put_transcript(self, msgs, shared):
        self.msgs = list(msgs)
        self.shared = shared
        return True, None

    def get_queue(self):
        return list(self.queue), "fake"

    def put_queue(self, items):
        ok, err = self.put_queue_result
        if ok:
            self.queue = list(items)
        return ok, err

    def now_iso(self):
        return "2026-09-15T03:00:00"


@pytest.fixture
def fake_rl():
    return FakeRamlink()


# ---------------------------------------------------------------------------
# Fake OpenAI-shaped door
# ---------------------------------------------------------------------------

class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8"))
        except ValueError:
            body = {}
        self.server.requests.append(body)
        if self.server.http_error:
            self.send_response(self.server.http_error)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        payload = json.dumps({
            "choices": [{"message": {"content": self.server.reply_text}}],
            "usage": {"completion_tokens": 3},
        }).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *a):
        pass


@pytest.fixture
def fake_door():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    server.requests = []
    server.reply_text = "hello from the fake door"
    server.http_error = 0
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    port = server.server_address[1]
    try:
        yield server, "http://127.0.0.1:%d/v1/chat/completions" % port
    finally:
        server.shutdown()
        server.server_close()


class _FakeProc:
    def __init__(self, stdout="", stderr=""):
        self.stdout = stdout
        self.stderr = stderr


# ---------------------------------------------------------------------------
# MemoryStore
# ---------------------------------------------------------------------------

def test_memory_store_post_and_read_tail():
    store = room.MemoryStore()
    for i in range(5):
        store.post("iddo", "line %d" % i)
    tail = store.read(2)
    assert [row["text"] for row in tail] == ["line 3", "line 4"]
    assert all(set(row.keys()) == {"ts", "who", "text"} for row in tail)


def test_memory_store_read_zero_returns_everything():
    store = room.MemoryStore()
    store.post("iddo", "a")
    store.post("iddo", "b")
    assert [r["text"] for r in store.read(0)] == ["a", "b"]


def test_memory_store_read_mutation_does_not_leak():
    store = room.MemoryStore()
    store.post("iddo", "a")
    rows = store.read(5)
    rows[0]["text"] = "tampered"
    assert store.read(5)[0]["text"] == "a"


# ---------------------------------------------------------------------------
# RamchatStore (against the fake ramlink, never the real files)
# ---------------------------------------------------------------------------

def test_ramchat_store_post_appends_and_maps_fields(fake_rl):
    store = room.RamchatStore(ramlink_module=fake_rl)
    store.post("iddo", "hello room")
    assert len(fake_rl.msgs) == 1
    assert fake_rl.msgs[0]["who"] == "iddo"
    assert fake_rl.msgs[0]["text"] == "hello room"
    assert "at" in fake_rl.msgs[0]

    rows = store.read(5)
    assert rows == [{"ts": fake_rl.msgs[0]["at"], "who": "iddo", "text": "hello room"}]


def test_ramchat_store_read_respects_tail(fake_rl):
    store = room.RamchatStore(ramlink_module=fake_rl)
    for i in range(10):
        store.post("iddo", "m%d" % i)
    assert [r["text"] for r in store.read(3)] == ["m7", "m8", "m9"]


def test_ramchat_store_post_raises_on_write_failure(fake_rl):
    store = room.RamchatStore(ramlink_module=fake_rl)
    fake_rl.put_transcript = lambda msgs, shared: (False, "disk full")
    with pytest.raises(RuntimeError):
        store.post("iddo", "boom")


def test_ramchat_store_never_imports_real_ramlink_when_injected(fake_rl, monkeypatch):
    # If RamchatStore ever fell back to the real module despite the injection,
    # this would blow up (or write real files) -- prove it does not even try.
    def _boom(*a, **kw):
        raise AssertionError("must not import the real ramlink when a fake is injected")
    monkeypatch.setattr(room, "_real_ramlink", _boom)
    store = room.RamchatStore(ramlink_module=fake_rl)
    store.post("iddo", "safe")
    assert fake_rl.msgs[-1]["text"] == "safe"


# ---------------------------------------------------------------------------
# room_prompt
# ---------------------------------------------------------------------------

def test_room_prompt_shape_and_identity():
    lines = [{"ts": "10:00", "who": "iddo", "text": "שלום"}]
    brain = {"human_name": "Qwen3-Coder-Next", "where_he": "eran4", "door": "http://x/y"}
    messages = room.room_prompt(lines, brain)
    assert [m["role"] for m in messages] == ["system", "user"]
    assert "Qwen3-Coder-Next" in messages[0]["content"]
    assert "eran4" in messages[0]["content"]
    assert "שלום" in messages[1]["content"]
    assert "iddo" in messages[1]["content"]


def test_room_prompt_only_last_tail_lines():
    lines = [{"ts": str(i), "who": "iddo", "text": "line-%02d" % i} for i in range(12)]
    brain = {"human_name": "X", "where_he": "y", "door": "z"}
    user_content = room.room_prompt(lines, brain)[1]["content"]
    for i in range(4):
        assert ("line-%02d" % i) not in user_content
    for i in range(4, 12):
        assert ("line-%02d" % i) in user_content


def test_room_prompt_handles_empty_room():
    messages = room.room_prompt([], {"human_name": "X", "where_he": "y", "door": "z"})
    assert "empty" in messages[1]["content"]


def test_room_prompt_falls_back_when_brain_sparse():
    # Only 'model' given -- no human_name/where_he/door.
    messages = room.room_prompt([], {"model": "some-model"})
    assert "some-model" in messages[0]["content"]


# ---------------------------------------------------------------------------
# ask_brain
# ---------------------------------------------------------------------------

def test_ask_brain_returns_content_and_posts_expected_body(fake_door):
    server, door = fake_door
    brain = {"id": "x", "model": "qwen-test", "door": door, "max_tokens": 55}
    reply = room.ask_brain(brain, [{"role": "user", "content": "hi"}], timeout=5)
    assert reply == "hello from the fake door"
    sent = server.requests[-1]
    assert sent["model"] == "qwen-test"
    assert sent["max_tokens"] == 55
    assert "reasoning_effort" not in sent


def test_ask_brain_sets_low_reasoning_effort_for_gpt_oss(fake_door):
    server, door = fake_door
    brain = {"id": "g", "model": "gpt-oss-120b", "door": door, "max_tokens": 40}
    room.ask_brain(brain, [{"role": "user", "content": "hi"}], timeout=5)
    assert server.requests[-1]["reasoning_effort"] == "low"


def test_ask_brain_missing_door_or_model_is_a_room_error():
    assert room.ask_brain({}, [], timeout=1).startswith("[room error]")
    assert room.ask_brain({"model": "m"}, [], timeout=1).startswith("[room error]")


def test_ask_brain_never_raises_on_connection_failure():
    brain = {"id": "y", "model": "m", "door": "http://127.0.0.1:1/v1/chat/completions",
             "max_tokens": 10}
    reply = room.ask_brain(brain, [{"role": "user", "content": "hi"}], timeout=2)
    assert reply.startswith("[room error]")


def test_ask_brain_http_error_is_reported(fake_door):
    server, door = fake_door
    server.http_error = 500
    brain = {"id": "z", "model": "m", "door": door, "max_tokens": 10}
    reply = room.ask_brain(brain, [{"role": "user", "content": "hi"}], timeout=5)
    assert reply.startswith("[room error] HTTP 500")


# ---------------------------------------------------------------------------
# ask_claude
# ---------------------------------------------------------------------------

def test_ask_claude_uses_injected_runner_and_returns_stdout():
    seen = {}

    def runner(prompt, timeout):
        seen["prompt"] = prompt
        seen["timeout"] = timeout
        return _FakeProc(stdout="claude says hi\n")

    reply = room.ask_claude("what is the plan", timeout=30, runner=runner)
    assert reply == "claude says hi"
    assert seen["prompt"] == "what is the plan"
    assert seen["timeout"] == 30


def test_ask_claude_falls_back_to_stderr_when_stdout_empty():
    reply = room.ask_claude("x", runner=lambda p, t: _FakeProc(stdout="", stderr="warn: low battery"))
    assert reply == "warn: low battery"


def test_ask_claude_empty_both_streams():
    reply = room.ask_claude("x", runner=lambda p, t: _FakeProc(stdout="", stderr=""))
    assert reply == "(empty reply)"


def test_ask_claude_timeout_is_a_room_error():
    def runner(p, t):
        raise subprocess.TimeoutExpired(cmd=["claude"], timeout=t)
    reply = room.ask_claude("x", timeout=5, runner=runner)
    assert reply.startswith("[room error]")
    assert "5" in reply


def test_ask_claude_not_found_is_a_room_error():
    def runner(p, t):
        raise FileNotFoundError("no claude")
    reply = room.ask_claude("x", runner=runner)
    assert reply.startswith("[room error]")


def test_ask_claude_default_runner_never_opens_a_console_window(monkeypatch):
    """POPUP LAW: the real runner must pass CREATE_NO_WINDOW on Windows."""
    captured = {}

    def fake_run(cmd, **kwargs):
        captured.update(kwargs)
        captured["cmd"] = cmd
        return _FakeProc(stdout="ok")

    monkeypatch.setattr(subprocess, "run", fake_run)
    reply = room.ask_claude("hi", timeout=9)
    assert reply == "ok"
    assert captured["cmd"] == ["claude", "-p", "--output-format", "text"]
    assert captured["input"] == "hi"
    if os.name == "nt":
        assert captured.get("creationflags") == subprocess.CREATE_NO_WINDOW


# ---------------------------------------------------------------------------
# ask_muse
# ---------------------------------------------------------------------------

def test_ask_muse_queues_a_task_shaped_like_ramlink_add(fake_rl):
    task_id = room.ask_muse("write the sql migration", ramlink_module=fake_rl)
    assert task_id.startswith("task-")
    assert len(fake_rl.queue) == 1
    task = fake_rl.queue[0]
    assert task["id"] == task_id
    assert task["targets"] == ["muse-code"]
    assert task["prompt"] == "write the sql migration"
    assert task["status"] == "open"
    assert task["claimed_by"] is None
    assert task["source"] == "room"


def test_ask_muse_strips_whitespace(fake_rl):
    room.ask_muse("  spaced out  \n", ramlink_module=fake_rl)
    assert fake_rl.queue[0]["prompt"] == "spaced out"


def test_ask_muse_reports_write_failure_without_raising(fake_rl):
    fake_rl.put_queue_result = (False, "queue disk full")
    reply = room.ask_muse("x", ramlink_module=fake_rl)
    assert reply.startswith("[room error]")
    assert fake_rl.queue == []  # nothing silently written


def test_ask_muse_never_imports_real_ramlink_when_injected(fake_rl, monkeypatch):
    def _boom(*a, **kw):
        raise AssertionError("must not import the real ramlink when a fake is injected")
    monkeypatch.setattr(room, "_real_ramlink", _boom)
    task_id = room.ask_muse("x", ramlink_module=fake_rl)
    assert task_id.startswith("task-")


# ---------------------------------------------------------------------------
# address() -- the room's one entry point
# ---------------------------------------------------------------------------

def test_address_posts_iddo_line_then_each_target_in_order(fake_door, fake_rl):
    server, door = fake_door
    server.reply_text = "brain reply"
    store = room.MemoryStore()
    brains = {"q": {"id": "q", "model": "qwen-test", "door": door, "max_tokens": 40,
                    "human_name": "Q", "where_he": "eran4"}}
    claude_calls = []

    def claude_runner(prompt, timeout):
        claude_calls.append(prompt)
        return _FakeProc(stdout="claude reply")

    replies = room.address(store, "hello room", ["q", "claude", "muse"],
                           brains=brains, claude_runner=claude_runner,
                           ramlink_module=fake_rl)

    assert replies[0] == ("q@coder", "brain reply")
    assert replies[1] == ("claude@coder", "claude reply")
    assert replies[2][0] == "muse@coder"
    assert replies[2][1].startswith("task-")
    assert len(claude_calls) == 1

    lines = store.read(10)
    assert [l["who"] for l in lines] == ["iddo", "q@coder", "claude@coder", "muse@coder"]
    assert lines[0]["text"] == "hello room"

    # Muse got the raw addressed text, not a room-context dump.
    assert fake_rl.queue[0]["prompt"] == "hello room"


def test_address_unknown_brain_id_is_one_error_line_not_a_crash():
    store = room.MemoryStore()
    replies = room.address(store, "hi", ["totally-nonexistent-brain-xyz"], brains={})
    assert replies == [("totally-nonexistent-brain-xyz@coder",
                        "[room error] unknown brain: totally-nonexistent-brain-xyz")]


def test_address_falls_back_to_real_coder_brains_catalog_when_none_given():
    # No brains= override -- must consult coder_brains.py (the sibling slice's
    # real, live catalog) rather than raise or silently skip the target.
    store = room.MemoryStore()
    replies = room.address(store, "hi", ["definitely-not-a-real-brain-id-999"])
    who, reply = replies[0]
    assert who == "definitely-not-a-real-brain-id-999@coder"
    assert reply == "[room error] unknown brain: definitely-not-a-real-brain-id-999"


def test_address_one_broken_target_does_not_silence_the_rest(fake_rl):
    store = room.MemoryStore()
    brains = {"broken": {"id": "broken", "model": "m",
                         "door": "http://127.0.0.1:1/v1/chat/completions",
                         "max_tokens": 10}}
    replies = room.address(store, "hi", ["broken", "muse"], brains=brains,
                           ramlink_module=fake_rl)
    assert replies[0][1].startswith("[room error]")
    assert replies[1][1].startswith("task-")


def test_address_caps_at_max_targets(fake_rl):
    store = room.MemoryStore()
    targets = ["nope-%d" % i for i in range(12)]
    replies = room.address(store, "hi", targets, brains={}, ramlink_module=fake_rl)
    assert len(replies) == room.MAX_TARGETS == 8
    # store has iddo's line + 8 replies, never all 12
    assert len(store.read(0)) == 9


def test_address_on_reply_callback_fires_per_reply_and_swallows_its_own_errors(fake_rl):
    store = room.MemoryStore()
    seen = []

    def on_reply(who, reply):
        seen.append((who, reply))
        raise RuntimeError("a broken UI callback must not break addressing")

    replies = room.address(store, "hi", ["muse"], on_reply=on_reply, ramlink_module=fake_rl)
    assert seen == replies


def test_address_empty_targets_only_posts_iddo_line():
    store = room.MemoryStore()
    replies = room.address(store, "just talking to myself", [])
    assert replies == []
    assert [l["who"] for l in store.read(0)] == ["iddo"]


def test_address_never_raises_even_when_store_post_fails_for_a_reply():
    class FlakyStore(room.MemoryStore):
        def post(self, who, text):
            if who != room.IDDO:
                raise RuntimeError("store is down")
            super().post(who, text)

    store = FlakyStore()
    # Review fix 2026-09-15: a failed REPLY post no longer escapes address() (the
    # old boundary broke the "never raises" contract and made the desktop offer
    # Iddo's already-posted line again). Only Iddo's own first post may raise --
    # see test_address_raises_only_when_iddos_own_line_cannot_be_posted.
    replies = room.address(store, "hi", ["muse"], ramlink_module=FakeRamlink())
    assert len(replies) == 1 and replies[0][0] == "muse@coder"
    assert replies[0][1].startswith("[room error] reply not posted (RuntimeError")
    assert [l["who"] for l in store.read(0)] == [room.IDDO]
