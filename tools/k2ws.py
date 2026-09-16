"""k2ws.py -- minimal websocket client for the Creality K2 Plus local API (port 9999).

Why this exists: the printer's Moonraker/Klipper gcode queue is jammed -- even M105
times out -- because Creality's runout handler paused the print in THEIR firmware
layer, above Klipper, and is holding the queue. The touchscreen normally clears that,
but the screen is dead (loose cable). Port 9999 is the same channel the screen and
the Creality app use, so it is the only remaining door into the stuck layer.

No dependencies: raw socket + hand-rolled RFC6455 framing.

  python k2ws.py state                 -- dump what their layer thinks is happening
  python k2ws.py send '<json>'         -- send one raw JSON command, print replies
  python k2ws.py gcode 'M105'          -- send gcode through their layer
"""
import base64
import json
import os
import socket
import struct
import sys
import time

HOST = os.environ.get("K2_HOST", "<lan-ip>")
PORT = 9999


def connect(timeout=6):
    s = socket.create_connection((HOST, PORT), timeout=timeout)
    key = base64.b64encode(os.urandom(16)).decode()
    req = (
        f"GET / HTTP/1.1\r\nHost: {HOST}:{PORT}\r\nUpgrade: websocket\r\n"
        f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
        f"Sec-WebSocket-Version: 13\r\n\r\n"
    ).encode()
    s.sendall(req)
    buf = b""
    while b"\r\n\r\n" not in buf:
        b = s.recv(4096)
        if not b:
            raise RuntimeError("closed during handshake")
        buf += b
    head, rest = buf.split(b"\r\n\r\n", 1)
    if b"101" not in head.split(b"\r\n")[0]:
        raise RuntimeError("handshake failed: " + head[:120].decode("utf-8", "replace"))
    return s, rest


def send_text(s, text):
    payload = text.encode()
    n = len(payload)
    hdr = b"\x81"
    mask = os.urandom(4)
    if n < 126:
        hdr += bytes([0x80 | n])
    elif n < 65536:
        hdr += bytes([0x80 | 126]) + struct.pack(">H", n)
    else:
        hdr += bytes([0x80 | 127]) + struct.pack(">Q", n)
    masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
    s.sendall(hdr + mask + masked)


def frames(s, buf, seconds=3.0):
    """yield decoded text frames for `seconds`"""
    s.settimeout(0.6)
    end = time.time() + seconds
    while time.time() < end:
        while True:
            if len(buf) < 2:
                break
            b1, b2 = buf[0], buf[1]
            op = b1 & 0x0F
            ln = b2 & 0x7F
            off = 2
            if ln == 126:
                if len(buf) < 4:
                    break
                ln = struct.unpack(">H", buf[2:4])[0]
                off = 4
            elif ln == 127:
                if len(buf) < 10:
                    break
                ln = struct.unpack(">Q", buf[2:10])[0]
                off = 10
            if len(buf) < off + ln:
                break
            data = buf[off:off + ln]
            buf = buf[off + ln:]
            if op == 1:
                yield data.decode("utf-8", "replace")
            elif op == 8:
                return
        try:
            more = s.recv(65536)
            if not more:
                return
            buf += more
        except socket.timeout:
            continue


def merged_state(seconds=4.0):
    s, rest = connect()
    out = {}
    try:
        for t in frames(s, rest, seconds):
            try:
                d = json.loads(t)
                if isinstance(d, dict):
                    out.update(d)
            except Exception:
                pass
    finally:
        s.close()
    return out


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    cmd = sys.argv[1]

    if cmd == "state":
        st = merged_state(4.0)
        keys = sys.argv[2:] or None
        if keys:
            for k in keys:
                for kk in sorted(st):
                    if k.lower() in kk.lower():
                        print(f"{kk:28} = {st[kk]}")
        else:
            for k in sorted(st):
                v = str(st[k])
                if len(v) > 110:
                    v = v[:110] + "..."
                print(f"{k:28} = {v}")
        return

    if cmd in ("send", "gcode"):
        if cmd == "gcode":
            payload = json.dumps({"method": "set", "params": {"gcodeCmd": sys.argv[2]}})
        else:
            payload = sys.argv[2]
        s, rest = connect()
        try:
            # let the initial state burst pass so replies are not buried
            list(frames(s, rest, 1.2))
            print(">>>", payload)
            send_text(s, payload)
            for t in frames(s, b"", 5.0):
                if len(t) > 400:
                    try:
                        d = json.loads(t)
                        keep = {k: v for k, v in d.items()
                                if any(w in k.lower() for w in
                                       ("err", "state", "pause", "print", "nozzle", "gcode", "cur", "layer"))}
                        t = json.dumps(keep, ensure_ascii=False)
                    except Exception:
                        t = t[:400]
                print("<<<", t[:400])
        finally:
            s.close()
        return

    print("unknown command")


if __name__ == "__main__":
    main()
