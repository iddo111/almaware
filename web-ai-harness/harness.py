#!/usr/bin/env python3
"""One harness for web-only AI services (Perplexity, Grok, ...).

    python harness.py --provider perplexity --login
    python harness.py --provider perplexity --check-login
    python harness.py --provider perplexity --prompt "hello"

Sessions live in profiles/<provider>/. Log in by hand once; the profile is
reused afterwards. If a session expires the harness fails closed and tells you
to re-run with --login — it never tries to solve a CAPTCHA or 2FA.

Exit codes:
    0  a real reply was printed to stdout
    1  --check-login / --check-usable printed False
    2  no reply: login wall, prompt echoed back, or no composer -> --login
    4  policy denied
    5  the browser or tab died mid-run
"""
from __future__ import annotations

import argparse
import sys
import time

# Windows consoles default to cp1252, which cannot encode the arrows, dashes
# and quotes these models emit constantly. Without this, a successful run dies
# on print().
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

from playwright.sync_api import Error as PlaywrightError  # noqa: E402

import providers  # noqa: E402
from browser_backend import browser_page
from policy import Policy, PolicyError, audit, prompt_digest, redacted
from providers.base import ReplyGuardError

LOGIN_POLL_SECONDS = 2
LOGIN_TIMEOUT_SECONDS = 300


def cmd_login(provider, policy: Policy) -> int:
    policy.check("browser_launch")
    policy.check("browser_goto", host=provider.host)
    print(f"Opening {provider.start_url} — log in by hand. Waiting up to "
          f"{LOGIN_TIMEOUT_SECONDS // 60} minutes.")
    with browser_page(provider.name, headless=False) as page:
        page.goto(provider.start_url, wait_until="domcontentloaded")
        deadline = time.time() + LOGIN_TIMEOUT_SECONDS
        while time.time() < deadline:
            try:
                if provider.is_logged_in(page):
                    audit("login_ok", provider=provider.name)
                    print(f"login OK, profile saved for {provider.name}")
                    return 0
            except Exception:
                pass
            time.sleep(LOGIN_POLL_SECONDS)
    audit("login_timeout", provider=provider.name)
    print(f"timed out waiting for {provider.name} login", file=sys.stderr)
    return 1


def cmd_check_login(provider, policy: Policy, *, headless: bool,
                    usable_only: bool = False) -> int:
    """--check-login asks "am I authenticated"; --check-usable asks "can I
    prompt at all". Perplexity answers anonymously, so the second can be True
    while the first is False. Reporting the second as the first is what made
    this print True for a profile with no cookie jar."""
    policy.check("check_login", host=provider.host)
    # These two were missing: check-login launches a browser and navigates just
    # like every other mode, but skipped the gate that authorises doing so.
    policy.check("browser_launch")
    policy.check("browser_goto", host=provider.host)

    with browser_page(provider.name, headless=headless) as page:
        page.goto(provider.start_url, wait_until="domcontentloaded")
        page.wait_for_timeout(2500)
        ok = provider.is_usable(page) if usable_only else provider.is_logged_in(page)
    event = "check_usable" if usable_only else "check_login"
    audit(event, provider=provider.name, ok=ok)
    print(ok)
    return 0 if ok else 1


def cmd_prompt(provider, policy: Policy, prompt: str, *, headless: bool,
               timeout_s: int) -> int:
    policy.check("browser_launch")
    policy.check("browser_goto", host=provider.host)
    policy.check("browser_type", host=provider.host, text=prompt)
    policy.check("browser_read", host=provider.host)

    digest = prompt_digest(prompt)
    started = time.time()
    audit("prompt_start", provider=provider.name, prompt_sha=digest,
          prompt_chars=len(prompt))

    try:
        with browser_page(provider.name, headless=headless) as page:
            page.goto(provider.start_url, wait_until="domcontentloaded")
            page.wait_for_timeout(2500)

            # Usable, not authenticated: Perplexity answers without a session
            # and gating this on is_logged_in would break the one path that
            # works. A prompt that lands on a wall anyway is caught below, on
            # the reply, where the evidence actually is.
            if not provider.is_usable(page):
                audit("not_usable", provider=provider.name, prompt_sha=digest)
                print(f"no usable prompt box for {provider.name}, re-run with "
                      f"--login", file=sys.stderr)
                return 2

            provider.send_prompt(page, prompt)
            reply = provider.wait_for_reply(page, timeout_s=timeout_s)
    except ReplyGuardError as exc:
        elapsed = round(time.time() - started, 1)
        audit("reply_rejected", provider=provider.name, prompt_sha=digest,
              seconds=elapsed, reason=str(exc))
        print(f"{provider.name} did not answer: {exc}", file=sys.stderr)
        print(f"re-run with: python harness.py --provider {provider.name} "
              f"--login", file=sys.stderr)
        return 2
    except PlaywrightError as exc:
        elapsed = round(time.time() - started, 1)
        audit("browser_died", provider=provider.name, prompt_sha=digest,
              seconds=elapsed, reason=str(exc).splitlines()[0])
        print(f"{provider.name} browser died mid-run: "
              f"{str(exc).splitlines()[0]}", file=sys.stderr)
        return 5

    elapsed = round(time.time() - started, 1)
    audit("prompt_done", provider=provider.name, prompt_sha=digest,
          reply_chars=len(reply), seconds=elapsed,
          reply_preview=redacted(reply))
    print(reply)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--provider", required=True,
                    choices=sorted(providers.REGISTRY))
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--login", action="store_true",
                      help="open a browser for a one-time manual login")
    mode.add_argument("--check-login", action="store_true",
                      help="print True/False for whether this profile is "
                           "actually logged in")
    mode.add_argument("--check-usable", action="store_true",
                      help="print True/False for whether a prompt can be sent "
                           "at all (Perplexity answers anonymously)")
    mode.add_argument("--prompt", help="send a prompt and print the reply")
    ap.add_argument("--headless", action="store_true",
                    help="run without a visible window (more likely to be "
                         "blocked by bot detection)")
    ap.add_argument("--timeout", type=int, default=120,
                    help="seconds to wait for a reply (default 120)")
    args = ap.parse_args(argv)

    provider = providers.get(args.provider)
    policy = Policy.load()

    try:
        if args.login:
            return cmd_login(provider, policy)
        if args.check_login or args.check_usable:
            return cmd_check_login(provider, policy, headless=args.headless,
                                   usable_only=args.check_usable)
        return cmd_prompt(provider, policy, args.prompt,
                          headless=args.headless, timeout_s=args.timeout)
    except PolicyError as exc:
        audit("policy_denied", provider=args.provider, reason=str(exc))
        print(f"policy denied: {exc}", file=sys.stderr)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
