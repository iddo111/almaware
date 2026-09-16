#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
fleet.py -- one-shot question to Iddo's own free fleet models.

Never spend a paid API call for bulk/simple work: this hits his resident
DGX models (qwen-coder on dgx4:8450, gpt-oss-120b on eran2:8000) over their
OpenAI-compatible /v1/chat/completions endpoint. Free: his hardware.

Usage:
    python fleet.py "write a regex for an IPv4 address"
    python fleet.py "explain this error" --system "You are terse."

Options:
    --max-tokens N     cap on the answer (default 600)
    --temperature F    default 0.2
    --system TEXT      optional system prompt
    --help             this text
"""
import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import lower_priority, approx_tokens, call_fleet, eprint


def main():
    ap = argparse.ArgumentParser(prog="fleet.py", description=__doc__)
    ap.add_argument("prompt", nargs="+")
    ap.add_argument("--max-tokens", type=int, default=600)
    ap.add_argument("--temperature", type=float, default=0.2)
    ap.add_argument("--system", default=None)
    args = ap.parse_args()

    lower_priority()
    prompt = " ".join(args.prompt)
    messages = []
    if args.system:
        messages.append({"role": "system", "content": args.system})
    messages.append({"role": "user", "content": prompt})

    try:
        name, model, content = call_fleet(
            messages, max_tokens=args.max_tokens, temperature=args.temperature)
    except RuntimeError as e:
        print("fleet.py: no fleet model answered (%s)" % e)
        return

    print(content.strip())
    saved = approx_tokens(prompt) + approx_tokens(content)
    print("[fleet.py] answered by %s (%s), free -- ~%d paid tokens avoided"
          % (name, model, saved))


if __name__ == "__main__":
    main()
