"""Grok web provider.

Grok is reachable at both grok.com and x.com/i/grok depending on the account.
`GROK_URL` overrides the default if this account needs the X-hosted one.
"""
from __future__ import annotations

import os

from playwright.sync_api import Page

from browser_backend import settle_text
from providers.base import ReplyGuardError, guard_reply, signin_control


class GrokProvider:
    name = "grok"
    start_url = os.getenv("GROK_URL", "https://grok.com/")
    _last_prompt = ""

    @property
    def host(self) -> str:
        return "x.com" if "x.com" in self.start_url else "grok.com"

    def _composer(self, page: Page, *, wait_s: int = 20):
        """Find the prompt box, polling while the SPA finishes rendering."""
        for _ in range(max(1, wait_s * 4)):
            for locator in (
                page.get_by_placeholder("What do you want to know?"),
                page.get_by_role("textbox").first,
                page.locator("textarea").first,
                page.locator("div[contenteditable='true']").first,
            ):
                try:
                    if locator.count() and locator.is_visible():
                        return locator
                except Exception:
                    continue
            page.wait_for_timeout(250)
        raise RuntimeError("could not find the Grok prompt box")

    def is_usable(self, page: Page) -> bool:
        """A reachable composer. Grok renders one on the logged-out wall too,
        so this says nothing about having a session — see is_logged_in.

        Inspects; never navigates (see the note in perplexity.py).
        """
        try:
            self._composer(page)
            return True
        except RuntimeError:
            return False

    def is_logged_in(self, page: Page) -> bool:
        """Grok really does need a session, and the logged-out page still shows
        a composer — so composer-presence reported True for a profile that had
        never been logged into. The Sign in / Sign up control is the tell."""
        if not self.is_usable(page):
            return False
        return signin_control(page) is None

    def send_prompt(self, page: Page, prompt: str) -> None:
        box = self._composer(page)
        box.click()
        try:
            box.fill("")
        except Exception:
            pass
        box.type(prompt, delay=8)
        page.keyboard.press("Enter")
        self._last_prompt = prompt

    # Ordered most- to least-specific. `div.prose` and `.markdown` are LAST and
    # dangerous: on grok.com the user's own prompt bubble is a `div.prose`, so
    # a bare "first selector that returns text wins" loop returned the prompt
    # and the harness called that success. They stay only because the echo
    # check below makes them safe — a candidate identical to the prompt is
    # discarded and the next selector is tried.
    ANSWER_SELECTORS = [
        "[data-testid='markdown']",
        ".response-content-markdown",
        "div.prose",
        ".markdown",
    ]

    def wait_for_reply(self, page: Page, timeout_s: int = 120) -> str:
        page.wait_for_timeout(2000)

        errors: list[str] = []
        for selector in self.ANSWER_SELECTORS:
            try:
                if not page.locator(selector).count():
                    continue
                text = settle_text(page, selector, quiet_ms=2500,
                                   timeout_s=timeout_s)
            except Exception as exc:
                errors.append(f"{selector}: {exc}")
                continue
            try:
                return guard_reply(text, self._last_prompt)
            except ReplyGuardError as exc:
                # Not an answer (prompt echo, login wall, empty) — keep looking.
                errors.append(f"{selector}: {exc}")

        # There used to be a whole-page-diff fallback here. It could not fail:
        # when the diff found nothing it returned the entire page, so a run that
        # produced no answer at all still exited 0 with plausible-looking text.
        # A missing answer element must raise.
        raise ReplyGuardError(
            "no Grok answer element produced a reply; tried "
            + "; ".join(errors or ["<no selector matched>"])
        )
