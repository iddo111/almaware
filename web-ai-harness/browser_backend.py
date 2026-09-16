"""Playwright wrapper: one persistent browser profile per provider.

Persistent contexts are what make this work at all — the login cookies for
Perplexity/Grok live in profiles/<provider>/ so you log in by hand once and
subsequent runs reuse the session.
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parent
PROFILES = ROOT / "profiles"

# Bundled Chromium trips bot detection more often than the real installed
# Chrome. Try Chrome first and fall back rather than failing outright.
_CHANNELS = ["chrome", None]


@contextmanager
def browser_page(provider: str, *, headless: bool = False, slow_mo: int = 0):
    """Yield a Page backed by the persistent profile for `provider`."""
    profile_dir = PROFILES / provider
    profile_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        context = None
        last_error: Exception | None = None
        for channel in _CHANNELS:
            try:
                context = pw.chromium.launch_persistent_context(
                    user_data_dir=str(profile_dir),
                    headless=headless,
                    slow_mo=slow_mo,
                    channel=channel,
                    viewport={"width": 1440, "height": 900},
                    args=["--disable-blink-features=AutomationControlled"],
                )
                break
            except Exception as exc:  # channel unavailable — try the next
                last_error = exc
        if context is None:
            raise RuntimeError(
                f"could not launch a browser for {provider!r}: {last_error}"
            )

        try:
            page = context.pages[0] if context.pages else context.new_page()
            yield page
        finally:
            try:
                context.close()
            except Exception:
                pass  # already gone; closing a dead context must not mask the
                      # real error on the way out


def _tick(page: Page, ms: int = 250) -> bool:
    """Sleep `ms` inside the page. False means the page/context is gone.

    The text read in the settle loops was already guarded; this was not, so a
    context that died mid-poll raised TargetClosedError straight out of the
    harness with a traceback and no `prompt_done` audit record.
    """
    try:
        page.wait_for_timeout(ms)
        return True
    except Exception:
        return False


def settle_text(page: Page, selector: str, *, quiet_ms: int = 2000,
                timeout_s: int = 120) -> str:
    """Wait until `selector`'s text stops changing, then return it.

    Scoping to the answer container instead of the whole body is what makes
    this reliable — page chrome, cookie banners and sign-up modals mutate
    independently of the reply and defeat a whole-page diff.
    """
    import time

    deadline = time.time() + timeout_s
    last_text = ""
    last_change = time.time()

    while time.time() < deadline:
        try:
            nodes = page.locator(selector)
            text = nodes.last.inner_text() if nodes.count() else ""
        except Exception:
            text = last_text
        if text != last_text:
            last_text = text
            last_change = time.time()
        elif last_text and (time.time() - last_change) * 1000 >= quiet_ms:
            return last_text.strip()
        if not _tick(page):
            # The tab died mid-read (Perplexity closes the context on its
            # signup interstitial). Return what we already have and let the
            # caller's reply guard judge it, instead of raising
            # TargetClosedError out of the middle of a successful-looking run.
            return last_text.strip()

    return last_text.strip()

# `settle()` — whole-page text settle — lived here and is deliberately gone. Its
# only caller was Grok's fallback, which diffed the whole page against a
# "before" snapshot and returned the entire page whenever the diff found no
# common prefix. That is how a run that produced no answer at all still exited 0
# with plausible-looking text. Scope to the answer element (settle_text) or
# raise; do not guess from the page body.
