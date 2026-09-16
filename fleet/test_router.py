#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
לזכרה של עלמה ז"ל

Tests for the ALMAWARE Fleet Router.

These tests are hermetic: no real network calls are ever made. The single
network primitive in router.py is `_http_post`, so every test monkeypatches
that one function (and any required env keys) to exercise:

  * classify() -> pick_model() routing decisions
  * all four provider branches in dispatch() (anthropic / gemini / xai / ollama)
  * the fallback_chain walk: when the primary model raises, route() must fall
    through to the next working model in the chain.

Run:  python -m pytest test_router.py -v
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import router


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture
def cfg():
    """The real fleet config — routing/model wiring is part of what we test."""
    return router.load_config()


@pytest.fixture(autouse=True)
def _clear_keys(monkeypatch):
    """Default to a clean env so a stray real key can never leak into a test."""
    for var in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "XAI_API_KEY",
                "OLLAMA_URL"):
        monkeypatch.delenv(var, raising=False)


# --------------------------------------------------------------------------- #
# classify() — task-type detection
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("prompt, expected", [
    ("Write a Python function to reverse a list", "code"),
    ("what's the latest news on AI chips today?", "realtime"),
    ("reply to this whatsapp message quickly", "whatsapp"),
    ("summarize this long transcript for me", "document"),
    ("תרגם לעברית: hello world", "hebrew"),
    ("שלום עולם", "hebrew"),            # pure Hebrew, no keyword -> hebrew fallback
    ("Hello, how are you?", "default"),  # no signal -> default
    ("ask eran what he thinks", "almaware"),     # ALMAWARE-specific -> Eran
    ("tell me about ALMAWARE", "almaware"),
    ("write a poem about the sea", "creative"),  # creative -> Eran
])
def test_classify(prompt, expected):
    assert router.classify(prompt) == expected


def test_classify_long_context():
    # >4000 chars with no other signal -> long_context
    assert router.classify("a " * 3000) == "long_context"


# --------------------------------------------------------------------------- #
# pick_model() — routing table lookup
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("task, model", [
    ("code", "sonnet"),
    ("realtime", "grok-web"),
    ("web_search", "grok-web"),
    ("reasoning", "grok"),
    ("whatsapp", "gemma2:2b"),
    ("document", "gemini-pro"),
    ("hebrew", "eran-local"),
    ("hebrew_nlp", "eran-local"),
    ("creative", "eran-local"),
    ("almaware", "eran-local"),
    ("eran", "eran-local"),
    ("default", "haiku"),
])
def test_pick_model(cfg, task, model):
    assert router.pick_model(cfg, task) == model


def test_pick_model_unknown_task_falls_to_default(cfg):
    assert router.pick_model(cfg, "no_such_task") == cfg["task_routing"]["default"]


# --------------------------------------------------------------------------- #
# Provider branches — each dispatch() path, with _http_post mocked
# --------------------------------------------------------------------------- #
def test_dispatch_anthropic(cfg, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    captured = {}

    def fake_post(url, payload, headers, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["payload"] = payload
        return {"content": [{"type": "text", "text": "anthropic-reply"}]}

    monkeypatch.setattr(router, "_http_post", fake_post)

    out = router.dispatch(cfg, "haiku", "hi")
    assert out == "anthropic-reply"
    assert captured["url"] == "https://api.anthropic.com/v1/messages"
    assert captured["headers"]["x-api-key"] == "test-key"
    assert captured["payload"]["model"] == "claude-haiku-4-5"


def test_dispatch_gemini(cfg, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    captured = {}

    def fake_post(url, payload, headers, timeout):
        captured["url"] = url
        return {"candidates": [{"content": {"parts": [{"text": "gemini-reply"}]}}]}

    monkeypatch.setattr(router, "_http_post", fake_post)

    out = router.dispatch(cfg, "gemini-pro", "hi")
    assert out == "gemini-reply"
    assert "gemini-2.5-pro:generateContent" in captured["url"]
    assert "key=test-key" in captured["url"]


def test_dispatch_xai(cfg, monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "test-key")
    captured = {}

    def fake_post(url, payload, headers, timeout):
        captured["url"] = url
        captured["headers"] = headers
        return {"choices": [{"message": {"content": "grok-reply"}}]}

    monkeypatch.setattr(router, "_http_post", fake_post)

    out = router.dispatch(cfg, "grok", "hi")
    assert out == "grok-reply"
    assert captured["url"] == "https://api.x.ai/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer test-key"


def test_dispatch_ollama(cfg, monkeypatch):
    # ollama needs no key; endpoint comes from env or default
    captured = {}

    def fake_post(url, payload, headers, timeout):
        captured["url"] = url
        captured["payload"] = payload
        return {"response": "ollama-reply"}

    monkeypatch.setattr(router, "_http_post", fake_post)

    out = router.dispatch(cfg, "gemma2:2b", "hi")
    assert out == "ollama-reply"
    assert captured["url"] == "http://localhost:11434/api/generate"
    assert captured["payload"]["model"] == "gemma2:2b"


def test_dispatch_ollama_honors_endpoint_env(cfg, monkeypatch):
    monkeypatch.setenv("OLLAMA_URL", "http://example.local:9999")
    seen = {}

    def fake_post(url, payload, headers, timeout):
        seen["url"] = url
        return {"response": "ok"}

    monkeypatch.setattr(router, "_http_post", fake_post)
    router.dispatch(cfg, "gemma2:2b", "hi")
    assert seen["url"] == "http://example.local:9999/api/generate"


def test_dispatch_missing_key_raises(cfg, monkeypatch):
    # No ANTHROPIC_API_KEY in env (cleared by autouse fixture) -> RuntimeError
    monkeypatch.setattr(router, "_http_post",
                        lambda *a, **k: pytest.fail("should not be called"))
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY not set"):
        router.dispatch(cfg, "haiku", "hi")


def test_dispatch_grok_web_sends_search_params(cfg, monkeypatch):
    """grok-web must carry extra_body (Live Search) into the xAI request."""
    monkeypatch.setenv("XAI_API_KEY", "test-key")
    captured = {}

    def fake_post(url, payload, headers, timeout):
        captured["payload"] = payload
        return {"choices": [{"message": {"content": "web-reply"}}]}

    monkeypatch.setattr(router, "_http_post", fake_post)
    out = router.dispatch(cfg, "grok-web", "what's new today?")
    assert out == "web-reply"
    assert captured["payload"]["search_parameters"]["mode"] == "auto"


def test_dispatch_grok_plain_has_no_search_params(cfg, monkeypatch):
    """Plain grok must NOT carry search_parameters (no live web)."""
    monkeypatch.setenv("XAI_API_KEY", "test-key")
    captured = {}

    def fake_post(url, payload, headers, timeout):
        captured["payload"] = payload
        return {"choices": [{"message": {"content": "ok"}}]}

    monkeypatch.setattr(router, "_http_post", fake_post)
    router.dispatch(cfg, "grok", "reason about this")
    assert "search_parameters" not in captured["payload"]


def test_dispatch_eran_local(cfg, monkeypatch):
    """eran provider POSTs the server's native schema to {endpoint}/chat."""
    captured = {}

    def fake_post(url, payload, headers, timeout):
        captured["url"] = url
        captured["payload"] = payload
        captured["headers"] = headers
        return {"reply": "  שלום מער\"ן  ", "step": 42, "tokens": 7}

    monkeypatch.setattr(router, "_http_post", fake_post)
    out = router.dispatch(cfg, "eran-local", "שלום")
    assert out.strip() == 'שלום מער"ן'
    assert captured["url"] == "http://localhost:7800/chat"
    assert captured["payload"]["prompt"] == "שלום"
    # loopback default: no token in env -> no Authorization header
    assert "Authorization" not in captured["headers"]


def test_dispatch_eran_honors_endpoint_and_token(cfg, monkeypatch):
    monkeypatch.setenv("ERAN_DGX4_URL", "http://localhost:7801")
    monkeypatch.setenv("ERAN_TOKEN", "secret-tok")
    captured = {}

    def fake_post(url, payload, headers, timeout):
        captured["url"] = url
        captured["headers"] = headers
        return {"reply": "ok"}

    monkeypatch.setattr(router, "_http_post", fake_post)
    router.dispatch(cfg, "eran-dgx4", "hi")
    assert captured["url"] == "http://localhost:7801/chat"
    assert captured["headers"]["Authorization"] == "Bearer secret-tok"


def test_dispatch_eran_empty_reply_raises(cfg, monkeypatch):
    """An empty generation must raise so route() can fall back to a real model."""
    monkeypatch.setattr(router, "_http_post",
                        lambda *a, **k: {"reply": "   "})
    with pytest.raises(RuntimeError, match="empty reply"):
        router.dispatch(cfg, "eran-local", "hi")


# --------------------------------------------------------------------------- #
# route() — end-to-end with mocked transport, incl. fallback_chain walk
# --------------------------------------------------------------------------- #
def test_route_dry_run_makes_no_call(monkeypatch):
    monkeypatch.setattr(router, "_http_post",
                        lambda *a, **k: pytest.fail("dry run must not call"))
    res = router.route("Write a Python function", dry_run=True)
    assert res["task"] == "code"
    assert res["model"] == "sonnet"
    assert res["provider"] == "anthropic"
    assert res["output"] == "(dry run — no call made)"


def test_route_happy_path_local(monkeypatch):
    # whatsapp -> gemma2:2b (ollama, free) — the primary should answer directly.
    monkeypatch.setattr(
        router, "_http_post",
        lambda url, payload, headers, timeout: {"response": "ok"},
    )
    res = router.route("reply to this whatsapp message", task="whatsapp")
    assert res["model"] == "gemma2:2b"
    assert res["provider"] == "ollama"
    assert res["free"] is True
    assert res["output"] == "ok"
    assert "fell_back_from" not in res


def test_route_falls_through_to_next_in_chain(monkeypatch):
    """Primary raises -> route() walks fallback_chain to the next working model.

    Primary for 'code' is sonnet (anthropic). We make anthropic fail and let
    the first fallback (gemma2:2b / ollama) succeed, and assert the result
    reflects the fallback model + records fell_back_from.
    """
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    def fake_post(url, payload, headers, timeout):
        if "anthropic.com" in url:
            raise RuntimeError("simulated anthropic 500")
        if "11434" in url:  # ollama
            return {"response": "fallback-ok"}
        raise AssertionError(f"unexpected url {url}")

    monkeypatch.setattr(router, "_http_post", fake_post)

    res = router.route("Write a Python function", task="code")
    assert res["model"] == "gemma2:2b"          # first entry of fallback_chain
    assert res["provider"] == "ollama"
    assert res["output"] == "fallback-ok"
    assert res["fell_back_from"] == "sonnet"
    assert "error" not in res


def test_route_eran_escalates_to_sonnet_via_fallback_to(monkeypatch):
    """hebrew -> eran-local; Eran down -> per-model fallback_to escalates to the
    DGX Eran (also down) -> sonnet (a REAL model), NOT generic gemma2:2b."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    def fake_post(url, payload, headers, timeout):
        if url.endswith("/chat"):                 # both eran endpoints (local+dgx)
            raise RuntimeError("eran offline")
        if "anthropic.com" in url:                # sonnet
            return {"content": [{"type": "text", "text": "סונט עונה"}]}
        raise AssertionError(f"unexpected url {url} (should never reach gemma2)")

    monkeypatch.setattr(router, "_http_post", fake_post)
    res = router.route("ספר לי סיפור", task="hebrew")
    assert res["model"] == "sonnet"
    assert res["provider"] == "anthropic"
    assert res["fell_back_from"] == "eran-local"
    assert res["output"] == "סונט עונה"


def test_route_eran_happy_path(monkeypatch):
    """When Eran answers, the request stays on Eran (free, our own model)."""
    monkeypatch.setattr(
        router, "_http_post",
        lambda url, payload, headers, timeout: {"reply": "אני ער\"ן"},
    )
    res = router.route("מי אתה?", task="eran")
    assert res["model"] == "eran-local"
    assert res["provider"] == "eran"
    assert res["free"] is True
    assert res["output"].strip() == 'אני ער"ן'
    assert "fell_back_from" not in res


def test_route_walks_multiple_failures(monkeypatch):
    """gemma2 (chain[0]) AND haiku (chain[1]) fail -> lands on gemini-flash."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    def fake_post(url, payload, headers, timeout):
        if "11434" in url:                       # gemma2:2b (primary for whatsapp)
            raise RuntimeError("ollama down")
        if "anthropic.com" in url:               # haiku (chain[1])
            raise RuntimeError("anthropic down")
        if "generativelanguage" in url:          # gemini-flash (chain[2])
            return {"candidates": [{"content": {"parts": [{"text": "g-ok"}]}}]}
        raise AssertionError(f"unexpected url {url}")

    monkeypatch.setattr(router, "_http_post", fake_post)

    res = router.route("quick whatsapp reply", task="whatsapp")
    assert res["model"] == "gemini-flash"
    assert res["provider"] == "gemini"
    assert res["output"] == "g-ok"
    assert res["fell_back_from"] == "gemma2:2b"


def test_route_all_fail_returns_error(monkeypatch):
    """Every model in primary+chain raises -> result carries an error string."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    def fake_post(url, payload, headers, timeout):
        raise RuntimeError("everything is down")

    monkeypatch.setattr(router, "_http_post", fake_post)

    res = router.route("quick whatsapp reply", task="whatsapp")
    assert "output" not in res
    assert "error" in res
    assert "all models failed" in res["error"]


def test_main_list_exits_zero(capsys):
    rc = router.main(["--list"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "ALMAWARE Fleet" in out
    assert "gemma2:2b" in out
