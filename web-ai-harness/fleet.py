"""The local fleet: models served over OpenAI-compatible HTTP.

This is the single source of truth for where the fleet lives. gui.py imports
FLEET from here; it used to re-declare the same two URLs inline, which is how
this file ended up imported by nothing at all.

It lived in providers/ and did not belong there: `providers` is the registry of
*browser* providers and its Protocol is is_logged_in/send_prompt/wait_for_reply.
These implement `ask()` over HTTP and share none of that. Keeping them in the
same package also meant importing a fleet endpoint dragged Playwright in.

The system prompt matters more than it looks. gpt-oss refuses questions like
"check the system you're on and report" because the phrasing pattern-matches to
reconnaissance in its safety training — while having no tools at all, so it was
apologising for something it could not do either way. Telling it plainly that it
is an operator's own diagnostic assistant, with read-only tools, on the
operator's own hardware, removes the ambiguity that produced the refusal.
"""
from __future__ import annotations

import json
import os

import diagnostics
from backends.http_openai import answer_text, chat, first_message

SYSTEM = (
    "You are a diagnostic assistant running on the operator's own machine and "
    "their own private DGX fleet. The operator owns all of this hardware and is "
    "asking about their own systems.\n\n"
    "You have read-only diagnostic tools. Call them to answer questions about "
    "the machine, its GPUs, the LAN, or the fleet — do not guess or state "
    "figures from memory, and do not describe what you 'would' do. Call the "
    "tool and report what it returns.\n\n"
    "The tools cannot modify anything: no writes, no installs, no configuration "
    "changes, no shell. Reporting the operator's own inventory back to them is "
    "the entire purpose of this assistant and is not a security concern.\n\n"
    "Answer concisely with concrete numbers. If a tool reports something is "
    "unavailable or unreachable, say so plainly rather than inventing a value."
)

MAX_TOOL_ROUNDS = 4


class LocalModel:
    """One OpenAI-compatible endpoint on the fleet."""

    backend = "http"

    def __init__(self, name: str, base_url: str, model: str,
                 api_key_env: str | None = None, host: str = "",
                 label: str = "", where: str = "") -> None:
        self.name = name
        self.base_url = base_url
        self.model = model
        self.api_key_env = api_key_env
        self.host = host or base_url.split("//")[-1].split(":")[0]
        self.label = label or name          # what the GUI shows
        self.where = where                  # which box it runs on

    def ask(self, prompt: str, *, timeout_s: int = 300, max_tokens: int = 2048,
            use_tools: bool = True) -> str:
        messages = [{"role": "system", "content": SYSTEM},
                    {"role": "user", "content": prompt}]
        tools = diagnostics.tool_schemas() if use_tools else None

        for _ in range(MAX_TOOL_ROUNDS):
            resp = chat(self.base_url, self.model, messages,
                        api_key_env=self.api_key_env, tools=tools,
                        max_tokens=max_tokens, timeout_s=timeout_s)
            msg = first_message(resp)
            calls = msg.get("tool_calls") or []
            if not calls:
                return answer_text(msg)

            messages.append(msg)
            for c in calls:
                fn = (c.get("function") or {}).get("name", "")
                messages.append({
                    "role": "tool",
                    "tool_call_id": c.get("id", fn),
                    "content": diagnostics.call(fn),
                })

        # Ran out of tool rounds — ask for a final answer with no tools left.
        resp = chat(self.base_url, self.model, messages,
                    api_key_env=self.api_key_env, max_tokens=max_tokens,
                    timeout_s=timeout_s)
        return answer_text(first_message(resp))


# The fleet, as it actually runs today. Change an endpoint HERE and gui.py
# follows; that is the point of this module existing.
GPT_OSS = LocalModel(
    name="gpt-oss",
    base_url=os.getenv("GPT_OSS_URL", "http://<tailnet-ip>:8000"),
    model=os.getenv("GPT_OSS_MODEL", "gpt-oss-120b"),
    host="<tailnet-ip>",
    label="gpt-oss 120B",
    where="eran4 · llama.cpp · MXFP4",
)

COLIBRI = LocalModel(
    name="colibri",
    base_url=os.getenv("COLIBRI_URL", "http://<tailnet-ip>:8800"),
    model="glm-5.2",
    api_key_env="COLI_API_KEY",
    host="<tailnet-ip>",
    # The speed warning belongs with the endpoint: GLM is slow enough that a user
    # staring at a blank pane assumes it hung.
    #
    # NOTE (2026-08-06 tuning): this URL points straight at eran4, which is the
    # SLOWEST node in the fleet (~0.5 tok/s) because it shares its 121 GiB with
    # gpt-oss and alma-stt, so only ~12 GB of experts stay resident.  eran1/2/3
    # now run at ~1.0 tok/s after the big-core OMP fix.  Set
    #     COLIBRI_URL=http://127.0.0.1:8801
    # to go through glm_router.py instead: it load-balances across all four nodes,
    # picks eran4 last, and is roughly 2x faster for a single request.
    label="GLM-5.2 (slow — ~1 tok/s via router, ~0.5 tok/s on eran4)",
    where="eran4 · colibrì · 744B MoE · int4 · ~0.5 tok/s, expect 1.5-4 min",
)

# Keyed by the id the GUI uses in its <select>.
FLEET = {"gpt-oss": GPT_OSS, "glm": COLIBRI}
