"""The provider contract. Adding a new web AI service means writing one of
these, not touching the harness.

Two separate questions, deliberately kept apart:

* `is_logged_in` — is this profile *authenticated*? A visible "Sign in" /
  "Sign up" control means it is not, no matter what else renders.
* `is_usable`    — can we prompt at all? Perplexity answers anonymously, so
  this is the precondition for `--prompt`, not authentication.

Collapsing the two is what made `--check-login` print True for a logged-out
browser and let `--prompt` walk into a signup wall.
"""
from __future__ import annotations

import re
from typing import Protocol, runtime_checkable

from playwright.sync_api import Page


class ReplyGuardError(RuntimeError):
    """The page handed back something that is not a model reply.

    Raised instead of returning it, because a harness that returns the signup
    wall — or the user's own prompt — with exit 0 is worse than one that fails.
    """


# Text these sites render *in place of an answer* when they want a login. A
# reply containing one of these is a wall, not an answer.
INTERSTITIALS = (
    "sign up and repeat your request",
    "continue your conversation",
    "sign up to continue",
    "sign in to continue",
    "log in to continue",
    "create an account to continue",
    "sign up below to unlock",
    "to continue seamlessly with grok",
)

# Anchored, so "Sign in with Google" inside an already-authenticated settings
# page does not count and a bare "Sign in" button does.
_AUTH_CONTROL = re.compile(r"^\s*(sign[ -]?in|sign[ -]?up|log[ -]?in|register)\s*$", re.I)


def signin_control(page: Page) -> str | None:
    """Label of a visible sign-in/sign-up control, or None if there is none.

    This is the observable proxy for "no session". Cookie names churn faster
    than the login button does.
    """
    for role in ("button", "link"):
        try:
            loc = page.get_by_role(role, name=_AUTH_CONTROL)
            count = loc.count()
        except Exception:
            continue
        for i in range(min(count, 10)):
            try:
                item = loc.nth(i)
                if item.is_visible():
                    return " ".join(item.inner_text().split()) or role
            except Exception:
                continue
    return None


def _norm(text: str) -> str:
    return " ".join(text.split()).strip().casefold()


def guard_reply(reply: str, prompt: str) -> str:
    """Return `reply`, or raise if it is not plausibly a model reply.

    Three ways a scraper lies about success, all seen live:
      * it scraped the user's own prompt bubble and returned it verbatim;
      * it scraped a signup interstitial;
      * it scraped nothing and returned "".
    """
    text = reply.strip()
    if not text:
        raise ReplyGuardError("empty reply — no answer element ever rendered")
    if prompt and _norm(text) == _norm(prompt):
        raise ReplyGuardError(
            "the page returned the prompt back verbatim — that is the user's "
            "own message bubble, not a model reply"
        )
    low = _norm(text)
    for wall in INTERSTITIALS:
        if wall in low:
            raise ReplyGuardError(f"login wall instead of an answer: {text[:120]!r}")
    return text


@runtime_checkable
class Provider(Protocol):
    name: str
    start_url: str
    host: str

    def is_logged_in(self, page: Page) -> bool:
        """True only if this profile is actually authenticated."""

    def is_usable(self, page: Page) -> bool:
        """True if we can submit a prompt, authenticated or not."""

    def send_prompt(self, page: Page, prompt: str) -> None:
        """Type the prompt and submit it. Must not wait for the reply."""

    def wait_for_reply(self, page: Page, timeout_s: int = 120) -> str:
        """Block until the reply finishes streaming, then return just the
        reply text (not the whole page). Raises ReplyGuardError rather than
        returning the prompt, a login wall, or "".
        """
