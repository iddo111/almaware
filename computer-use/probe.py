#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""probe.py -- end-to-end proof for the computer-use MCP server.

Spawns server.py over stdio and proves: handshake, tool list,
real screenshot (PNG magic + dims), cursor read, gate deny path
(confirm without valid id fails), and a HARMLESS gated round
trip: request move-to-current-position -> confirm -> cursor
verified unchanged -> audit shows requested+confirmed. A deny
path is proven too. Exits nonzero on any failure.
"""
import base64
import json
import subprocess
import sys

SERVER = r"D:\CLAUDE\computer-use\server.py"


class Rim:
    def __init__(self):
        self.p = subprocess.Popen(
            [sys.executable, SERVER],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            text=True, bufsize=1)
        self.seq = 0

    def call(self, method, params=None):
        self.seq += 1
        msg = {"jsonrpc": "2.0", "id": self.seq, "method": method}
        if params is not None:
            msg["params"] = params
        self.p.stdin.write(json.dumps(msg) + "\n")
        self.p.stdin.flush()
        line = self.p.stdout.readline()
        if not line:
            raise RuntimeError("server went silent on " + method)
        return json.loads(line)

    def tool(self, name, args=None):
        r = self.call("tools/call",
                      {"name": name, "arguments": args or {}})
        if "error" in r:
            raise RuntimeError("tool %s failed: %s"
                               % (name, r["error"]["message"]))
        return r["result"]

    def close(self):
        self.p.kill()


def check(cond, label):
    print(("PASS " if cond else "FAIL ") + label)
    if not cond:
        raise SystemExit("PROOF FAILED: " + label)

def main():
    rim = Rim()
    try:
        r = rim.call("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "probe", "version": "1.0"}})
        check(r["result"]["serverInfo"]["name"] == "computer-use",
              "handshake names computer-use")

        r = rim.call("tools/list")
        names = sorted(t["name"] for t in r["result"]["tools"])
        check(names == ["audit_tail", "confirm_action",
                        "cursor_pos", "deny_action",
                        "list_windows", "request_action",
                        "screenshot"],
              "7 tools listed: " + ",".join(names))

        res = rim.tool("screenshot")
        img = [c for c in res["content"] if c["type"] == "image"][0]
        raw = base64.b64decode(img["data"])
        check(raw[:8] == b"\x89PNG\r\n\x1a\n", "screenshot is a real PNG")
        check(len(raw) > 10000, "screenshot has real pixels (%d bytes)"
              % len(raw))
        print("INFO " + res["content"][0]["text"])

        pos = json.loads(rim.tool("cursor_pos")["content"][0]["text"])
        check("x" in pos and "y" in pos, "cursor read")

        wins = json.loads(
            rim.tool("list_windows")["content"][0]["text"])
        check(isinstance(wins, list) and len(wins) > 0,
              "windows listed (%d)" % len(wins))
        print("INFO first window: " + wins[0][:60])

        bad = rim.call("tools/call", {"name": "confirm_action",
                                      "arguments": {"confirm_id": "c99999"}})
        check("error" in bad, "confirm with bogus id is refused")

        req = json.loads(rim.tool(
            "request_action",
            {"op": "move",
             "params": {"x": pos["x"], "y": pos["y"]}})[
                 "content"][0]["text"])
        cid = req["confirm_id"]
        check(cid.startswith("c"), "move staged, id " + cid)

        done = json.loads(rim.tool(
            "confirm_action",
            {"confirm_id": cid})["content"][0]["text"])
        pos2 = json.loads(
            rim.tool("cursor_pos")["content"][0]["text"])
        check(pos2 == pos, "harmless move executed, cursor same")

        again = rim.call("tools/call", {"name": "confirm_action",
                                        "arguments": {"confirm_id": cid}})
        check("error" in again, "confirm id is single-use")

        req2 = json.loads(rim.tool(
            "request_action",
            {"op": "key", "params": {"key": "enter"}})[
                "content"][0]["text"])
        d = json.loads(rim.tool(
            "deny_action",
            {"confirm_id": req2["confirm_id"]})[
                "content"][0]["text"])
        check(d.get("denied") == req2["confirm_id"], "enter denied")
        after = rim.call("tools/call", {"name": "confirm_action",
                         "arguments": {"confirm_id": req2["confirm_id"]}})
        check("error" in after, "denied action cannot run")

        tail = json.loads(rim.tool(
            "audit_tail", {"n": 30})["content"][0]["text"])
        events = [e["event"] for e in tail]
        for want in ("requested", "confirmed", "denied",
                     "confirm_rejected", "screenshot"):
            check(want in events, "audit shows " + want)
        print("ALL-PROOF-PASSED")
    finally:
        rim.close()


if __name__ == "__main__":
    main()
