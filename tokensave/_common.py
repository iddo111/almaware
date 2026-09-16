"""
tokensave / _common.py — shared helpers, stdlib only.
Not a CLI. Imported by ask.py, web.py, sum.py, peek.py, fleet.py.
"""
import os
import sys
import json
import urllib.request
import urllib.parse
import urllib.error

# Set BELOW_NORMAL priority for this process on Windows so bulk/heavy calls
# never compete with Iddo's live mic/audio pipeline. Cheap, best-effort.
def lower_priority():
    if os.name == "nt":
        try:
            import ctypes
            IDLE_PRIORITY_CLASS = 0x00000040
            BELOW_NORMAL_PRIORITY_CLASS = 0x00004000
            handle = ctypes.windll.kernel32.GetCurrentProcess()
            ctypes.windll.kernel32.SetPriorityClass(handle, BELOW_NORMAL_PRIORITY_CLASS)
        except Exception:
            pass


def http_get_json(url, timeout=2.5, headers=None):
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "tokensave/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def http_get_text(url, timeout=4.0, headers=None):
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "tokensave/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def http_post_json(url, payload, timeout=90.0, headers=None):
    data = json.dumps(payload).encode("utf-8")
    hdrs = {"Content-Type": "application/json", "User-Agent": "tokensave/1.0"}
    hdrs.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=hdrs, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def approx_tokens(s):
    """Very rough token estimate: ~4 chars/token (English) — good enough for
    a savings estimate, not for billing."""
    if not s:
        return 0
    return max(1, len(s) // 4)


def savings_line(raw_chars, out_chars, label="tokensave"):
    raw_tok = approx_tokens("x" * raw_chars)
    out_tok = approx_tokens("x" * out_chars)
    saved = max(0, raw_tok - out_tok)
    pct = (saved / raw_tok * 100) if raw_tok else 0
    return "[%s] ~%d tokens read avoided, ~%d tokens shown (saved ~%d, %.0f%%)" % (
        label, raw_tok, out_tok, saved, pct
    )


def eprint(*a, **k):
    print(*a, file=sys.stderr, **k)


# Iddo's own resident fleet models -- free, his hardware. Order = try order.
# (name, chat-completions url, model id)
FLEET_ENDPOINTS = [
    ("dgx4-coder", "https://<tailnet-host>:8450/v1/chat/completions",
     "qwen-coder-dgx4:latest"),
    ("eran2-gptoss120b", "http://<tailnet-ip>:8000/v1/chat/completions",
     "gpt-oss-120b"),
]


def call_fleet(messages, max_tokens=600, temperature=0.2, timeout=120.0,
                endpoints=None, verify_tls=False):
    """Try each fleet endpoint in order, return (name, model, content) of the
    first one that answers. Raises RuntimeError if none respond."""
    import ssl
    ctx = ssl._create_unverified_context() if not verify_tls else None
    errs = []
    for name, url, model in (endpoints or FLEET_ENDPOINTS):
        payload = {"model": model, "messages": messages,
                   "max_tokens": max_tokens, "temperature": temperature}
        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url, data=data, method="POST",
                headers={"Content-Type": "application/json",
                         "User-Agent": "tokensave/1.0"})
            if url.startswith("https://") and ctx is not None:
                with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
                    resp = json.loads(r.read().decode("utf-8", "replace"))
            else:
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    resp = json.loads(r.read().decode("utf-8", "replace"))
            content = resp["choices"][0]["message"]["content"]
            return name, model, content
        except Exception as e:
            errs.append("%s: %s" % (name, e))
            continue
    raise RuntimeError("no fleet endpoint answered -- " + " | ".join(errs))
