"""Offline tests. No network, no browser — these run every time."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from policy import Policy, PolicyError, prompt_digest, redacted  # noqa: E402


@pytest.fixture
def policy() -> Policy:
    return Policy.load()


def test_allowlisted_verb_passes(policy):
    policy.check("browser_goto", host="perplexity.ai")


def test_unknown_verb_denied(policy):
    with pytest.raises(PolicyError, match="verb not allowlisted"):
        policy.check("rm_rf")


def test_unknown_host_denied(policy):
    with pytest.raises(PolicyError, match="host not allowlisted"):
        policy.check("browser_goto", host="evil.example.com")


def test_subdomain_allowed(policy):
    policy.check("browser_goto", host="www.perplexity.ai")


def test_lookalike_host_denied(policy):
    """perplexity.ai.evil.com must not pass just because it contains the host."""
    with pytest.raises(PolicyError):
        policy.check("browser_goto", host="perplexity.ai.evil.com")


def test_overlong_prompt_denied(policy):
    with pytest.raises(PolicyError, match="text too long"):
        policy.check("browser_type", host="grok.com", text="x" * 9000)


def test_prompt_digest_is_stable_and_not_reversible():
    a = prompt_digest("secret question")
    assert a == prompt_digest("secret question")
    assert a != prompt_digest("other question")
    assert "secret" not in a


def test_redaction_truncates():
    assert redacted("a" * 500, limit=10) == "a" * 10 + "…"


def test_every_provider_host_is_allowlisted(policy):
    """A provider we cannot legally visit is a packaging bug."""
    import providers

    for name in providers.REGISTRY:
        provider = providers.get(name)
        policy.check("browser_goto", host=provider.host)


def _verbs_used_in_harness() -> set[str]:
    import re

    src = (Path(__file__).resolve().parents[1] / "harness.py").read_text(
        encoding="utf-8")
    return set(re.findall(r'policy\.check\(\s*"([a-z_]+)"', src))


def test_config_verbs_cover_what_harness_uses(policy):
    """Guards against adding a policy.check() the config forgot to allow."""
    assert _verbs_used_in_harness() <= policy.allowed_verbs


def test_config_allowlists_nothing_unused(policy):
    """The other direction. `browser_screenshot` sat in the allowlist granting
    a capability no code path ever exercised — a standing permission for
    nothing. An allowlist you do not read is not a control."""
    assert policy.allowed_verbs <= _verbs_used_in_harness()


def test_check_login_is_gated_on_launch_and_goto():
    """cmd_check_login launched a browser and navigated while checking only
    the `check_login` verb, so the docstring claim that every action passes
    through Policy.check was false for that whole command."""
    import inspect

    import harness

    src = inspect.getsource(harness.cmd_check_login)
    for verb in ("check_login", "browser_launch", "browser_goto"):
        assert f'policy.check("{verb}"' in src, f"{verb} not gated"


def test_providers_never_navigate_on_their_own():
    """Navigation is policy-gated in harness.py. A provider calling page.goto
    itself routes around that gate."""
    from pathlib import Path as _P

    root = _P(__file__).resolve().parents[1] / "providers"
    offenders = [f.name for f in root.glob("*.py") if "page.goto(" in
                 f.read_text(encoding="utf-8")]
    assert offenders == [], f"providers calling page.goto: {offenders}"
