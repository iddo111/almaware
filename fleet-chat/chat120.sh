#!/bin/bash
# chat120 -- the maintained round-trip test for gpt-oss-120b chat.
# One real completion through every known route (tailnet, LAN,
# fabric, loopback); first answer wins. reasoning_effort:low is
# REQUIRED (empty-content scar, 2026-09-12). Kept with the
# fleet-chat project; deployed to /tmp on each DGX for runs.
# Usage: chat120 "prompt"  (default: reply PONG)
CANDS="http://<tailnet-ip>:8000 http://<lan-ip>:8000 http://<fabric-ip>:8000 http://<fabric-ip>:8000 http://127.0.0.1:8000"
PROMPT="${1:-reply PONG}"
for B in $CANDS; do
  OUT=$(timeout 25 python3 - "$B" "$PROMPT" <<'PYEOF' 2>/dev/null
import json, sys, urllib.request
base, prompt = sys.argv[1], sys.argv[2]
payload = {"model": "gpt-oss-120b",
           "messages": [{"role": "user", "content": prompt}],
           "max_tokens": 900,
           "chat_template_kwargs": {"reasoning_effort": "low"}}
req = urllib.request.Request(base + "/v1/chat/completions",
    data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
with urllib.request.urlopen(req, timeout=8) as r:
    d = json.loads(r.read().decode())
print("_BACKEND=" + base)
print(d["choices"][0]["message"]["content"][:500])
PYEOF
)
  if [ -n "$OUT" ]; then echo "$OUT"; exit 0; fi
done
echo "CHAT120-FAIL: no route to gpt-oss-120b" >&2
exit 1
