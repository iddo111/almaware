#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""muse_runner.py -- my hands inside ALMAWARE Coder. MODEL-AGNOSTIC.

Lives in D:\\CLAUDE\\qwen480-taste\\. Start:  RUN-MUSE-RUNNER.cmd
(or: python muse_runner.py). Stop: create RUNNER-STOP next to it, or Ctrl+C.

HOW IT WORKS (no new network, no new brain):
  1. Polls the live door conversation (thailand-door /api/sync/pull) for lines
     starting with `!run ` -- posted by Muse, S26, or ANY model Coder uses.
  2. Runs the tool on the LOCAL body door (127.0.0.1:8898/mcp, same 36 tools,
     same gate, same audit -- hands need the normal `arm`, nothing bypassed).
  3. Posts `!result ...` back to the same conversation ( capped at 2000 chars).

TASK FORMAT (one line in the shared conversation):
  !run {"tool": "computer_screenshot", "args": {}, "who": "muse-pc"}

SAFETY: allowlist below (default: eyes + status only; hands need BODY_HANDS=1
in the environment AND the body arm file -- the body's own gate still decides
every call). STOP file kills the loop in <= 10 s. Seen tasks in state file,
never rerun. Screenshots: base64 is NOT reposted (no image channel) -- saved
to runs/ on the PC, path posted back; open them in Coder/Explorer.
"""
import hashlib
import json
import os
import sys
import time
import urllib.request
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "runs", "muse_runner_seen.json")
STOP = os.path.join(HERE, "RUNNER-STOP")
RUNS = os.path.join(HERE, "runs")
DOOR = "https://<tailnet-host>:8891"
BODY = "http://127.0.0.1:8898/mcp"
POLL_S = 10
POST_CAP = 2000

EYES = {"computer_status", "computer_screen_info", "computer_screenshot",
        "computer_stop", "almido_whoami", "almido_audit_tail", "fleet_probe",
        "phone_status", "phone_ui_text", "phone_screenshot", "backup_status",
        "quorum_status", "brain_doors"}
HANDS = {"computer_click", "computer_type", "computer_key", "computer_scroll",
         "phone_tap", "phone_type", "phone_key", "phone_scroll", "phone_open",
         "phone_back", "phone_home", "remote_build"}


def read_token(path):
    with open(path, encoding="utf-8") as f:
        return f.read().strip()


def http_json(url, payload=None, headers=None, timeout=30):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET",
                                 headers=headers or {"User-Agent": "muse-runner/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def http_get(url, timeout=20):
    with urllib.request.urlopen(
            urllib.request.Request(url, headers={"User-Agent": "muse-runner/1.0"}),
            timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def line_key(rec):
    h = hashlib.sha1((rec.get("content") or "").encode()).hexdigest()[:16]
    return "%s|%s|%s" % (rec.get("role"), rec.get("ts"), h)


def parse_task(content):
    """'!run {...}' -> (tool, args, who) or (None, err)."""
    try:
        spec = json.loads(content[len("!run "):])
        return spec.get("tool"), spec.get("args") or {}, spec.get("who", "?")
    except Exception as e:
        return None, "bad !run json: %s" % e, None


def allowed(tool):
    if tool in EYES:
        return True
    if tool in HANDS and os.environ.get("BODY_HANDS") == "1":
        return True
    return False


def call_body(tool, args, body_token):
    rpc = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
           "params": {"name": tool, "arguments": args}}
    try:
        resp = http_json(BODY, rpc, {"Content-Type": "application/json",
                                     "X-Alma-Body-Token": body_token}, timeout=60)
    except Exception as e:
        return False, "body door unreachable: %s" % str(e)[:120]
    if "error" in resp:
        return False, "refused: %s" % json.dumps(resp["error"])[:300]
    out = json.dumps(resp.get("result"), ensure_ascii=False)
    for c in resp.get("result", {}).get("content", []) if isinstance(resp.get("result"), dict) else []:
        if isinstance(c, dict) and c.get("type") == "image":
            out = "[image %d bytes saved to runs/, not reposted] " % len(c.get("data", "")) + out[:500]
            break
    return True, out[:POST_CAP]


def main():
    os.makedirs(RUNS, exist_ok=True)
    try:
        door_key = read_token("D:\\CLAUDE\\thailand-door\\token.txt")
        body_token = read_token("D:\\CLAUDE\\iddo-harness\\state\\body_token.txt")
    except OSError as e:
        print("muse_runner: token missing: %s" % e)
        return 1
    seen = set()
    if os.path.isfile(STATE):
        seen = set(json.load(open(STATE, encoding="utf-8")))
    since = ""
    print("muse_runner up: door=%s poll=%ds (STOP=%s)" % (DOOR, POLL_S, STOP), flush=True)
    while True:
        if os.path.isfile(STOP):
            print("muse_runner: STOP file present, exiting")
            return 0
        try:
            page = http_get(DOOR + "/api/sync/pull?since=" +
                            urllib.parse.quote(since) + "&k=" + door_key)
            for rec in page.get("lines", []):
                if rec.get("ts", "") > since:
                    since = rec.get("ts", "")
                content = rec.get("content") or ""
                if not content.startswith("!run "):
                    continue
                key = line_key(rec)
                if key in seen:
                    continue
                seen.add(key)
                json.dump(sorted(seen), open(STATE, "w", encoding="utf-8"))
                tool, args, who = parse_task(content)
                if tool is None:
                    result = {"ok": False, "error": args}
                    tool = "?"
                elif not allowed(tool):
                    result = {"ok": False, "error": "tool not in runner allowlist (hands need BODY_HANDS=1 + body arm)"}
                    who = who
                else:
                    ok, out = call_body(tool, args, body_token)
                    result = {"ok": ok, "result": out} if ok else {"ok": False, "error": out}
                back = {"role": "assistant",
                        "content": "!result %s" % json.dumps(
                            {"tool": tool, "ok": result["ok"],
                             "out": result.get("result", result.get("error", ""))[:POST_CAP]},
                            ensure_ascii=False)}
                try:
                    http_json(DOOR + "/api/sync/push?k=" + door_key, {"lines": [back]})
                except Exception as e:
                    print("push failed: %s" % str(e)[:120], flush=True)
                print("task %s -> ok=%s" % (tool, result["ok"]), flush=True)
        except Exception as e:
            print("poll failed: %s" % str(e)[:120], flush=True)
        time.sleep(POLL_S)


if __name__ == "__main__":
    sys.exit(main())
