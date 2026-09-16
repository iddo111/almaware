# -*- coding: utf-8 -*-
r"""almido_backup: delete a source ONLY when the backup is proven, and the proof that
Iddo's gate -- not this module -- is what proves it.

> BROKEN WINDOWS LAW: test the REAL output, not a proxy.

Hermetic in the one way that matters, exactly like test_almido_computer.py: the gate these
tests exercise is the REAL `almido_gate` loaded out of Iddo's harness -- the sha256 compare,
the never-delete list and the STOP logic are his, not a mock -- but its STOP_FILE and
AUDIT_LOG are redirected into tmp_path. So:

  * a test can never create Iddo's real ~/.iddo-harness/STOP and silently disarm every
    computer-use door on this machine   [[feedback_never_test_safety_on_a_living_system]]
  * every file these tests delete is a file they created themselves, seconds earlier, under
    tmp_path -- nothing of Iddo's, and never F:\Phone-Photos-Pull
  * and yet a change to the real gate WILL break these tests, which is the point.

The case that matters most is `test_a_corrupt_backup_of_exactly_the_right_size_is_caught`:
it proves in the same test that a size-only check would have passed the corrupt copy and
deleted the original.
"""
import json
import os
import shutil
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import almido_backup as B  # noqa: E402
import almido_mcp as M  # noqa: E402


@pytest.fixture()
def bk(tmp_path, monkeypatch):
    """The real gate, pointed at a temp STOP file and a temp audit log."""
    loaded = B._load()
    gate = loaded["gate"]
    assert gate is not None, \
        "the REAL almido_gate must load, or these tests prove nothing: %s" % loaded["errors"]
    monkeypatch.setattr(gate, "HARNESS", tmp_path)
    monkeypatch.setattr(gate, "STOP_FILE", tmp_path / "STOP")
    monkeypatch.setattr(gate, "AUDIT_LOG", tmp_path / "audit.log")
    gate._RECEIPTS.clear()

    class Fixture:
        pass

    f = Fixture()
    f.gate, f.tmp = gate, tmp_path
    f.src, f.bak = tmp_path / "src", tmp_path / "bak"
    f.src.mkdir()
    f.bak.mkdir()
    f.rows = lambda: [json.loads(ln) for ln in
                      (tmp_path / "audit.log").read_text(encoding="utf-8").splitlines() if ln.strip()] \
        if (tmp_path / "audit.log").is_file() else []
    return f


def w(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
    return path


# ------------------------------------------------------------------ the gate is really there
def test_the_real_gate_loads_from_iddos_harness():
    st = B.status()
    assert st["gate_loaded"] is True, st
    assert st["gate_file"].endswith("almido_gate.py")
    assert "Perplexity-Computer-Use-Harness" in st["gate_file"], \
        "the gate must be Iddo's, not a second copy"
    assert st["algorithm"] == "sha256"


def test_nothing_is_deleted_when_the_gate_cannot_be_loaded(monkeypatch):
    """FAIL CLOSED. No gate, no delete -- and certainly no fallback to os.remove."""
    monkeypatch.setitem(B._LOADED, "gate", None)
    monkeypatch.setitem(B._LOADED, "errors", ["harness not found (simulated)"])
    for out in (B.verify(["anything"], "anywhere"), B.delete("any-receipt")):
        assert out["verdict"] == "BLOCK"
        assert "GATE UNAVAILABLE" in out["reason"]


# ------------------------------------------------------------------ the five cases
def test_a_genuine_backup_verifies_and_the_delete_really_removes_the_file(bk):
    payload = b"\xff\xd8\xff" + b"IDDO-PHOTO" * 500
    src = w(bk.src / "photo.jpg", payload)
    bak = w(bk.bak / "photo.jpg", payload)

    v = B.verify([str(src)], str(bak))
    assert v["verdict"] == "ALLOW", v
    assert v["receipt"]
    assert src.is_file(), "verify_backup must delete NOTHING"

    d = B.delete(v["receipt"])
    assert d["ok"] is True, d
    assert not src.exists(), "the source really has to be gone"
    assert bak.read_bytes() == payload, "the backup must be untouched"
    assert d["freed_bytes"] == len(payload)


def test_a_missing_backup_blocks_and_the_source_is_untouched(bk):
    src = w(bk.src / "a.bin", b"A" * 4096)
    v = B.verify([str(src)], str(bk.bak / "a.bin"))
    assert v["verdict"] == "BLOCK"
    assert v["receipt"] is None
    assert v["failures"][0]["problem"] == "backup-missing"
    assert src.stat().st_size == 4096
    assert B.delete(v["receipt"])["verdict"] == "BLOCK"


def test_a_corrupt_backup_of_exactly_the_right_size_is_caught(bk):
    """THE ONE. Same byte count, different bytes -- size/mtime would have passed it."""
    good = b"real-photo-content-0123456789" * 100
    corrupt = good[:-29] + b"X" * 29
    assert len(good) == len(corrupt)
    src = w(bk.src / "photo.jpg", good)
    bak = w(bk.bak / "photo.jpg", corrupt)

    # proof, in this test, that the cheap check would have said yes
    assert src.stat().st_size == bak.stat().st_size
    assert src.read_bytes() != bak.read_bytes()

    v = B.verify([str(src)], str(bak))
    assert v["verdict"] == "BLOCK", v
    assert v["failures"][0]["problem"] == "hash-mismatch", v["failures"]
    assert "DIFFERENT CONTENT" in v["failures"][0]["detail"]
    assert src.read_bytes() == good, "the original must still be there, byte for byte"


def test_a_directory_backup_missing_one_file_names_that_file(bk):
    names = ["IMG_%04d.jpg" % i for i in range(12)] + ["sub/VID.mp4", "sub/deep/note.txt"]
    for i, n in enumerate(names):
        w(bk.src / n, ("content-%s-%d" % (n, i)).encode() * 30)
        if n != "IMG_0007.jpg":
            w(bk.bak / n, (bk.src / n).read_bytes())

    v = B.verify([str(bk.src)], str(bk.bak))
    assert v["verdict"] == "BLOCK", v
    assert any("IMG_0007.jpg" in f["source"] for f in v["failures"]), v["failures"]
    assert v["checked"]["source_files"] == 14 and v["checked"]["backup_files"] == 13
    assert any("COUNT" in n for n in v["notes"]), v["notes"]
    assert len(list(bk.src.rglob("*.jpg"))) == 12, "not one source file may have been deleted"

    # complete the copy and it passes
    w(bk.bak / "IMG_0007.jpg", (bk.src / "IMG_0007.jpg").read_bytes())
    v = B.verify([str(bk.src)], str(bk.bak))
    assert v["verdict"] == "ALLOW", v
    d = B.delete(v["receipt"])
    assert d["deleted_files"] == 14 and not bk.src.exists()
    assert (bk.bak / "IMG_0007.jpg").is_file()


def test_the_stop_file_blocks_the_delete_even_with_a_perfect_backup(bk):
    src = w(bk.src / "x.bin", b"Z" * 2048)
    w(bk.bak / "x.bin", b"Z" * 2048)
    v = B.verify([str(src)], str(bk.bak / "x.bin"))
    assert v["verdict"] == "ALLOW", "control: the backup really is perfect"

    (bk.tmp / "STOP").write_text("engaged by a test", encoding="utf-8")
    assert B.verify([str(src)], str(bk.bak / "x.bin"))["verdict"] == "BLOCK"
    d = B.delete(v["receipt"])                       # a receipt issued BEFORE the stop
    assert d["verdict"] == "BLOCK" and "STOP" in d["reason"]
    assert src.is_file(), "STOP wins over a valid receipt"

    (bk.tmp / "STOP").unlink()
    assert B.delete(v["receipt"])["ok"] is True and not src.exists()


# ------------------------------------------------------------------ the teeth
def test_verification_and_deletion_are_two_steps_that_cannot_be_fused(bk):
    """There is no path from a path-string to a deletion."""
    src = w(bk.src / "f.bin", b"data" * 100)
    w(bk.bak / "f.bin", b"data" * 100)
    verdict, reason = bk.gate.gate("delete", str(src))
    assert verdict == "BLOCK", "gate('delete', <a string>) must never authorise anything"
    assert "verify_backup" in reason
    assert src.is_file()
    for bogus in ("", "   ", "0" * 32, str(src)):
        assert B.delete(bogus)["verdict"] == "BLOCK"
    assert src.is_file()


def test_a_receipt_is_single_use(bk):
    src = w(bk.src / "one.bin", b"1" * 512)
    w(bk.bak / "one.bin", b"1" * 512)
    v = B.verify([str(src)], str(bk.bak / "one.bin"))
    assert B.delete(v["receipt"])["ok"] is True
    again = B.delete(v["receipt"])
    assert again["verdict"] == "BLOCK" and "already been used" in again["reason"]


def test_an_expired_receipt_cannot_delete(bk):
    src = w(bk.src / "slow.bin", b"s" * 256)
    w(bk.bak / "slow.bin", b"s" * 256)
    v = bk.gate.verify_backup([str(src)], str(bk.bak / "slow.bin"), ttl=-1)
    assert v["verdict"] == "ALLOW"
    d = bk.gate.delete_verified(v["receipt"])
    assert d["verdict"] == "BLOCK" and "expired" in d["reason"]
    assert src.is_file()


def test_a_source_edited_after_verification_is_not_deleted(bk):
    src = w(bk.src / "moving.txt", b"original" * 100)
    w(bk.bak / "moving.txt", b"original" * 100)
    v = B.verify([str(src)], str(bk.bak / "moving.txt"))
    assert v["verdict"] == "ALLOW"
    os.utime(src, ns=(1, 1))
    src.write_bytes(b"the user edited this after it was verified")
    d = B.delete(v["receipt"])
    assert d["verdict"] == "BLOCK" and "source-changed" in json.dumps(d["problems"])
    assert src.is_file()


def test_a_backup_that_vanishes_between_verify_and_delete_stops_the_delete(bk):
    src = w(bk.src / "z.txt", b"zzz" * 50)
    bak = w(bk.bak / "z.txt", b"zzz" * 50)
    v = B.verify([str(src)], str(bak))
    bak.unlink()
    d = B.delete(v["receipt"])
    assert d["verdict"] == "BLOCK" and "backup-gone" in json.dumps(d["problems"])
    assert src.is_file(), "with the backup gone the source is all there is"


def test_a_backup_inside_the_source_is_refused(bk):
    """Deleting the source would have destroyed the backup with it."""
    w(bk.src / "f.txt", b"hello")
    w(bk.src / "backup" / "f.txt", b"hello")
    v = B.verify([str(bk.src)], str(bk.src / "backup"))
    assert v["verdict"] == "BLOCK"
    assert v["failures"][0]["problem"] == "backup-inside-source"


@pytest.mark.parametrize("path", [r"D:\CLAUDE\keshev-next", r"D:\CLAUDE\eran-brain",
                                  r"C:\Windows", "D:\\"])
def test_the_living_systems_are_never_deletable_however_good_the_backup(bk, path):
    """A backup does not make deleting the mic Iddo speaks through a good idea."""
    v = B.verify([path], str(bk.bak))
    assert v["verdict"] == "BLOCK", v
    assert v["failures"][0]["problem"] in ("never-delete", "source-missing"), v["failures"]
    assert v["receipt"] is None


def test_a_file_that_appeared_after_verification_is_left_behind_not_swept_away(bk):
    """Directories are never rmtree'd -- only the proven files are removed."""
    for n in ("a.txt", "b.txt"):
        w(bk.src / n, b"x" * 64)
        w(bk.bak / n, b"x" * 64)
    v = B.verify([str(bk.src)], str(bk.bak))
    newcomer = w(bk.src / "NEW-UNVERIFIED.txt", b"written after verification")
    d = B.delete(v["receipt"])
    assert newcomer.is_file(), "an unverified file must never be destroyed by a prune"
    assert d["deleted_files"] == 2
    assert d["left_behind"] and "NEW-UNVERIFIED" in json.dumps(d["left_behind"])


def test_a_dry_run_deletes_nothing_and_keeps_the_receipt(bk):
    src = w(bk.src / "d.txt", b"dry" * 100)
    w(bk.bak / "d.txt", b"dry" * 100)
    v = B.verify([str(src)], str(bk.bak / "d.txt"))
    d = B.delete(v["receipt"], dry_run=True)
    assert src.is_file() and d["would_delete_files"] == 1 and d["deleted_files"] == 0
    assert B.delete(v["receipt"])["ok"] is True and not src.exists()


def test_the_same_volume_warning_is_a_note_not_a_refusal(bk):
    src = w(bk.src / "v.bin", b"v" * 128)
    w(bk.bak / "v.bin", b"v" * 128)
    v = B.verify([str(src)], str(bk.bak / "v.bin"))
    assert v["verdict"] == "ALLOW"
    assert any("SAME volume" in n for n in v["notes"]), v["notes"]


# ------------------------------------------------------------------ the audit
def test_every_verify_and_delete_attempt_lands_in_the_gates_audit_log(bk):
    src = w(bk.src / "audited.bin", b"q" * 300)
    w(bk.bak / "audited.bin", b"q" * 300)
    B.verify([str(src)], str(bk.bak / "missing.bin"))        # a BLOCK
    v = B.verify([str(src)], str(bk.bak / "audited.bin"))    # an ALLOW
    B.delete(v["receipt"])                                   # a delete
    B.delete(v["receipt"])                                   # a replay, BLOCK

    rows = bk.rows()
    kinds = [r["kind"] for r in rows]
    assert kinds.count("verify_backup") == 2, rows
    assert kinds.count("delete_verified") >= 3, rows
    for r in rows:
        assert set(r) == {"ts", "src", "kind", "detail", "verdict", "reason"}, r
        assert r["verdict"] in ("ALLOW", "BLOCK", "CONFIRM")
        assert len(r["reason"]) > 8, "a row with no reason is not a record"
    assert any(r["verdict"] == "ALLOW" and "freed" in r["reason"] for r in rows)


def test_nothing_is_deleted_when_the_audit_cannot_be_written(bk, monkeypatch):
    """An irreversible act that leaves no record does not happen here."""
    src = w(bk.src / "unloggable.bin", b"u" * 200)
    w(bk.bak / "unloggable.bin", b"u" * 200)
    v = B.verify([str(src)], str(bk.bak / "unloggable.bin"))
    assert v["verdict"] == "ALLOW"
    monkeypatch.setattr(bk.gate, "AUDIT_LOG", bk.tmp / "no" / "such" / "\0bad" / "audit.log")
    d = B.delete(v["receipt"])
    assert d["verdict"] == "BLOCK" and "audit" in d["reason"].lower(), d
    assert src.is_file(), "no record, no deletion"


# ------------------------------------------------------------------ the MCP door
def test_the_mcp_door_declares_and_answers_every_backup_tool():
    names = {t["name"] for t in M.TOOLS}
    assert {"backup_verify", "backup_delete_verified", "backup_status"} <= names
    assert names == set(M.HANDLERS), "a tool declared without a handler, or the reverse"


def test_the_backup_tool_schemas_have_no_maxLength():
    """llama.cpp's grammar builder chokes on maxLength -- see ramchat_mcp_qwen.py."""
    schemas = [t["inputSchema"] for t in M.TOOLS if t["name"].startswith("backup_")]
    assert "maxLength" not in json.dumps(schemas)


def test_a_refused_verification_reaches_the_model_as_an_ERROR_not_a_success(tmp_path):
    """{"ok": false} inside a success envelope is how a model concludes the files are safely
    backed up when they are not."""
    src = w(tmp_path / "s" / "f.bin", b"A" * 1000)
    bad = w(tmp_path / "b" / "f.bin", b"A" * 999 + b"B")
    res = M.call_tool("backup_verify", {"sources": [str(src)], "backup": str(bad)})
    assert res.get("isError") is True, res
    body = json.loads(res["content"][0]["text"])
    assert body["failures"][0]["problem"] == "hash-mismatch"
    assert src.is_file()


def test_the_mcp_delete_tool_requires_a_receipt():
    res = M.call_tool("backup_delete_verified", {})
    assert res.get("isError") is True
    assert "receipt" in res["content"][0]["text"]


# ------------------------------------------------------------------ qwen-code's own gate
HOOK = r"D:\CLAUDE\iddo-harness\almido_gate_hook.py"


def _hook(tool_name, tool_input=None):
    import subprocess
    env = dict(os.environ, PYTHONIOENCODING="utf-8",
               ALMIDO_GATE_STOP=os.path.join(os.environ.get("TEMP", "."), "no-such-STOP"))
    p = subprocess.run([sys.executable, "-X", "utf8", HOOK], input=json.dumps(
        {"tool_name": tool_name, "tool_input": tool_input or {}, "session_id": "pytest"}),
        capture_output=True, text=True, timeout=120, env=env)
    return json.loads(p.stdout)["hookSpecificOutput"]


@pytest.mark.skipif(not os.path.isfile(HOOK), reason="the qwen-code gate hook is not installed")
@pytest.mark.parametrize("tool,expected", [("backup_verify", "allow"),
                                           ("backup_status", "allow"),
                                           ("backup_delete_verified", "ask")])
def test_qwen_codes_gate_has_a_deliberate_rule_for_every_backup_tool(tool, expected):
    """The read-only halves run; the destructive half asks Iddo. If he moves
    backup_delete_verified* into auto_allow, this test is what has to be updated with him."""
    d = _hook("mcp__almido__" + tool, {"sources": [r"D:\CLAUDE\almido\workspace\x"],
                                       "backup": r"F:\b", "receipt": "deadbeef"})
    assert d["permissionDecision"] == expected, d
    assert "no matching rule" not in d["permissionDecisionReason"], d


@pytest.mark.skipif(not os.path.isfile(HOOK), reason="the qwen-code gate hook is not installed")
def test_the_eran_fence_still_wins_over_the_new_auto_allow():
    d = _hook("mcp__almido__backup_verify", {"sources": [r"D:\CLAUDE\eran-brain"],
                                             "backup": "ssh eran3 somewhere"})
    assert d["permissionDecision"] == "deny", d
    assert "eran3" in d["permissionDecisionReason"]
