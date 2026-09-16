# -*- coding: utf-8 -*-
r"""ONE autouse fixture that makes this suite hermetic (Phase-2 defect #18).

Before 2026-09-06 the suite was green and dishonest: `almido_whoami` did a real GET to the
live QUORUM on :8099 and really spawned `claude --version`; pointing QUORUM at a dead port
cost 2.04 s per connect on this PC (63 % of the file's runtime); and process-global state
(STATE, _BRAIN, the announce latch, the cached AuditLog) leaked between tests so the order
they ran in changed the result.

Everything a test could reach OUTSIDE this repo is cut here, in one place, so a new test
cannot forget: no council post, no live HTTP, no subprocess, no write into
~/.iddo-harness or D:\CLAUDE\iddo-harness. A test that WANTS one of them re-patches it
itself, and then it is visible in that test.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import almido_mcp as M  # noqa: E402

BRAIN = r"D:\CLAUDE\alma-second-brain-system"

# The real functions, kept before anything is patched, so a test that WANTS the network or a
# subprocess can hand exactly one of them back instead of importing a second copy of the module.
REAL = {"http_json": M.http_json, "run": M.run, "ramchat_post": M.ramchat_post,
        "tcp_open": M._tcp_open}


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    """No network, no subprocess, no council, no live audit -- unless a test asks."""
    monkeypatch.setattr(M, "AUDIT", tmp_path / "almido-audit.jsonl")
    M._AUDITLOG.update(log=None, path=None)

    monkeypatch.setenv("ALMIDO_ANNOUNCE", "0")
    monkeypatch.setenv("ALMIDO_SECURE_KEY", "0")   # the real icacls run is tested once, on purpose
    monkeypatch.setattr(M, "ramchat_post", lambda text: (True, "posted (stubbed)"))
    monkeypatch.setattr(M, "QUORUM", "http://127.0.0.1:9")          # discard port, never listens
    monkeypatch.setattr(M, "http_json", _refuse("http_json"))
    monkeypatch.setattr(M, "run", _refuse("run"))
    monkeypatch.setattr(M, "_tcp_open", lambda url, timeout=2.0: False)

    monkeypatch.setenv("ALMA_BRAIN_ROOT", str(tmp_path / "store"))
    monkeypatch.setenv("ALMA_BRAIN_PROPOSALS", str(tmp_path / "proposals"))

    M.STATE.update(claude_calls=0, claude_failures=0, started=None, client={})
    M._ANNOUNCE["done"] = False
    yield
    M.STATE.update(claude_calls=0, claude_failures=0, started=None, client={})
    M._ANNOUNCE["done"] = False
    M._AUDITLOG.update(log=None, path=None)


def _refuse(what):
    def _stub(*a, **k):
        raise AssertionError(
            "%s reached the real world in a test. Patch it in the test that needs it." % what)
    return _stub


@pytest.fixture()
def audit_rows(tmp_path):
    """Read back the rows almido just wrote, in order."""
    import json

    def _read():
        path = tmp_path / "almido-audit.jsonl"
        if not path.is_file():
            return []
        return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    return _read


@pytest.fixture()
def brain_isolated(monkeypatch):
    """The real second-brain package against a temp store, with the council stubbed."""
    b = M.brain()
    assert b and "error" not in b, "second brain must import from %s" % BRAIN
    monkeypatch.setattr(b["bridge"], "publish", lambda entry, **k: {"published": False, "reason": "test"})
    return b
