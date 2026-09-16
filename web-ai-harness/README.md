# web-ai-harness

One harness for driving web-only AI services (Perplexity, Grok, …) from the
command line. Replaces the scattered half-finished computer-use harnesses that
accumulated across Claude, Codex and Grok.

## Why it looks like this

Perplexity and Grok are **DOM pages in a browser**, not desktop apps. The
earlier harnesses drove them by clicking pixels and running a vision model in
the loop, which is slow, non-deterministic and near-impossible to test.
Playwright was already installed on this machine and unused. So: DOM
automation with stable role/placeholder locators, and a real logged-in browser
profile per provider.

## Install

Nothing to install — Playwright 1.60 and its Chromium are already present.

```powershell
py -3.13 -m playwright --version    # expect 1.60.0
```

## Use

```powershell
cd D:\CLAUDE\web-ai-harness

# one-time, per provider: log in by hand in the window that opens
py -3.13 harness.py --provider grok --login

# is the session still alive?
py -3.13 harness.py --provider perplexity --check-login

# ask something
py -3.13 harness.py --provider perplexity --prompt "what is 2+2"
```

Perplexity answers anonymously, so it works without `--login`. Grok generally
needs a session.

If Grok lives at `x.com/i/grok` for your account rather than `grok.com`:

```powershell
$env:GROK_URL = "https://x.com/i/grok"
```

## Adding a provider

Write one file in `providers/` with three methods and register it. The harness
never learns the service's name.

```python
class MyProvider:
    name = "myservice"
    start_url = "https://example.com/"
    host = "example.com"

    def is_logged_in(self, page) -> bool: ...
    def send_prompt(self, page, prompt: str) -> None: ...
    def wait_for_reply(self, page, timeout_s: int = 120) -> str: ...
```

Then add it to `REGISTRY` in `providers/__init__.py` and add its host to
`config.json`. `tests/test_policy.py` fails if you forget the host — that is
deliberate.

`tools/probe_dom.py` dumps candidate selectors from the live site, which is how
the Perplexity `.prose` answer selector was found. Use it when a provider
breaks.

## Safety model

- **Policy gate.** Every action passes `policy.check` first. Unknown verbs and
  non-allowlisted hosts are refused. Host matching is exact-or-subdomain, so
  `perplexity.ai.evil.com` does not pass.
- **Fail closed.** If a session is dead the harness prints
  `session expired for <provider>, re-run with --login` and exits 2. It never
  attempts to solve a CAPTCHA or 2FA.
- **Audit log.** `logs/audit.jsonl` records every run. It stores a SHA-256
  prefix of the prompt, never the prompt itself, so the log is safe to share.
- **No inbound surface.** This is a CLI. It opens no port and accepts no
  requests — unlike the server it replaces, which auto-started on login with
  `allow_origins=["*"]` in front of real mouse and keyboard control.

## Tests

```powershell
py -3.13 -m pytest -q                                   # offline, always run
py -3.13 -m pytest tests/test_providers_live.py -m live  # hits the real sites
```

Live tests generate a fresh UUID per run and assert it comes back in the reply.
That is the only thing that proves a real model answered rather than a cache or
a stub — a fixture or recorded response does not count.

Verified against live Perplexity on 2026-08-05: nonce `9dc12c1472bc` echoed
exactly.

## Known limits

- **Selector drift.** Perplexity and Grok change their DOM; providers will need
  occasional repair. Role/placeholder locators reduce but do not eliminate this.
- **Bot detection.** Headed mode with the real Chrome channel is the default
  because it is least likely to be blocked. `--headless` is more likely to trip
  Cloudflare.
- **Session lifetime unknown.** No data yet on how long these sessions last.
  The fail-closed check is a safety net, not a fix.
- **Grok is untested end-to-end.** Perplexity passed the live nonce test;
  Grok's selectors are written but need a `--login` and a live run to confirm.
