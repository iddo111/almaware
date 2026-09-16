"""Live tests. These hit the real services over the network.

    py -3.13 -m pytest tests/test_providers_live.py -m live -v

A fresh UUID is generated per run and must appear in the reply. On its own that
proved nothing: Grok's reply *was the prompt echoed back*, which contains the
nonce, so this suite passed while Grok had never emitted a token. Every
assertion here now also requires the reply not to be the prompt.

Requires a one-time `harness.py --provider <name> --login` first.
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import harness  # noqa: E402

pytestmark = pytest.mark.live

PROVIDERS = ["perplexity", "grok"]


def _norm(text: str) -> str:
    return " ".join(text.split()).strip().casefold()


def _run(provider: str, prompt: str, capsys) -> str:
    code = harness.main(["--provider", provider, "--prompt", prompt,
                         "--timeout", "180"])
    captured = capsys.readouterr()
    out = captured.out
    if code == 2:
        pytest.skip(f"{provider} has no session / hit a login wall — run: "
                    f"python harness.py --provider {provider} --login\n"
                    f"{captured.err.strip()}")
    assert code == 0, f"{provider} exited {code}: {captured.err.strip()}"
    # The assertion this suite was missing. A scraper that grabs the user's own
    # prompt bubble satisfies every nonce check ever written.
    assert _norm(out) != _norm(prompt), (
        f"{provider} returned the prompt back verbatim — that is the prompt "
        f"bubble, not a reply"
    )
    return out


@pytest.mark.parametrize("provider", PROVIDERS)
def test_provider_echoes_fresh_nonce(provider, capsys):
    nonce = uuid.uuid4().hex[:12]
    reply = _run(
        provider,
        f"Reply with only this exact token and nothing else: {nonce}",
        capsys,
    )
    assert nonce in reply, (
        f"{provider} did not echo the nonce; got: {reply[:300]!r}"
    )


@pytest.mark.parametrize("provider", PROVIDERS)
def test_provider_is_not_cached(provider, capsys):
    """Two different nonces back to back must produce two different replies."""
    first, second = uuid.uuid4().hex[:12], uuid.uuid4().hex[:12]
    r1 = _run(provider, f"Reply with only this token: {first}", capsys)
    r2 = _run(provider, f"Reply with only this token: {second}", capsys)
    assert first in r1 and second in r2
    assert first not in r2, f"{provider} appears to be serving a cached reply"
