"""Throwaway diagnostic: submit a prompt and dump what the DOM looks like
afterwards, so provider selectors can be written against reality.

    py -3.13 tools/probe_dom.py perplexity "what is 2+2"
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import providers
from browser_backend import browser_page

name = sys.argv[1] if len(sys.argv) > 1 else "perplexity"
prompt = sys.argv[2] if len(sys.argv) > 2 else "what is 2+2"

provider = providers.get(name)

with browser_page(provider.name, headless=False) as page:
    page.goto(provider.start_url, wait_until="domcontentloaded")
    provider._composer(page)
    print(f"url before: {page.url}")
    provider.send_prompt(page, prompt)
    page.wait_for_timeout(12000)
    print(f"url after:  {page.url}")

    for sel in [
        "main",
        "[data-testid='answer']",
        ".prose",
        "div.prose",
        "[class*='answer']",
        "[class*='markdown']",
        "article",
        "[dir='auto']",
    ]:
        try:
            loc = page.locator(sel)
            n = loc.count()
            if not n:
                continue
            sample = " ".join(loc.last.inner_text().split())[:220]
            print(f"\n--- {sel!r}  count={n}")
            print(f"    {sample}")
        except Exception as exc:
            print(f"\n--- {sel!r} ERROR {exc}")

    print("\n===== full body tail =====")
    print(" ".join(page.inner_text("body").split())[-1200:])
