"""alma-mic / brain.py — the mic's brain, embedded (not a new app).

Iddo's rule (2026-07-07, וועדת חקירה): reuse the working app; embed the brain here.
Primary = Grok (grok.exe headless, already proven in this mic). Hebrew fallback =
DictaLM served on a DGX ("do dicta for hebrew if grok doesn't cut it"). Both are the
existing grok.py / dicta.py blocks — this file only ROUTES between them.

    ans, who = ask("...", backend="grok", dicta_url=cfg.dicta_url)

Contract, same as the blocks it wraps: returns (answer_text, who); who is the model
that actually answered ("grok" | "dicta") or "—" on failure. Never raises.
"""
from __future__ import annotations

import dicta
import grok


def available() -> bool:
    return grok.available()


def ask(prompt: str, *, backend: str = "grok", dicta_url: str = "",
        timeout: float = 90.0) -> tuple[str, str]:
    """Route a single-turn question.
      backend="grok"  -> Grok; if it fails AND dicta_url is set, auto-fall-back to Dicta.
      backend="dicta" -> force the Hebrew DictaLM brain on the DGX.
    Returns (answer, who). Never raises."""
    prompt = (prompt or "").strip()
    if not prompt:
        return ("", "—")

    if backend == "dicta":
        return dicta.ask(prompt, dicta_url, timeout=timeout)

    ans, who = grok.ask(prompt, timeout=timeout)
    if who == "—" and dicta.available(dicta_url):   # Grok didn't cut it → try Dicta
        d_ans, d_who = dicta.ask(prompt, dicta_url, timeout=timeout)
        if d_who != "—":
            return (d_ans, d_who)
    return (ans, who)


def cleanup(text: str, *, timeout: float = 120.0) -> tuple[str, str]:
    """Hebrew transcript cleanup — delegated to Grok (its proven cleanup prompt)."""
    return grok.cleanup(text, timeout=timeout)
