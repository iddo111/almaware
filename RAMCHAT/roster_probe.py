"""Auto-detect every AI on the fleet and write roster.json for the RAMCHAT GUI.

Run from Task Scheduler every 5 minutes. Detection is evidence-based:
HTTP probes for services, process checks for apps, binary checks for CLIs,
recent-transcript checks for conversational agents. A member is marked dead
only after 3 consecutive failed probes (auto-remove-defunct without flapping).
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ROSTER = ROOT / "roster.json"
STATE = ROOT / "ramchat_session.json"
DESKCLOD_RECEIPT = ROOT / "ramchat_deskclod_receipt.json"
DEAD_AFTER = 3

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def http(url: str, timeout: int = 6, ok_codes: tuple[int, ...] = (200,)) -> bool:
    request = urllib.request.Request(url, headers={"Accept-Encoding": "gzip"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status in ok_codes
    except urllib.error.HTTPError as exc:
        return exc.code in ok_codes
    except Exception:
        return False


def process_running(name: str) -> bool:
    try:
        out = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {name}", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ).stdout
        return name.lower() in out.lower()
    except Exception:
        return False


def desktop_claude_running() -> bool:
    """Require the packaged Claude Desktop executable, not a same-named CLI."""
    try:
        script = (
            "$p=Get-CimInstance Win32_Process -Filter \"Name='claude.exe'\" | "
            "Where-Object {$_.ExecutablePath -like '*WindowsApps\\Claude_*\\app\\Claude.exe'}; "
            "if($p){'yes'}"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            timeout=15,
            encoding="utf-8",
            errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return result.returncode == 0 and result.stdout.strip() == "yes"
    except Exception:
        return False


def _message_age_minutes(value: object, now: datetime | None = None) -> float | None:
    """Return the age of a transcript HH:MM timestamp, including midnight wrap."""
    if not isinstance(value, str):
        return None
    try:
        hour, minute = (int(part) for part in value.split(":", 1))
        current = now or datetime.now()
        candidate = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
        # A small future skew can happen while writers cross a minute boundary.
        if candidate > current + timedelta(minutes=2):
            candidate -= timedelta(days=1)
        return max(0.0, (current - candidate).total_seconds() / 60)
    except (TypeError, ValueError):
        return None


def recent_transcript_post(
    who: str | tuple[str, ...],
    minutes: int = 120,
    markers: tuple[str, ...] = (),
) -> bool:
    """Require a recent attributable post, not merely a recently-written file.

    The previous implementation treated an old member in the transcript tail as
    live whenever *another* agent updated the session file.  That produced a
    false-full-house roster.  Participation now requires the record's own HH:MM
    timestamp plus optional identity markers (for example JOINED + RAMCHAT).
    """
    try:
        data = json.loads(STATE.read_text(encoding="utf-8"))
        records = data if isinstance(data, list) else []
        names = {who} if isinstance(who, str) else set(who)
        required = tuple(marker.casefold() for marker in markers)
        now = datetime.now()
        for message in reversed(records):
            if not isinstance(message, dict) or message.get("who") not in names:
                continue
            age = _message_age_minutes(message.get("at"), now)
            text = str(message.get("text", "")).casefold()
            if age is not None and age <= minutes and all(x in text for x in required):
                return True
        return False
    except Exception:
        return False


def attested_desktop_post(minutes: int = 120) -> bool:
    """Require a matching MCP receipt launched under packaged Claude Desktop."""
    try:
        receipt = json.loads(DESKCLOD_RECEIPT.read_text(encoding="utf-8"))
        if receipt.get("schema") != 1 or receipt.get("author") != "deskclod":
            return False
        issued = datetime.fromisoformat(str(receipt.get("issued_at", "")))
        now = datetime.now().astimezone()
        if issued.tzinfo is None:
            issued = issued.astimezone()
        if not timedelta(0) <= now - issued <= timedelta(minutes=minutes):
            return False
        chain = receipt.get("process_chain")
        if not isinstance(chain, list) or not any(
            isinstance(item, dict)
            and "\\windowsapps\\claude_" in str(item.get("executable", "")).casefold()
            and str(item.get("executable", "")).casefold().endswith("\\app\\claude.exe")
            for item in chain
        ):
            return False
        expected_hash = receipt.get("text_sha256")
        messages = json.loads(STATE.read_text(encoding="utf-8"))
        if not isinstance(messages, list):
            return False
        for message in reversed(messages):
            if not isinstance(message, dict) or message.get("who") != "deskclod":
                continue
            text = str(message.get("text", ""))
            age = _message_age_minutes(message.get("at"), now.replace(tzinfo=None))
            if (
                age is not None
                and age <= minutes
                and hashlib.sha256(text.encode("utf-8")).hexdigest() == expected_hash
                and "joined" in text.casefold()
                and "ramchat" in text.casefold()
            ):
                return True
        return False
    except Exception:
        return False


def probe_all() -> dict[str, dict[str, str]]:
    agy = r"C:\Users\<user>\AppData\Local\agy\bin\agy.exe"
    checks: dict[str, tuple[bool, str, str]] = {
        # name: (alive, detail_alive, detail_dead)
        "deskclod": (
            desktop_claude_running()
            and attested_desktop_post(),
            "Desktop Claude פרסם nonce עם קבלת MCP", "אין קבלת MCP מזוהה מ-Desktop Claude",
        ),
        "GPT-OSS 120B": (
            http("http://<tailnet-ip>:8000/props")
            and recent_transcript_post("GPT-OSS 120B", markers=("joined", "ramchat")),
            "eran4:8000 + nonce מזוהה", "endpoint או nonce חסר",
        ),
        "Qwen3-480B": (
            http("http://<tailnet-ip>:8080/health")
            and recent_transcript_post("Qwen3-480B", markers=("joined", "ramchat")),
            "eran1+2+3 + nonce מזוהה", "endpoint או nonce חסר",
        ),
        "Qwen-CLI": (
            bool(shutil.which("qwen"))
            and recent_transcript_post("Qwen-CLI", markers=("ramchat",)),
            "Qwen Code CLI + nonce מזוהה", "CLI או nonce חסר",
        ),
        "GLM-5.2": (
            http("http://<tailnet-ip>:8800/health", ok_codes=(200, 401))
            and recent_transcript_post("GLM-5.2", markers=("ramchat",)),
            "eran4:8800 + nonce מזוהה", "endpoint או nonce חסר",
        ),
        "Nemotron": (
            http("http://127.0.0.1:8095/api/models")
            and recent_transcript_post(
                ("Nemotron", "Nemotron 3 Super"), markers=("joined", "ramchat")
            ),
            "Alma 8095 + nonce מזוהה", "Alma 8095 או nonce חסר",
        ),
        "QUORUM": (
            http("http://127.0.0.1:8099/health"),
            "8099 חי", "8099 לא עונה",
        ),
        "ALMA-FS-MCP": (
            http("http://127.0.0.1:8930/health"),
            "8930 חי", "8930 לא עונה",
        ),
        "Perplexity": (
            process_running("Perplexity.exe")
            and recent_transcript_post("Perplexity", markers=("ramchat",)),
            "אפליקציה + nonce מזוהה", "אפליקציה או nonce חסר",
        ),
        "Codex": (
            os.path.exists(r"C:\Users\<user>\AppData\Local\Programs\OpenAI\Codex\bin\codex.exe")
            and recent_transcript_post(("Codex", "codex"), markers=("ramchat",)),
            "CLI + nonce מזוהה", "CLI או nonce חסר",
        ),
        "Gemini": (
            os.path.exists(agy)
            and recent_transcript_post("Gemini", markers=("joined", "ramchat")),
            "Antigravity Gemini + nonce מזוהה", "Antigravity או nonce חסר",
        ),
        "Grok": (
            os.path.exists(r"C:\Users\<user>\.grok\bin\grok.exe")
            and recent_transcript_post("Grok", markers=("ramchat",)),
            "CLI + nonce מזוהה", "CLI או nonce חסר",
        ),
        "claude-cli": (
            recent_transcript_post("claude-cli"),
            "פעיל בשיחה", "לא פעיל לאחרונה",
        ),
    }

    previous: dict[str, dict] = {}
    try:
        previous = json.loads(ROSTER.read_text(encoding="utf-8")).get("members", {})
    except Exception:
        pass

    members: dict[str, dict[str, str]] = {}
    for name, (alive, up_detail, down_detail) in checks.items():
        fails = 0 if alive else int(previous.get(name, {}).get("fails", 0)) + 1
        status = "alive" if alive else ("dead" if fails >= DEAD_AFTER else "unknown")
        members[name] = {
            "status": status,
            "detail": up_detail if alive else down_detail,
            "fails": fails,
        }
    return members


def main() -> int:
    members = probe_all()
    payload = {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "members": members,
    }
    temporary = ROSTER.with_name(ROSTER.name + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(ROSTER)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
