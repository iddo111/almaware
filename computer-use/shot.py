#!/usr/bin/env python3
"""shot.py -- one screenshot via the computer-use server, saved to a file.
Usage: python shot.py D:/CLAUDE/_scratch/popup/watch-01.png
"""
import base64
import json
import subprocess
import sys

SERVER = r"D:\CLAUDE\computer-use\server.py"


def main():
    out = sys.argv[1]
    p = subprocess.Popen([sys.executable, SERVER],
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         text=True, bufsize=1)
    seq = [0]

    def call(method, params=None):
        seq[0] += 1
        msg = {"jsonrpc": "2.0", "id": seq[0], "method": method}
        if params is not None:
            msg["params"] = params
        p.stdin.write(json.dumps(msg) + "\n")
        p.stdin.flush()
        return json.loads(p.stdout.readline())

    try:
        call("initialize", {"protocolVersion": "2024-11-05",
                            "capabilities": {},
                            "clientInfo": {"name": "shot", "version": "1"}})
        r = call("tools/call", {"name": "screenshot", "arguments": {}})
        img = [c for c in r["result"]["content"]
               if c["type"] == "image"][0]
        raw = base64.b64decode(img["data"])
        open(out, "wb").write(raw)
        print("SHOT-OK %s %d bytes" % (out, len(raw)))
    finally:
        p.kill()


if __name__ == "__main__":
    main()
