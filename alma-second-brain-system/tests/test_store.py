# -*- coding: utf-8 -*-
"""store.py: append-only, provenance-mandatory, Hebrew-safe, and tamper-detecting.

These are the judge's tests on the coder's module. Two of them (Hebrew round-trip,
tamper detection) are the ones that would have caught the 2026-09-03 corpus fraud.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import store as S  # noqa: E402

HE = "ערן למד לומר /ba/ — הפה נסגר"  # ERAN learned to say /ba/


def test_layout_is_scope_scope_id(tmp_path):
    p = S.brain_path("model", "eran", root=tmp_path)
    assert p == tmp_path / "scope" / "model" / "eran.jsonl"


@pytest.mark.parametrize("scope", ["project", "model", "welder"])
def test_all_three_levels_exist(tmp_path, scope):
    e = S.write(scope, "x1", "tester", "learned", "t", provenance={"source": "test"}, root=tmp_path)
    assert e["scope"] == scope and S.read(scope, "x1", root=tmp_path)[0]["text"] == "t"


def test_provenance_is_mandatory(tmp_path):
    for bad in (None, {}, {"note": "no source key"}):
        with pytest.raises(ValueError, match="provenance"):
            S.write("model", "eran", "a", "learned", "t", provenance=bad, root=tmp_path)


def test_bad_kind_scope_id_and_empty_text(tmp_path):
    ok = {"provenance": {"source": "test"}, "root": tmp_path}
    with pytest.raises(ValueError, match="kind"):
        S.write("model", "eran", "a", "invented", "t", **ok)
    with pytest.raises(ValueError, match="scope"):
        S.write("nope", "eran", "a", "learned", "t", **ok)
    with pytest.raises(ValueError, match="id"):
        S.write("model", "ERAN", "a", "learned", "t", **ok)
    with pytest.raises(ValueError, match="text"):
        S.write("model", "eran", "a", "learned", "   ", **ok)
    with pytest.raises(ValueError, match="author"):
        S.write("model", "eran", "", "learned", "t", **ok)


@pytest.mark.parametrize("evil", ["../escape", "a/b", "a\\b", "..", "a\x00b"])
def test_path_traversal_refused(tmp_path, evil):
    with pytest.raises(ValueError):
        S.brain_path("model", evil, root=tmp_path)


def test_hebrew_round_trip_and_search(tmp_path):
    S.write("model", "eran", "eran", "worked", HE, refs=["קובץ.wav"],
            outcome="F2 בטווח", provenance={"source": "sitting-4"}, root=tmp_path)
    raw = (tmp_path / "scope" / "model" / "eran.jsonl").read_text(encoding="utf-8")
    assert HE in raw, "Hebrew must be stored as Hebrew, not \\uXXXX"
    assert S.read("model", "eran", query="/ba/", root=tmp_path)[0]["text"] == HE
    assert S.read("model", "eran", query="למד", root=tmp_path), "Hebrew query must match"
    assert S.read("model", "eran", query="קובץ", root=tmp_path), "refs are searchable"
    assert S.read("model", "eran", query="nothing-like-this", root=tmp_path) == []


def test_append_only_never_rewrites(tmp_path):
    for i in range(5):
        S.write("project", "tzelem", "claude", "tried", "attempt %d" % i,
                provenance={"source": "bench"}, root=tmp_path)
    lines = (tmp_path / "scope" / "project" / "tzelem.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 5
    assert [json.loads(x)["seq"] for x in lines] == [1, 2, 3, 4, 5]


def test_read_is_newest_last_and_capped(tmp_path):
    for i in range(30):
        S.write("project", "p", "a", "tried", "n%d" % i, provenance={"source": "s"}, root=tmp_path)
    got = S.read("project", "p", n=5, root=tmp_path)
    assert [g["text"] for g in got] == ["n25", "n26", "n27", "n28", "n29"]


def test_kind_filter_and_missing_file(tmp_path):
    S.write("model", "miko", "a", "failed", "f", provenance={"source": "s"}, root=tmp_path)
    S.write("model", "miko", "a", "worked", "w", provenance={"source": "s"}, root=tmp_path)
    assert [e["kind"] for e in S.read("model", "miko", kinds=["worked"], root=tmp_path)] == ["worked"]
    assert S.read("model", "never-written", root=tmp_path) == []
    assert S.stats("model", "never-written", root=tmp_path)["entries"] == 0


def test_corrupt_line_is_skipped_not_fatal(tmp_path):
    S.write("model", "eran", "a", "learned", "good", provenance={"source": "s"}, root=tmp_path)
    p = tmp_path / "scope" / "model" / "eran.jsonl"
    with p.open("a", encoding="utf-8") as fh:
        fh.write("{not json at all\n")
        fh.write('{"ts":"x"}\n')
    assert len(S.read("model", "eran", root=tmp_path)) == 1
    assert S.stats("model", "eran", root=tmp_path)["corrupt_lines"] == 2


def test_verify_detects_a_line_rewritten_in_place(tmp_path):
    """THE 2026-09-03 TEST: silently editing a past lesson must be detectable."""
    S.write("project", "corpus", "a", "worked", "the corpus is human speech",
            provenance={"source": "fleurs"}, root=tmp_path)
    S.write("project", "corpus", "a", "learned", "second line", provenance={"source": "s"}, root=tmp_path)
    assert S.verify("project", "corpus", root=tmp_path)["ok"] is True
    p = tmp_path / "scope" / "project" / "corpus.jsonl"
    lines = p.read_text(encoding="utf-8").splitlines()
    row = json.loads(lines[0])
    row["text"] = "the corpus is TTS"                 # the fraud, committed in place
    lines[0] = json.dumps(row, ensure_ascii=False)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    v = S.verify("project", "corpus", root=tmp_path)
    assert v["ok"] is False and v["bad_sha"] == [1] and v["checked"] == 2


def test_verify_detects_a_deleted_line(tmp_path):
    for i in range(3):
        S.write("welder", "master", "a", "decided", "d%d" % i, provenance={"source": "s"}, root=tmp_path)
    p = tmp_path / "scope" / "welder" / "master.jsonl"
    lines = p.read_text(encoding="utf-8").splitlines()
    p.write_text("\n".join([lines[0], lines[2]]) + "\n", encoding="utf-8")   # line 2 removed
    v = S.verify("welder", "master", root=tmp_path)
    assert v["ok"] is False and v["bad_seq"] == [2]


def test_stats_and_list_brains(tmp_path):
    S.write("model", "eran", "eran", "learned", "a", provenance={"source": "s"}, root=tmp_path)
    S.write("model", "eran", "claude", "failed", "b", provenance={"source": "s"}, root=tmp_path)
    S.write("project", "tzelem", "claude", "worked", "c", provenance={"source": "s"}, root=tmp_path)
    st = S.stats("model", "eran", root=tmp_path)
    assert st["entries"] == 2 and st["kinds"] == {"learned": 1, "failed": 1}
    assert st["authors"] == {"eran": 1, "claude": 1} and st["first_ts"] <= st["last_ts"]
    lb = S.list_brains(root=tmp_path)
    assert lb == {"project": ["tzelem"], "model": ["eran"], "welder": []}
    assert S.list_brains("model", root=tmp_path)["model"] == ["eran"]
    with pytest.raises(ValueError):
        S.list_brains("nope", root=tmp_path)


def test_timestamp_is_local_with_offset(tmp_path):
    e = S.write("model", "eran", "a", "learned", "t", provenance={"source": "s"}, root=tmp_path)
    assert len(e["ts"]) == 25 and e["ts"][10] == "T" and e["ts"][19] in "+-"
