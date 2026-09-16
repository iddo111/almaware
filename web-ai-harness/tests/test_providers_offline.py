"""Offline provider tests: real Playwright, real provider code, no network.

Saved fixtures of the pages that broke us are served from a loopback HTTP
server, so `wait_for_url("**/search/**")` and friends behave as they do live
without a packet leaving the machine.

These exist because the live suite could not see the bug it was written to
catch: it proved "we reached a model" by finding a fresh nonce in the reply,
and Grok's reply *was the prompt*, which contains the nonce. Every assertion
below fails against the code as it shipped.
"""
from __future__ import annotations

import sys
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(ROOT))

import providers  # noqa: E402
from providers.base import ReplyGuardError, guard_reply, signin_control  # noqa: E402

PROMPT = "What is 2+2? Answer with just the number."


# --------------------------------------------------------------------------
# Pure logic — no browser, always runs.
# --------------------------------------------------------------------------

def test_guard_rejects_prompt_echo():
    """The exact failure: Grok returned the prompt byte-for-byte, exit 0."""
    with pytest.raises(ReplyGuardError, match="prompt back"):
        guard_reply(PROMPT, PROMPT)


def test_guard_rejects_prompt_echo_ignoring_case_and_space():
    with pytest.raises(ReplyGuardError):
        guard_reply("  what is 2+2?   answer with just the number.\n", PROMPT)


def test_guard_rejects_signup_wall():
    with pytest.raises(ReplyGuardError, match="login wall"):
        guard_reply("Sign up and repeat your request.", PROMPT)


def test_guard_rejects_empty():
    with pytest.raises(ReplyGuardError, match="empty"):
        guard_reply("   \n ", PROMPT)


def test_guard_allows_a_real_answer():
    assert guard_reply("4", PROMPT) == "4"
    assert guard_reply("2 + 2 = 4.", PROMPT) == "2 + 2 = 4."


def test_guard_allows_a_nonce_echo():
    """The live test asks the model to repeat a token, so a reply that is a
    substring of the prompt is legitimate. Only full equality is an echo."""
    prompt = "Reply with only this exact token and nothing else: 4d205dcab742"
    assert guard_reply("4d205dcab742", prompt) == "4d205dcab742"


def test_tail_diff_is_gone():
    """It returned the whole page when it found no common prefix, which is how
    a run with no answer produced plausible-looking text and exit 0."""
    import providers.perplexity as pplx

    assert not hasattr(pplx, "_tail_diff")


def test_every_provider_separates_usable_from_logged_in():
    for name in providers.REGISTRY:
        p = providers.get(name)
        assert hasattr(p, "is_usable"), f"{name} has no is_usable"
        assert hasattr(p, "is_logged_in"), f"{name} has no is_logged_in"


# --------------------------------------------------------------------------
# Real pages, loopback only.
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def serve():
    handler = partial(SimpleHTTPRequestHandler, directory=str(FIXTURES))
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    httpd.RequestHandlerClass.log_message = lambda *a, **k: None
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


@pytest.fixture(scope="module")
def browser():
    """One browser for the module. The sync Playwright API cannot be started
    twice in a thread, so every browser test shares this."""
    pw = pytest.importorskip("playwright.sync_api").sync_playwright().start()
    br = None
    for channel in ("chrome", None):
        try:
            br = pw.chromium.launch(headless=True, channel=channel)
            break
        except Exception:
            continue
    if br is None:
        pw.stop()
        pytest.skip("no chromium available; run: playwright install chromium")
    yield br
    br.close()
    pw.stop()


@pytest.fixture(scope="module")
def page(browser):
    pg = browser.new_page()
    yield pg
    pg.close()


def _open(page, serve, fixture: str):
    # The Perplexity fixtures live under fixtures/search/ on purpose, so the
    # served URL matches wait_for_url("**/search/**") and the test does not sit
    # out that 30s timeout.
    page.goto(f"{serve}/{fixture}")
    return page


def test_grok_does_not_return_the_prompt(page, serve):
    """THE regression test. Old code returned PROMPT here and exit 0."""
    grok = providers.get("grok")
    grok._last_prompt = PROMPT
    _open(page, serve, "grok_logged_out_echo.html")

    with pytest.raises(ReplyGuardError):
        grok.wait_for_reply(page, timeout_s=8)


def test_grok_logged_out_page_is_not_logged_in(page, serve):
    grok = providers.get("grok")
    _open(page, serve, "grok_logged_out_echo.html")
    assert signin_control(page) == "Sign in"
    assert grok.is_usable(page) is True, "composer is there, so usable"
    assert grok.is_logged_in(page) is False, "...but it is NOT a session"


def test_perplexity_signup_wall_is_not_an_answer(page, serve):
    pplx = providers.get("perplexity")
    pplx._last_prompt = PROMPT
    _open(page, serve, "search/perplexity_signup_wall.html")

    with pytest.raises(ReplyGuardError, match="login wall"):
        pplx.wait_for_reply(page, timeout_s=8)


def test_perplexity_wall_page_is_not_logged_in(page, serve):
    pplx = providers.get("perplexity")
    _open(page, serve, "search/perplexity_signup_wall.html")
    assert pplx.is_usable(page) is True
    assert pplx.is_logged_in(page) is False


def test_perplexity_real_answer_still_works(page, serve):
    """Guards must not reject the working path — this is the 10-of-12 case."""
    pplx = providers.get("perplexity")
    pplx._last_prompt = PROMPT
    _open(page, serve, "search/perplexity_answer.html")

    assert pplx.wait_for_reply(page, timeout_s=8) == "2 + 2 = 4."
    assert pplx.is_logged_in(page) is True


def test_settle_text_survives_a_closed_page(browser, serve):
    """TargetClosedError used to escape settle_text as a traceback, from the
    page.wait_for_timeout at the bottom of the poll loop. 1 run in 12."""
    from browser_backend import settle_text

    pg = browser.new_page()
    pg.goto(f"{serve}/search/perplexity_answer.html")
    pg.locator(".prose").wait_for()
    pg.close()
    # Must return, not raise.
    assert settle_text(pg, ".prose", quiet_ms=500, timeout_s=5) == ""
