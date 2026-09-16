# -*- coding: utf-8 -*-
"""Tests for coder_brains.py — the ONE source of truth for ALMAWARE Coder's
brains (see coder_brains.py's module docstring for why this file exists).

No network calls here (door liveness is checked separately, by hand, with a
read-only GET /v1/models per the HARNESS SWARM task — see the sub-agent's
final report). These tests only check the *shape* and *consistency* of the
data, and that a missing/broken fleet_inventory can never take the module
down (it must fall back to the literal door bases instead of raising).

Review fix 2026-09-15: door bases come from fleet_inventory's NAMED doors
(port included). The PC-local brain is IN BRAINS (on demand) since Iddo amended
the PC-models law on 2026-09-15 02:54.
"""
from __future__ import annotations

import os
import sys
from urllib.parse import urlsplit

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import pytest

import coder_brains


REQUIRED_KEYS = {
    "id", "profile", "model", "label", "human_name", "where_he",
    "door", "max_tokens", "cost", "on_demand",
}


# --------------------------------------------------------------------- shape

def test_all_brains_returns_list_of_dicts_with_required_keys():
    brains = coder_brains.all_brains()
    assert isinstance(brains, list)
    # 5 fleet brains + the on-demand pc-local brain (Iddo amended the PC-models law 09-15)
    assert len(brains) >= 5
    for b in brains:
        assert isinstance(b, dict)
        missing = REQUIRED_KEYS - set(b.keys())
        assert not missing, "brain %r missing keys %r" % (b.get("id"), missing)


def test_all_brains_returns_a_copy_not_the_live_list():
    brains = coder_brains.all_brains()
    brains.append({"id": "intruder"})
    brains2 = coder_brains.all_brains()
    assert all(b.get("id") != "intruder" for b in brains2)
    # mutating a returned dict must not corrupt the module's own record either
    original = coder_brains.by_model("gpt-oss-120b")
    original["label"] = "TAMPERED"
    assert coder_brains.by_model("gpt-oss-120b")["label"] != "TAMPERED"


def test_ids_and_models_are_unique():
    brains = coder_brains.all_brains()
    ids = [b["id"] for b in brains]
    models = [b["model"] for b in brains]
    assert len(ids) == len(set(ids)), "duplicate brain id"
    assert len(models) == len(set(models)), "duplicate model id"


def test_cost_is_free_or_paid():
    for b in coder_brains.all_brains():
        assert b["cost"] in ("free", "paid")


def test_max_tokens_is_a_positive_int():
    for b in coder_brains.all_brains():
        assert isinstance(b["max_tokens"], int)
        assert b["max_tokens"] > 0


def test_door_is_a_chat_completions_url():
    for b in coder_brains.all_brains() + [coder_brains.PC_LOCAL_BRAIN]:
        door = b["door"]
        assert door.startswith("http://") or door.startswith("https://")
        assert door.endswith("/v1/chat/completions")


# ----------------------------------------------------------- policy: no Maverick

def test_no_maverick_anywhere():
    for b in coder_brains.all_brains():
        blob = " ".join(str(v) for v in b.values()).lower()
        assert "maverick" not in blob


# ------------------------------------------- policy: no local models on the PC

def test_pc_local_is_a_brain_on_demand_since_iddo_amended_the_law():
    # Iddo 2026-09-15 02:54-02:55: models on the PC are allowed, on demand, never
    # choking it. The only brain allowed on loopback is the on-demand pc-local one.
    assert coder_brains.PC_LOCAL_ALLOWED is True
    pc = coder_brains.by_id("pc-local")
    assert pc is not None and pc["on_demand"] is True
    assert coder_brains.by_model("qwen2.5-coder:7b") == pc   # lookups return copies
    for b in coder_brains.all_brains():
        host = urlsplit(b["door"]).hostname
        if host in ("127.0.0.1", "localhost"):
            assert b["id"] == "pc-local" and b["on_demand"] is True, "%s runs on the PC" % b["id"]


def test_pc_local_record_is_on_demand_and_says_so_in_hebrew():
    pc = coder_brains.PC_LOCAL_BRAIN
    assert not (REQUIRED_KEYS - set(pc))
    assert pc["on_demand"] is True
    assert pc["door"] == "http://127.0.0.1:11434/v1/chat/completions"
    # human text must say it runs on Iddo's PC and is small, per the task spec
    assert "מחשב" in pc["label"] + pc["where_he"]  # "PC" in Hebrew
    assert "קטן" in pc["label"] + pc["where_he"]   # "small"


def test_only_pc_local_is_on_demand():
    for b in coder_brains.all_brains():
        if b["id"] == "pc-local":
            continue
        assert b["on_demand"] is False, "%s should not be on_demand" % b["id"]


# ------------------------------------------------------------------- lookups

@pytest.mark.parametrize("model", [
    "qwen-coder-dgx4:latest",
    "gpt-oss-120b",
    "moonshotai/kimi-k3",
    "nvidia/nemotron-3-super-120b-a12b",
    "z-ai/glm-5.3-flash",
])
def test_by_model_finds_every_known_brain(model):
    b = coder_brains.by_model(model)
    assert b is not None
    assert b["model"] == model


def test_by_model_unknown_returns_none():
    assert coder_brains.by_model("no-such-model-xyz") is None


def test_by_id_roundtrips_with_by_model():
    for b in coder_brains.all_brains():
        assert coder_brains.by_id(b["id"])["model"] == b["model"]
    assert coder_brains.by_id("no-such-id") is None


def test_model_label_known_and_unknown():
    assert coder_brains.model_label("gpt-oss-120b") == "GPT-OSS 120B · eran2"
    assert coder_brains.model_label("mystery-model") == "mystery-model"
    assert coder_brains.model_label("") == "model"


def test_brain_facts_known_matches_record():
    name, where = coder_brains.brain_facts("nvidia/nemotron-3-super-120b-a12b")
    b = coder_brains.by_model("nvidia/nemotron-3-super-120b-a12b")
    assert (name, where) == (b["human_name"], b["where_he"])


def test_brain_facts_unknown_falls_back_like_identity_line_always_did():
    name, where = coder_brains.brain_facts("something-nobody-registered")
    assert name == "something-nobody-registered"
    assert where == "מוגש מהדלת שלמטה"


# --------------------------------------------------------- fleet_inventory tie-in

def test_door_base_falls_back_when_fleet_inventory_is_unavailable(monkeypatch):
    monkeypatch.setattr(coder_brains, "_fleet_inventory", lambda: None)
    got = coder_brains._door_base("eran2_gptoss", "http://1.2.3.4:8000")
    assert got == "http://1.2.3.4:8000"


def test_door_base_falls_back_when_door_unknown_or_garbage(monkeypatch):
    class _FakeFI:
        def door(self, name):
            if name == "garbage":
                return "not a url"
            raise KeyError(name)

    monkeypatch.setattr(coder_brains, "_fleet_inventory", lambda: _FakeFI())
    assert coder_brains._door_base("nosuchdoor", "http://9.9.9.9:1") == "http://9.9.9.9:1"
    assert coder_brains._door_base("garbage", "http://9.9.9.9:1") == "http://9.9.9.9:1"


def test_door_base_takes_scheme_host_and_port_from_the_inventory(monkeypatch):
    class _FakeFI:
        def door(self, name):
            assert name == "eran4_ollama"
            return "https://fake.tail.ts.net:9450/api/tags"

    monkeypatch.setattr(coder_brains, "_fleet_inventory", lambda: _FakeFI())
    assert coder_brains._door_base("eran4_ollama", "fallback") == "https://fake.tail.ts.net:9450"


def test_doors_come_from_fleet_inventory_named_doors():
    """With the real fleet_inventory.json present, every brain's door is that
    inventory's named door (scheme, host AND port) plus the chat path -- no
    private copy of a port, no literal locked into this test."""
    fi = coder_brains._fleet_inventory()
    if fi is None:
        pytest.skip("fleet_inventory.json not available on this machine")

    def base(name):
        p = urlsplit(fi.door(name))
        return "%s://%s" % (p.scheme, p.netloc)

    expected = {
        "qwen-coder-dgx4:latest": base("eran4_ollama"),
        "gpt-oss-120b": base("eran2_gptoss"),
        "moonshotai/kimi-k3": base("eran1_router"),
        "nvidia/nemotron-3-super-120b-a12b": base("eran1_router"),
        "z-ai/glm-5.3-flash": base("eran1_router"),
    }
    for model, door_base in expected.items():
        assert coder_brains.by_model(model)["door"] == door_base + coder_brains.CHAT_PATH


# --------------------------------------------------------------- coder_identity

def test_coder_identity_brain_facts_is_derived_from_coder_brains():
    import coder_identity
    expected = {b["model"]: (b["human_name"], b["where_he"])
                for b in coder_brains.all_brains()}
    assert coder_identity.BRAIN_FACTS == expected


def test_identity_line_unchanged_behaviour_for_known_model():
    import coder_identity
    line = coder_identity.identity_line(
        {"model": "gpt-oss-120b", "door": "http://door.example"})
    assert "GPT-OSS 120B" in line
    assert "gpt-oss-120b" in line
    assert "http://door.example" in line
    assert "MXFP4" in line


def test_identity_line_never_raises_on_garbage_input():
    import coder_identity
    assert coder_identity.identity_line(None) == "" or isinstance(
        coder_identity.identity_line(None), str)
    assert coder_identity.identity_line({"model": object()}) == "" or isinstance(
        coder_identity.identity_line({"model": object()}), str)
    # explicitly must not raise
    coder_identity.identity_line(42)
    coder_identity.identity_line({"model": "??", "door": None})
