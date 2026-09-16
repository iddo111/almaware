"""alma-mic / dicta.py — Hebrew brain via DictaLM, served on a DGX node.

ALMAWARE-pure APP code: ours. DictaLM (dicta-il) is a MODEL (model-not-app, like
Whisper and Grok). A 7B model is HEAVY, so per Iddo's 'heavy → DGX' rule it runs on
a DGX Spark box (128GB unified, plenty), NOT on the PC. This module is only the thin
CLIENT: a single-turn POST to an OpenAI-compatible endpoint the DGX exposes
(e.g. vLLM / llama.cpp server holding DictaLM). Pure stdlib (urllib), never raises.

    ans, who = ask("מה מזג האוויר?", url)     # who = "dicta" | "—"

Configure the endpoint in config.json -> dicta_url, e.g.
    http://your-llm-host:8090/v1/chat/completions
Serve it on the DGX with (example): a vLLM/llama.cpp OpenAI server loading
dicta-il/dictalm2.0-instruct. See DICTA_DGX_SERVE.md in this folder.
"""
from __future__ import annotations
import json
import urllib.error
import urllib.request

LABEL = "dicta"
_SYS = "אתה עוזר עברי. ענה בעברית תקנית, טבעית ורהוטה, בקצרה ולעניין. אל תשתמש באנגלית אלא אם הכרחי."


def available(url: str) -> bool:
    """We consider Dicta 'available' only if an endpoint is configured. Liveness is
    proven by actually asking (the DGX server may be down)."""
    return bool(url)


def ask(prompt: str, url: str, *, timeout: float = 90.0,
        model: str = "dicta") -> tuple[str, str]:
    """Single-turn ask to a DictaLM OpenAI-compatible endpoint on the DGX.
    Returns (answer_text, who). who = 'dicta' on success, '—' on any failure
    (reason as the text). Never raises."""
    prompt = (prompt or "").strip()
    if not prompt:
        return ("", "—")
    if not url:
        return ("דיקטה לא מוגדרת. הגדר כתובת שרת DictaLM על ה-DGX בהגדרות (dicta_url).", "—")

    body = json.dumps({
        "model": model,
        "messages": [{"role": "system", "content": _SYS},
                     {"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 400,
        "stream": False,
    }).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
        text = (data["choices"][0]["message"]["content"] or "").strip()
        return (text, LABEL) if text else ("דיקטה חזרה ריקה.", "—")
    except urllib.error.HTTPError as e:
        return (f"דיקטה: שגיאת שרת {e.code}. ודא שהמודל טעון על ה-DGX.", "—")
    except urllib.error.URLError as e:
        return (f"דיקטה לא זמינה ({getattr(e, 'reason', e)!r}). ודא ששרת ה-DGX רץ ונגיש.", "—")
    except (KeyError, ValueError, TypeError) as e:
        return (f"דיקטה: תשובה לא צפויה ({e!r}).", "—")
    except Exception as e:
        return (f"שגיאת דיקטה: {e!r}", "—")
