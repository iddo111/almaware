"""
claude-cli-bridge.py — pipes the Hermes Baileys bridge to claude.exe (CC subscription).

Hermes's bridge.js runs on http://127.0.0.1:3000 with the working WA session
at C:\\Users\\iddo1\\.hermes\\whatsapp\\session\\. This script polls /messages,
calls `claude.exe -p` for each inbound from Iddo, POSTs the reply via /send.

No Anthropic API key required — uses the CC subscription via claude.exe.

לזכרה של עלמה ז״ל — iddoperez.ai
"""
from __future__ import annotations
import json
import os
import sys
import time
import logging
import subprocess
from collections import deque
from pathlib import Path

import requests

BRIDGE = os.environ.get("BRIDGE_URL", "http://127.0.0.1:3000")
CLAUDE_EXE = os.environ.get("CLAUDE_EXE", r"C:\Users\<user>\.local\bin\claude.exe")
MODEL = os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5-20251001")
POLL_S = float(os.environ.get("POLL_S", "2"))
HISTORY_TURNS = int(os.environ.get("HISTORY_TURNS", "10"))
ROOT = Path(__file__).resolve().parent
LOG_PATH = ROOT / "claude-cli-bridge.log"
STATE_PATH = ROOT / "claude-cli-bridge-state.json"

# Allowlist: only respond to these. WhatsApp uses both phone msisdn JIDs
# (`@s.whatsapp.net`) AND LID-based JIDs (`@lid`). Iddo's LID is
# 54262767870123 — confirmed via Hermes inbound log where senderName="עידו פרץ".
# (The old forensic_commission_2026-05-17 mislabeled this LID "Argentine" — it's
# actually Iddo's own LID under WhatsApp's identifier transition.)
ALLOWED_NUMBERS = {"972528174749", "54262767870123"}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("clod-bridge")

# Conversation history per chatId. Each entry: {"role": "user|assistant", "content": str}
histories: dict[str, deque] = {}


def _load_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(state: dict) -> None:
    try:
        STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        log.warning("state save failed: %s", e)


def _chat_phone(chatId: str) -> str:
    return chatId.split("@", 1)[0]


def _allowed(chatId: str, senderId: str) -> bool:
    return _chat_phone(chatId) in ALLOWED_NUMBERS or _chat_phone(senderId) in ALLOWED_NUMBERS


def _hist(chatId: str) -> deque:
    if chatId not in histories:
        histories[chatId] = deque(maxlen=HISTORY_TURNS * 2)
    return histories[chatId]


SYSTEM_PROMPT = (
    "You are Haiku, chatting with Iddo Perez on WhatsApp. Reply in the same "
    "language he uses (Hebrew or English). Be concise — WhatsApp messages, "
    "not essays. Be warm, direct, capable. If he asks for code or a long "
    "plan, deliver it cleanly. If he just wants to chat, just chat. Never "
    "preface with 'Sure!' or 'Of course!'. לזכרה של עלמה ז״ל."
)


def call_claude(chatId: str, user_text: str) -> str:
    """Shell out to claude.exe -p with the conversation history baked into the prompt."""
    hist = _hist(chatId)
    transcript_lines = []
    for turn in hist:
        speaker = "USER" if turn["role"] == "user" else "YOU"
        transcript_lines.append(f"{speaker}: {turn['content']}")
    transcript_lines.append(f"USER: {user_text}")
    transcript = "\n".join(transcript_lines)

    prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        f"Conversation so far (most recent at bottom):\n"
        f"---\n{transcript}\n---\n\n"
        f"Reply now as YOU to the last USER message. Output ONLY the reply text, "
        f"no role prefix, no markdown headers."
    )

    try:
        result = subprocess.run(
            [CLAUDE_EXE, "-p", "--model", MODEL, prompt],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        if result.returncode != 0:
            log.error("claude.exe rc=%d stderr=%s", result.returncode, (result.stderr or "")[:500])
            return f"[claude.exe error rc={result.returncode}]"
        reply = (result.stdout or "").strip()
        if not reply:
            log.warning("claude.exe empty stdout; stderr=%s", (result.stderr or "")[:300])
            return "[empty reply from claude.exe]"
        return reply
    except subprocess.TimeoutExpired:
        log.error("claude.exe timed out (120s)")
        return "[timeout]"
    except Exception as e:
        log.error("claude.exe exception: %s", e)
        return f"[exception: {e}]"


def post_send(chatId: str, message: str) -> bool:
    try:
        r = requests.post(
            f"{BRIDGE}/send",
            json={"chatId": chatId, "message": message},
            timeout=90,
        )
        if r.ok:
            return True
        log.error("/send failed: %s %s", r.status_code, r.text[:200])
        return False
    except Exception as e:
        log.error("/send exception: %s", e)
        return False


def main() -> None:
    log.info("starting; bridge=%s claude=%s model=%s", BRIDGE, CLAUDE_EXE, MODEL)

    # Sanity check the bridge
    try:
        h = requests.get(f"{BRIDGE}/health", timeout=5).json()
        log.info("bridge health: %s", h)
    except Exception as e:
        log.error("bridge unreachable at %s: %s", BRIDGE, e)
        sys.exit(2)

    state = _load_state()
    seen_ids: set = set(state.get("seen_ids", [])[-500:])

    while True:
        try:
            r = requests.get(f"{BRIDGE}/messages", timeout=10)
            if not r.ok:
                log.warning("/messages %s %s", r.status_code, r.text[:120])
                time.sleep(POLL_S)
                continue
            events = r.json()
        except Exception as e:
            log.warning("/messages exception: %s", e)
            time.sleep(POLL_S)
            continue

        for ev in events:
            mid = ev.get("messageId")
            if mid and mid in seen_ids:
                continue
            if mid:
                seen_ids.add(mid)
                if len(seen_ids) > 1000:
                    seen_ids = set(list(seen_ids)[-500:])

            body = (ev.get("body") or "").strip()
            chatId = ev.get("chatId") or ""
            senderId = ev.get("senderId") or chatId
            sender = ev.get("senderName") or _chat_phone(senderId)
            is_group = ev.get("isGroup")

            if is_group:
                continue
            if not body:
                continue
            if not _allowed(chatId, senderId):
                log.info("ignoring non-allowlisted chat: %s", chatId)
                continue

            log.info("<- %s (%s): %s", sender, chatId, body[:200])

            hist = _hist(chatId)
            hist.append({"role": "user", "content": body})

            reply = call_claude(chatId, body)
            hist.append({"role": "assistant", "content": reply})

            ok = post_send(chatId, reply)
            status = "OK" if ok else "FAIL"
            log.info("-> %s [%s]: %s", sender, status, reply[:200])

            state["seen_ids"] = list(seen_ids)[-500:]
            _save_state(state)

        time.sleep(POLL_S)


if __name__ == "__main__":
    main()
