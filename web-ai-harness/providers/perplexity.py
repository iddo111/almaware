"""Perplexity web provider.

Locators use roles/placeholders rather than CSS classes — Perplexity ships DOM
changes often and class names are the first thing to break.
"""
from __future__ import annotations

from playwright.sync_api import Page

from browser_backend import settle_text
from providers.base import guard_reply, signin_control


class PerplexityProvider:
    name = "perplexity"
    start_url = "https://www.perplexity.ai/"
    host = "perplexity.ai"
    _last_prompt = ""

    def _composer(self, page: Page, *, wait_s: int = 20):
        """Find the prompt box, polling while the SPA finishes rendering."""
        # Perplexity has shipped both a textarea and a contenteditable div.
        for _ in range(max(1, wait_s * 4)):
            for locator in (
                page.get_by_placeholder("Ask anything"),
                page.locator("textarea").first,
                page.locator("div[contenteditable='true']").first,
            ):
                try:
                    if locator.count() and locator.is_visible():
                        return locator
                except Exception:
                    continue
            page.wait_for_timeout(250)
        raise RuntimeError("could not find the Perplexity prompt box")

    def is_usable(self, page: Page) -> bool:
        """Can we prompt at all? Perplexity answers anonymously, so a present
        composer is enough — this is the precondition for --prompt.

        Inspects; never navigates. Every caller in harness.py has already done
        the page.goto under the policy gate, so the goto that used to be here
        was both redundant and an un-audited navigation — and during a manual
        --login it could yank the user off the page they were logging in on.
        """
        try:
            self._composer(page)
            return True
        except RuntimeError:
            return False

    def is_logged_in(self, page: Page) -> bool:
        """Authenticated, which is a strictly stronger claim than usable.

        This used to return True whenever a composer rendered, which meant it
        printed True for a browser with no cookie jar at all. A visible
        "Sign in" control is the thing that proves there is no session.
        """
        if not self.is_usable(page):
            return False
        return signin_control(page) is None

    def send_prompt(self, page: Page, prompt: str) -> None:
        box = self._composer(page)
        box.click()
        box.fill("")
        box.type(prompt, delay=8)
        page.keyboard.press("Enter")
        self._last_prompt = prompt

    # Verified against the live site 2026-08-05: the answer body renders into
    # `.prose`, and submitting navigates to /search/<uuid>.
    ANSWER = ".prose"

    def wait_for_reply(self, page: Page, timeout_s: int = 120) -> str:
        try:
            page.wait_for_url("**/search/**", timeout=30_000)
        except Exception:
            pass  # some flows answer in place without navigating
        page.wait_for_selector(self.ANSWER, timeout=timeout_s * 1000)
        text = settle_text(page, self.ANSWER, quiet_ms=2500, timeout_s=timeout_s)
        # Roughly 1 run in 12 renders "Sign up and repeat your request." into
        # this very element. Returning that as the answer is the worst failure
        # mode there is, because the caller cannot tell it from a real reply.
        return guard_reply(text, self._last_prompt)
