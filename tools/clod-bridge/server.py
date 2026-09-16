"""Clod-Bridge — receive text via HTTP, auto-paste into Claude Code window + press Enter.

Listens on Tailscale interface so A70 (<tailnet>.ts.net) can POST.
"""
import os
import sys
import time
import logging
import pyperclip
import pyautogui
import win32gui
import win32con
from flask import Flask, request, jsonify, send_from_directory
from waitress import serve

HOST = os.environ.get('CLOD_BRIDGE_HOST', '0.0.0.0')
PORT = int(os.environ.get('CLOD_BRIDGE_PORT', '8765'))
LOG_PATH = os.path.expandvars(r'%LOCALAPPDATA%\clod-bridge\bridge.log')
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[logging.FileHandler(LOG_PATH, encoding='utf-8'), logging.StreamHandler()],
)
log = logging.getLogger('clod-bridge')

app = Flask(__name__, static_folder='static', static_url_path='/static')

# Guitar Teacher PWA mounted at /guitar
GUITAR_STATIC = os.path.join(os.path.dirname(__file__), '..', 'guitar-teacher', 'static')
@app.route('/guitar/')
@app.route('/guitar')
def guitar_index():
    return send_from_directory(GUITAR_STATIC, 'index.html')
@app.route('/guitar/<path:p>')
def guitar_static(p):
    return send_from_directory(GUITAR_STATIC, p)
pyautogui.FAILSAFE = False


def find_target_windows(substring='Claude'):
    """Return list of (hwnd, title) for visible windows whose title contains substring (case-insensitive)."""
    results = []
    sub_l = substring.lower()

    def enum_proc(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return True
        title = win32gui.GetWindowText(hwnd)
        if not title:
            return True
        if sub_l in title.lower():
            results.append((hwnd, title))
        return True

    win32gui.EnumWindows(enum_proc, None)
    return results

# back-compat alias
def find_claude_windows():
    return find_target_windows('Claude')


def activate(hwnd):
    """Restore + bring to foreground."""
    try:
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    except Exception:
        pass
    win32gui.SetForegroundWindow(hwnd)


@app.route('/')
def index():
    return send_from_directory('static', 'index.html')


@app.route('/health')
def health():
    wins = find_target_windows('Claude') + find_target_windows('Grok')
    seen = set()
    out = []
    for hwnd, t in wins:
        if hwnd in seen: continue
        seen.add(hwnd)
        out.append({'title': t})
    return jsonify({
        'ok': True,
        'claude_windows': out,
        'tailscale_ip': '<tailnet-ip>',
    })


@app.route('/type', methods=['POST'])
def type_text():
    data = request.get_json(force=True, silent=True) or {}
    text = data.get('text', '').rstrip('\n')
    press_enter = bool(data.get('enter', True))
    title_match = data.get('title_match', 'Claude')

    if not text:
        return jsonify({'ok': False, 'error': 'empty text'}), 400

    wins = find_target_windows(title_match)
    if not wins:
        log.warning("no window matching %r", title_match)
        return jsonify({'ok': False, 'error': f'no window matching {title_match!r}'}), 404

    hwnd, title = wins[0]
    log.info("typing into %s (hwnd=%s) %d chars, enter=%s", title, hwnd, len(text), press_enter)

    try:
        activate(hwnd)
        time.sleep(0.25)
        pyperclip.copy(text)
        time.sleep(0.05)
        pyautogui.hotkey('ctrl', 'v')
        if press_enter:
            time.sleep(0.15)
            pyautogui.press('enter')
        return jsonify({'ok': True, 'window': title, 'chars': len(text), 'enter': press_enter})
    except Exception as e:
        log.exception("type failed")
        return jsonify({'ok': False, 'error': str(e)}), 500


if __name__ == '__main__':
    log.info("clod-bridge starting on %s:%d", HOST, PORT)
    log.info("PWA at http://<tailnet-ip>:%d/ — A70 opens this", PORT)
    serve(app, host=HOST, port=PORT, threads=4)
