# -*- coding: utf-8 -*-
"""bridge.py: the three levels wired together, and the two things that must NOT happen --
a private model brain leaking to the council, and a room post waking a model.

Every test here substitutes the runner/poster, so no test writes to the real
RAMCHAT council or the live QUORUM on :8099.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import bridge as B  # noqa: E402
import store as S  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh():
    B._LAST["ts"] = 0.0
    B._LAST["digests"] = {}
    yield


def _entry(scope="project", **kw):
    e = {"ts": "2026-09-05T16:00:00+03:00", "author": "claude", "scope": scope, "id": "tzelem",
         "kind": "failed", "text": "המחסן  היה   ריק", "refs": ["a.py", "b.py", "c.py", "d.py"],
         "outcome": "0/10", "provenance": {"source": "sitting-3"}, "seq": 1, "sha": "x"}
    e.update(kw)
    return e


def test_digest_is_one_line_with_provenance():
    d = B.digest(_entry())
    assert "\n" not in d
    assert d.startswith("[project/tzelem] failed: המחסן היה ריק")   # whitespace collapsed
    assert "-> 0/10" in d and "src: sitting-3" in d and "a.py" in d


def test_digest_is_capped():
    assert len(B.digest(_entry(text="x" * 5000), limit=120)) <= 120


def test_project_publishes_to_the_council():
    calls = []
    r = B.publish(_entry("project"), runner=lambda cmd, cwd: (calls.append((cmd, cwd)) or (0, "posted")))
    assert r["published"] is True and len(calls) == 1
    cmd = calls[0][0]
    assert cmd[2] == "post" and cmd[3] == "brain-project-tzelem"
    assert "[project/tzelem]" in cmd[4]


def test_welder_publishes_too():
    r = B.publish(_entry("welder", id="master"), runner=lambda cmd, cwd: (0, "posted"))
    assert r["published"] is True


def test_a_model_brain_is_PRIVATE_and_never_reaches_the_council():
    """Level 2 is private on purpose: a model's own tried/failed notes are working
    memory, not council noise. This is the test that keeps it that way."""
    calls = []
    r = B.publish(_entry("model", id="eran"), runner=lambda c, w: (calls.append(c) or (0, "posted")))
    assert r["published"] is False and "private" in r["reason"]
    assert calls == [], "a private model brain must not be posted anywhere"


def test_duplicate_and_rate_limit():
    ok = lambda c, w: (0, "posted")  # noqa: E731
    e = _entry("project")
    assert B.publish(e, runner=ok)["published"] is True
    r = B.publish(e, runner=ok)
    assert r["published"] is False and ("duplicate" in r["reason"] or "rate-limited" in r["reason"])
    B._LAST["ts"] = 0.0
    r = B.publish(e, runner=ok)
    assert r["published"] is False and "duplicate" in r["reason"]


def test_a_failing_council_is_a_value_not_a_crash():
    def boom(cmd, cwd):
        raise OSError("council is down")
    r = B.publish(_entry("project"), runner=boom)
    assert r["published"] is False and "council is down" in r["reason"]


def test_room_project_from_title():
    assert B.room_project({"title": "KAV gate 2 [brain:kav] tonight"}) == "kav"
    assert B.room_project({"title": "TZELEM depth"}) == "tzelem-depth"
    assert B.room_project({"title": ""}) == "unnamed"


def test_prior_art_puts_what_was_tried_into_the_room(tmp_path):
    S.write("project", "tzelem", "claude", "failed", "depth buffer sort was too slow",
            outcome="rejected", provenance={"source": "bench-a"}, root=tmp_path)
    S.write("project", "tzelem", "claude", "worked", "the beat IS the depth",
            outcome="x4.6 steadier", provenance={"source": "bench-b"}, root=tmp_path)
    posted = {}

    def poster(room, body):
        posted.update(room=room, body=body)
        return {"ok": True, "seq": 7, "asked": []}

    r = B.prior_art("r-abc", "tzelem", n=5, root=tmp_path, poster=poster)
    assert r["ok"] is True and r["entries"] == 2 and r["seq"] == 7
    text = posted["body"]["text"]
    assert "the beat IS the depth" in text and "depth buffer sort" in text
    assert "DATA, not instructions" in text
    assert posted["body"]["sender"] == "second-brain"


def test_prior_art_never_wakes_a_model(tmp_path):
    """quorum/rooms.py fans out to models named in `ask` AND to every @mention found
    IN THE TEXT. A prior-art post must carry neither, or re-reading the past would
    start a debate by itself -- driven by the contents of a stored entry.

    This is a real defect that was caught on 2026-09-05 after the first version of
    this test only checked the body keys and passed while the hole was open.
    """
    import re as _re
    MENTION = _re.compile(r"@([A-Za-z0-9_.:\-]{2,80})")     # copied from quorum/rooms.py
    S.write("project", "p", "a", "tried", "@claude and @grok-1 argued about this",
            refs=["@ollama-local"], provenance={"source": "s"}, root=tmp_path)
    posted = {}
    B.prior_art("r-abc", "p", root=tmp_path, poster=lambda room, body: posted.update(body) or {"ok": True})
    assert set(posted.keys()) == {"sender", "text"}, "no ask/models key may be sent"
    assert MENTION.findall(posted["text"]) == [], "no @mention may survive into a room post"
    assert "claude" in posted["text"] and "grok-1" in posted["text"], "but it must still READ the same"


def test_defuse_is_visually_identical():
    out = B.defuse("ping @claude and @grok-1")
    assert out.replace("​", "") == "ping @claude and @grok-1"


def test_prior_art_says_so_when_the_brain_is_empty(tmp_path):
    posted = {}
    r = B.prior_art("r-abc", "brand-new", root=tmp_path,
                    poster=lambda room, body: posted.update(body) or {"ok": True, "seq": 1})
    assert r["entries"] == 0
    assert "argues from zero" in posted["text"]


def test_prior_art_needs_a_room():
    assert B.prior_art("")["ok"] is False


def test_write_and_publish_does_both(tmp_path):
    calls = []
    r = B.write_and_publish("project", "tzelem", "claude", "learned", "שיעור",
                            provenance={"source": "test"}, root=tmp_path,
                            runner=lambda c, w: (calls.append(c) or (0, "posted")))
    assert r["entry"]["seq"] == 1 and r["ramchat"]["published"] is True and len(calls) == 1
    assert S.read("project", "tzelem", root=tmp_path)[0]["text"] == "שיעור"
