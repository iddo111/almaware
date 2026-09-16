#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""computer-use MCP server -- Iddo's PC hands, gated.

Shape (chosen 2026-09-13): MCP stdio server, stdlib only.
Read-only tools run free: screenshot, cursor_pos, list_windows,
audit_tail. Everything that moves the machine (click, move, type,
key, scroll) runs ONLY as request_action -> confirm_action, one
confirm id per action, single-use, 120 s expiry. Every allow AND
deny lands in audit.jsonl (append-only).

Run:  python D:\\CLAUDE\\computer-use\\server.py   (stdio MCP)
Probe: python D:\\CLAUDE\\computer-use\\probe.py
"""
import base64
import binascii
import ctypes
import json
import os
import struct
import sys
import time
import zlib

APP_DIR = os.path.dirname(os.path.abspath(__file__))
AUDIT_PATH = os.path.join(APP_DIR, "audit.jsonl")
CONFIRM_TTL_S = 120

_pending = {}
_confirm_seq = 0

# ----------------------------------------------------------------------------
# Audit + confirm store
# ----------------------------------------------------------------------------
def audit(event, detail):
    rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "event": event, "detail": detail}
    with open(AUDIT_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def audit_tail(n=20):
    if not os.path.isfile(AUDIT_PATH):
        return []
    with open(AUDIT_PATH, encoding="utf-8") as f:
        lines = [l for l in f.read().splitlines() if l.strip()]
    out = []
    for line in lines[-n:]:
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def new_confirm(op, params):
    global _confirm_seq
    _confirm_seq += 1
    cid = "c%05d" % _confirm_seq
    _pending[cid] = {"op": op, "params": params,
                     "ts": time.time(), "state": "pending"}
    audit("requested", {"id": cid, "op": op, "params": params})
    return cid


def pop_confirm(cid):
    rec = _pending.get(cid)
    if rec is None:
        return None, "unknown confirm id"
    if rec["state"] != "pending":
        return None, "already " + rec["state"]
    if time.time() - rec["ts"] > CONFIRM_TTL_S:
        rec["state"] = "expired"
        audit("expired", {"id": cid})
        return None, "expired"
    rec["state"] = "confirmed"
    return rec, ""

# ----------------------------------------------------------------------------
# Screenshot (ctypes BitBlt + minimal PNG encoder, stdlib only)
# ----------------------------------------------------------------------------
user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

SRCCOPY = 0x00CC0020
BI_RGB = 0


def _png_chunk(ctype, data):
    out = struct.pack(">I", len(data)) + ctype + data
    out += struct.pack(">I", binascii.crc32(ctype + data) & 0xFFFFFFFF)
    return out


def _encode_png_rgb(w, h, rows):
    raw = b"".join(b"\x00" + r for r in rows)
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n"
            + _png_chunk(b"IHDR", ihdr)
            + _png_chunk(b"IDAT", zlib.compress(raw, 6))
            + _png_chunk(b"IEND", b""))


def take_screenshot():
    w = user32.GetSystemMetrics(0)
    h = user32.GetSystemMetrics(1)
    hdc = user32.GetDC(0)
    mdc = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    gdi32.SelectObject(mdc, bmp)
    gdi32.BitBlt(mdc, 0, 0, w, h, hdc, 0, 0, SRCCOPY)

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", ctypes.c_uint32),
                    ("biWidth", ctypes.c_int32),
                    ("biHeight", ctypes.c_int32),
                    ("biPlanes", ctypes.c_uint16),
                    ("biBitCount", ctypes.c_uint16),
                    ("biCompression", ctypes.c_uint32),
                    ("biSizeImage", ctypes.c_uint32),
                    ("biXPelsPerMeter", ctypes.c_int32),
                    ("biYPelsPerMeter", ctypes.c_int32),
                    ("biClrUsed", ctypes.c_uint32),
                    ("biClrImportant", ctypes.c_uint32)]

    bi = BITMAPINFOHEADER()
    bi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bi.biWidth = w
    bi.biHeight = -h
    bi.biPlanes = 1
    bi.biBitCount = 32
    bi.biCompression = BI_RGB
    size = w * h * 4
    buf = ctypes.create_string_buffer(size)
    gdi32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bi), 0)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mdc)
    user32.ReleaseDC(0, hdc)

    px = buf.raw
    rows = []
    for y in range(h):
        row = bytearray(3 * w)
        off = y * w * 4
        for x in range(w):
            i = off + x * 4
            row[3 * x] = px[i + 2]
            row[3 * x + 1] = px[i + 1]
            row[3 * x + 2] = px[i]
        rows.append(bytes(row))
    return w, h, _encode_png_rgb(w, h, rows)

# ----------------------------------------------------------------------------
# Mouse + keyboard (ctypes SendInput / SetCursorPos)
# ----------------------------------------------------------------------------
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_WHEEL = 0x0800
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
INPUT_MOUSE = 0
INPUT_KEYBOARD = 1


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long),
                ("mouseData", ctypes.c_ulong),
                ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong),
                ("dwExtraInfo", ctypes.c_void_p)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", ctypes.c_ushort),
                ("wScan", ctypes.c_ushort),
                ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong),
                ("dwExtraInfo", ctypes.c_void_p)]


class _U(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong), ("u", _U)]


def _send(inputs):
    n = len(inputs)
    arr = (INPUT * n)(*inputs)
    done = user32.SendInput(n, arr, ctypes.sizeof(INPUT))
    if done != n:
        raise RuntimeError("SendInput did %d of %d" % (done, n))


def cursor_pos():
    from ctypes import wintypes
    pt = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return {"x": pt.x, "y": pt.y}


def mouse_move(x, y):
    if not user32.SetCursorPos(int(x), int(y)):
        raise RuntimeError("SetCursorPos failed")
    return cursor_pos()


def _mouse_click(flags):
    inp = INPUT()
    inp.type = INPUT_MOUSE
    inp.u.mi.dwFlags = flags
    _send([inp])


def mouse_click(x, y, button="left", double=False):
    mouse_move(x, y)
    if button == "right":
        down, up = MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP
    else:
        down, up = MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP
    _mouse_click(down)
    _mouse_click(up)
    if double:
        _mouse_click(down)
        _mouse_click(up)
    return {"x": int(x), "y": int(y), "button": button,
            "double": bool(double)}


def mouse_scroll(dx):
    inp = INPUT()
    inp.type = INPUT_MOUSE
    inp.u.mi.dwFlags = MOUSEEVENTF_WHEEL
    inp.u.mi.mouseData = int(dx)
    _send([inp])
    return {"wheel": int(dx)}

VK = {"enter": 0x0D, "tab": 0x09, "esc": 0x1B, "escape": 0x1B,
      "space": 0x20, "left": 0x25, "up": 0x26, "right": 0x27,
      "down": 0x28, "delete": 0x2E, "backspace": 0x08,
      "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22}


def _key_in(vk, up):
    inp = INPUT()
    inp.type = INPUT_KEYBOARD
    inp.u.ki.wVk = vk
    if up:
        inp.u.ki.dwFlags = KEYEVENTF_KEYUP
    return inp


def press_key(name):
    vk = VK.get(str(name).lower())
    if vk is None:
        raise ValueError("unknown key: %r" % (name,))
    _send([_key_in(vk, False), _key_in(vk, True)])
    return {"key": str(name).lower()}


def type_text(text):
    text = str(text)
    if len(text) > 2000:
        raise ValueError("type_text max 2000 chars")
    for ch in text:
        dn = INPUT()
        dn.type = INPUT_KEYBOARD
        dn.u.ki.wScan = ord(ch)
        dn.u.ki.dwFlags = KEYEVENTF_UNICODE
        up = INPUT()
        up.type = INPUT_KEYBOARD
        up.u.ki.wScan = ord(ch)
        up.u.ki.dwFlags = KEYEVENTF_UNICODE | KEYEVENTF_KEYUP
        _send([dn, up])
    return {"typed": len(text)}

# ----------------------------------------------------------------------------
# Windows (EnumWindows, visible top-level with titles)
# ----------------------------------------------------------------------------
def list_windows():
    from ctypes import wintypes
    titles = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool,
                        wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if n <= 0 or n > 300:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        t = buf.value.strip()
        if t:
            titles.append(t)
        return True

    user32.EnumWindows(cb, 0)
    return titles[:100]

# ----------------------------------------------------------------------------
# Gated actions: request -> confirm / deny
# ----------------------------------------------------------------------------
GATED_OPS = ("click", "move", "type", "key", "scroll")


def do_request(op, params):
    op = str(op)
    if op not in GATED_OPS:
        raise ValueError("unknown op: %r" % (op,))
    params = dict(params or {})
    if op == "click":
        params["x"], params["y"] = int(params["x"]), int(params["y"])
        params["button"] = params.get("button", "left")
        params["double"] = bool(params.get("double", False))
    elif op == "move":
        params["x"], params["y"] = int(params["x"]), int(params["y"])
    elif op == "type":
        params["text"] = str(params.get("text", ""))[:2000]
    elif op == "key":
        params["key"] = str(params.get("key", "")).lower()
    elif op == "scroll":
        params["delta"] = int(params.get("delta", 120))
    cid = new_confirm(op, params)
    return {"confirm_id": cid, "op": op, "params": params,
            "note": "call confirm_action to execute"}


def do_execute(rec):
    op, p = rec["op"], rec["params"]
    if op == "click":
        out = mouse_click(p["x"], p["y"], p["button"], p["double"])
    elif op == "move":
        out = mouse_move(p["x"], p["y"])
    elif op == "type":
        out = type_text(p["text"])
    elif op == "key":
        out = press_key(p["key"])
    elif op == "scroll":
        out = mouse_scroll(p["delta"])
    else:
        raise ValueError("unknown op")
    return out

# ----------------------------------------------------------------------------
# MCP stdio framing (newline-delimited JSON-RPC)
# ----------------------------------------------------------------------------
TOOLS = [
    {"name": "screenshot", "description": "Capture the screen as PNG.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "cursor_pos", "description": "Current mouse position.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "list_windows", "description": "Visible window titles.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "request_action",
     "description": "Stage a gated action; returns a confirm id.",
     "inputSchema": {"type": "object",
                     "properties": {"op": {"type": "string"},
                                    "params": {"type": "object"}},
                     "required": ["op"]}},
    {"name": "confirm_action",
     "description": "Execute a staged action by confirm id.",
     "inputSchema": {"type": "object",
                     "properties": {"confirm_id": {"type": "string"}},
                     "required": ["confirm_id"]}},
    {"name": "deny_action",
     "description": "Refuse a staged action by confirm id.",
     "inputSchema": {"type": "object",
                     "properties": {"confirm_id": {"type": "string"}},
                     "required": ["confirm_id"]}},
    {"name": "audit_tail", "description": "Last audit entries.",
     "inputSchema": {"type": "object",
                     "properties": {"n": {"type": "integer"}}}},
]


def _text(s):
    return {"content": [{"type": "text", "text": s}]}


def call_tool(name, args):
    args = args or {}
    if name == "screenshot":
        w, h, png = take_screenshot()
        audit("screenshot", {"w": w, "h": h, "bytes": len(png)})
        return {"content": [
            {"type": "text",
             "text": "screen %dx%d, %d bytes" % (w, h, len(png))},
            {"type": "image", "data": base64.b64encode(png).decode(),
             "mimeType": "image/png"}]}
    if name == "cursor_pos":
        return _text(json.dumps(cursor_pos()))
    if name == "list_windows":
        wins = list_windows()
        audit("list_windows", {"count": len(wins)})
        return _text(json.dumps(wins, ensure_ascii=False))
    if name == "request_action":
        return _text(json.dumps(
            do_request(args.get("op"), args.get("params"))))
    if name == "confirm_action":
        cid = args.get("confirm_id", "")
        rec, err = pop_confirm(cid)
        if rec is None:
            audit("confirm_rejected", {"id": cid, "why": err})
            raise ValueError(err)
        out = do_execute(rec)
        audit("confirmed", {"id": cid, "op": rec["op"],
                            "params": rec["params"], "result": out})
        return _text(json.dumps(out))
    if name == "deny_action":
        cid = args.get("confirm_id", "")
        rec = _pending.get(cid)
        if rec is None or rec["state"] != "pending":
            raise ValueError("unknown or settled confirm id")
        rec["state"] = "denied"
        audit("denied", {"id": cid})
        return _text(json.dumps({"denied": cid}))
    if name == "audit_tail":
        return _text(json.dumps(
            audit_tail(int(args.get("n", 20))), ensure_ascii=False))
    raise ValueError("unknown tool: %s" % (name,))

def handle(msg):
    mid = msg.get("id")
    method = msg.get("method", "")

    def ok(result):
        return {"jsonrpc": "2.0", "id": mid, "result": result}

    def err(code, text):
        return {"jsonrpc": "2.0", "id": mid,
                "error": {"code": code, "message": text}}

    if method == "initialize":
        return ok({"protocolVersion": "2024-11-05",
                   "capabilities": {"tools": {}},
                   "serverInfo": {"name": "computer-use",
                                  "version": "1.0.0"}})
    if method == "notifications/initialized":
        return None
    if method == "tools/list":
        return ok({"tools": TOOLS})
    if method == "tools/call":
        p = msg.get("params", {})
        try:
            return ok(call_tool(p.get("name"), p.get("arguments")))
        except Exception as e:
            audit("tool_error", {"tool": p.get("name"),
                                 "why": str(e)[:200]})
            return err(-32000, str(e))
    if method == "ping":
        return ok({})
    return err(-32601, "unknown method: " + method)


def main():
    inp = sys.stdin
    for line in inp:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except Exception:
            continue
        try:
            resp = handle(msg)
        except Exception as e:
            resp = {"jsonrpc": "2.0", "id": msg.get("id"),
                    "error": {"code": -32603, "message": str(e)}}
        if resp is not None:
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
