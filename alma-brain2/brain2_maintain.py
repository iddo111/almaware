#!/usr/bin/env python3
"""brain2_maintain.py — THE MAINTAINER of the ALMA SECOND BRAIN.

Karpathy's pattern: raw sources go in, the model MAINTAINS a wiki. This job is
the only thing allowed to author pages. Agents propose; the maintainer writes.

  python brain2_maintain.py --all                  # every source
  python brain2_maintain.py --scars --dry-run      # see what would change
  python brain2_maintain.py --apply-proposals      # drain the proposal queue
  python brain2_maintain.py --index                # rebuild index.md only
  python brain2_maintain.py --all --no-model       # deterministic only, no LLM

Rules it enforces (not suggestions):
  * laws/       — an agent proposal NEVER rewrites a law. Only Iddo's word does.
  * scars/      — append-only. History is not edited away.
  * every page  — carries `sources:` and a date, or it is not written.
  * empty model output is a FAILURE, never a page. (2026-09-11: gpt-oss spends
    the whole budget on reasoning_content and returns content="".)

Cheap by default: bulk summarising runs on the fleet's free gpt-oss-120b.
Claude is for judgement, not for 200 summaries.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import brain2_lib as B  # noqa: E402

FAILURES = Path(r"D:\CLAUDE\eran-coder-pack\10-FAILURES.md")
MEMORY_DIR = Path(r"C:\Users\<user>\.claude\projects\D--CLAUDE\memory")
MEMORY_INDEX = MEMORY_DIR / "MEMORY.md"
RAMCHAT_SESSION = Path(r"D:\CLAUDE\RAMCHAT\ramchat_session.json")
FLEET_INVENTORY = Path(r"D:\CLAUDE\fleet_inventory.json")
LAWS_FILE = Path(r"D:\CLAUDE\CLAUDE.md")

SYSTEM = (
    "You maintain a shared engineering wiki for the ALMA/ERAN project. "
    "Write Hebrew FIRST, then English. Be short, concrete and honest. "
    "Never invent a fact that is not in the material you were given. "
    "If something is unknown or contradictory, say so explicitly. "
    "No marketing language, no praise, no emoji."
)

BANNER = (
    "> \U0001fa9f **BROKEN WINDOWS LAW \u2014 \u05d7\u05d5\u05e7 \u05d4\u05d7\u05dc\u05d5\u05e0\u05d5\u05ea \u05d4\u05e9\u05d1\u05d5\u05e8\u05d9\u05dd:** "
    "if it's not working, fix it IMMEDIATELY \u2014 don't wait for Iddo to say. "
    "Test the REAL output, not a proxy (`health: ok` \u2260 working). "
    "A broken window left unfixed invites decay.\n"
)

# --------------------------------------------------------------------------
# source 1 — the 180 dated failures
# --------------------------------------------------------------------------

SUBSYSTEMS = [
    ("mic", "\u05d4\u05de\u05d9\u05e7\u05e8\u05d5\u05e4\u05d5\u05df (KESHEV)", [
        "mic", "keshev", "stt", "whisper", "audio", "brio", "dictat", "vad",
        "logprob", "decode", "utterance", "microphone", "voice-input", "wh-1000",
        "bluetooth", "clipping", "portaudio", "\u05de\u05d9\u05e7\u05e8\u05d5\u05e4\u05d5\u05df",
    ]),
    ("eran", "\u05e2\u05e8\u05df \u05d5\u05d4\u05d4\u05d5\u05dc\u05d5\u05d1\u05e8\u05d9\u05d9\u05df", [
        "eran'", "eran\u2019", "proto-eran", "protoeran", "holobrain", "syllable",
        "corpus", "mouth", "larynx", "babble", "jepa", "tts", "\u05e2\u05e8\u05df",
        "phoneme", "the child", "exam",
    ]),
    ("fleet", "\u05d4\u05e6\u05d9 \u05d5\u05d4\u05ea\u05e9\u05ea\u05d9\u05ea", [
        "dgx", "eran1", "eran2", "eran3", "eran4", "fabric", "qsfp", "480b",
        "vllm", "llama-server", "cluster", "tailscale", "oom", "gpu", "disk",
        "reboot", "systemd", "router", "dhcp", "port", "firmware", "xid",
    ]),
    ("coder", "\u05d4\u05e7\u05d5\u05d3\u05e8, \u05d4\u05e1\u05d5\u05db\u05e0\u05d9\u05dd \u05d5\u05d4\u05db\u05dc\u05d9\u05dd", [
        "almido", "mcp", "agent", "harness", "tool", "gate", "headless",
        "quorum", "git", "coder", "claude code", "codex", "grok", "qwen",
        "pyautogui", "computer use", "watchdog", "hook", "token",
    ]),
]
ENTRY_RE = re.compile(r"^### (.+?)$", re.M)
H2_RE = re.compile(r"^## (.+?)$", re.M)


def classify(text: str) -> str:
    low = text.lower()
    best, best_score = "other", 0
    for key, _he, words in SUBSYSTEMS:
        score = sum(low.count(w) for w in words)
        if score > best_score:
            best, best_score = key, score
    return best


def parse_failures() -> list[dict]:
    text = FAILURES.read_text(encoding="utf-8")
    entries: list[dict] = []
    marks = [(m.start(), m.group(1).strip()) for m in ENTRY_RE.finditer(text)]
    for i, (start, title) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        block = text[start:end].strip()
        body = block.split("\n", 1)[1].strip() if "\n" in block else ""
        date = ""
        dm = re.search(r"(20\d\d-\d\d-\d\d)", title)
        if dm:
            date = dm.group(1)
        rule = ""
        rm = re.search(r"\*\*Rule born:\*\*\s*(.+?)(?=\n- \*\*|\Z)", block, re.S)
        if rm:
            rule = " ".join(rm.group(1).split())
        src = ""
        sm = re.search(r"\*\*Source:\*\*\s*(.+?)(?=\n- \*\*|\Z)", block, re.S)
        if sm:
            src = " ".join(sm.group(1).split())
        entries.append({
            "title": title,
            "date": date,
            "body": body,
            "rule": rule,
            "source": src,
            "subsystem": classify(title + " " + block),
        })
    return entries


def ingest_scars(use_model: bool, dry_run: bool) -> list[str]:
    if not FAILURES.exists():
        return [f"SKIP scars: {FAILURES} missing"]
    entries = parse_failures()
    groups: dict[str, list[dict]] = {}
    for e in entries:
        groups.setdefault(e["subsystem"], []).append(e)
    he_names = {k: he for k, he, _ in SUBSYSTEMS}
    he_names["other"] = "\u05d0\u05d7\u05e8\u05d9\u05dd"
    log = []
    for key, items in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        items.sort(key=lambda e: e["date"] or "0000")
        pid = f"scars/{key}"
        head = ""
        if use_model:
            digest = "\n".join(f"- {e['date']} {e['title']} :: {e['rule'][:220]}" for e in items[:70])
            try:
                head = B.ask_model(
                    "\u05dc\u05d4\u05dc\u05df \u05e8\u05e9\u05d9\u05de\u05ea \u05db\u05d9\u05e9\u05dc\u05d5\u05e0\u05d5\u05ea \u05de\u05ea\u05d5\u05e2\u05d3\u05d9\u05dd \u05d1\u05ea\u05ea-\u05de\u05e2\u05e8\u05db\u05ea \""
                    + key + "\" \u05e9\u05dc \u05d4\u05e4\u05e8\u05d5\u05d9\u05e7\u05d8.\n\n" + digest +
                    "\n\n\u05db\u05ea\u05d5\u05d1 \u05e1\u05d9\u05db\u05d5\u05dd \u05e7\u05e6\u05e8: \u05e2\u05d3 5 \u05e9\u05d5\u05e8\u05d5\u05ea \u05d1\u05e2\u05d1\u05e8\u05d9\u05ea \u05d5\u05d0\u05d6 \u05e2\u05d3 5 \u05e9\u05d5\u05e8\u05d5\u05ea \u05d1\u05d0\u05e0\u05d2\u05dc\u05d9\u05ea, "
                    "\u05e9\u05e2\u05d5\u05e0\u05d4 \u05e2\u05dc: \u05de\u05d4 \u05d4\u05d3\u05e4\u05d5\u05e1 \u05d4\u05d7\u05d5\u05d6\u05e8? \u05de\u05d4 \u05d4\u05db\u05dc\u05dc \u05e9\u05d0\u05e1\u05d5\u05e8 \u05dc\u05e9\u05db\u05d5\u05d7? "
                    "\u05d0\u05dc \u05ea\u05de\u05e6\u05d9\u05d0 \u05e2\u05d5\u05d1\u05d3\u05d5\u05ea. \u05dc\u05dc\u05d0 \u05db\u05d5\u05ea\u05e8\u05d5\u05ea.",
                    system=SYSTEM, max_tokens=700,
                )
            except B.ModelEmpty as exc:
                head = ""
                log.append(f"  ! model empty for {pid}: {exc}")
        lines = [BANNER, f"# \u05e6\u05dc\u05e7\u05d5\u05ea \u2014 {he_names.get(key, key)} / Scars \u2014 {key}", ""]
        lines.append(f"**{len(items)} \u05e8\u05e9\u05d5\u05de\u05d5\u05ea \u05de\u05ea\u05d5\u05e2\u05d3\u05d5\u05ea / {len(items)} dated entries.** "
                     "\u05d4\u05d3\u05e3 \u05d4\u05d6\u05d4 \u05d4\u05d5\u05d0 append-only \u2014 \u05e6\u05dc\u05e7\u05d4 \u05dc\u05d0 \u05e0\u05de\u05d7\u05e7\u05ea. "
                     "/ This page is append-only \u2014 a scar is never deleted.")
        lines.append("")
        if head:
            lines += ["## \u05de\u05d4 \u05d6\u05d4 \u05de\u05dc\u05de\u05d3 / What this teaches", "", head.strip(), ""]
        lines += ["## \u05d4\u05e8\u05e9\u05d5\u05de\u05d5\u05ea / The entries", ""]
        for e in items:
            lines.append(f"### {e['title']}")
            lines.append("")
            lines.append(e["body"])
            lines.append("")
        fm = {
            "name": f"scars/{key}",
            "title": f"\u05e6\u05dc\u05e7\u05d5\u05ea {he_names.get(key, key)} / {key} scars",
            "section": "scars",
            "policy": "append-only",
            "entries": str(len(items)),
            "confidence": "measured",
            "lang": "he+en",
            "sources": [
                "D:/CLAUDE/eran-coder-pack/10-FAILURES.md (180 dated entries, verified 2026-09-11 08:50)",
            ],
        }
        status = B.write_page(pid, fm, "\n".join(lines), dry_run=dry_run)
        log.append(f"  {status:9} {pid}  ({len(items)} entries)")
    return log


# --------------------------------------------------------------------------
# source 2 — the memory index and the files it links
# --------------------------------------------------------------------------

LINK_RE = re.compile(r"\]\(([A-Za-z0-9_.-]+\.md)\)")
WANTED_SECTIONS = ("Now \u2014 the live front", "Work-rules")
FORBIDDEN_SECTION = "Iddo \u2014 how to be with him"


def memory_targets() -> dict[str, str]:
    """{filename: section} for the allowed sections only. Privacy law: nothing
    from 'Iddo — how to be with him', nothing named user_*."""
    text = MEMORY_INDEX.read_text(encoding="utf-8")
    out: dict[str, str] = {}
    marks = [(m.start(), m.group(1).strip()) for m in H2_RE.finditer(text)]
    for i, (start, name) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        if name == FORBIDDEN_SECTION or not any(w in name for w in WANTED_SECTIONS):
            continue
        for fn in LINK_RE.findall(text[start:end]):
            if fn.startswith("user_") or fn.startswith("index_") or fn == "MEMORY.md":
                continue
            out[fn] = name
    return out


def ingest_memory(use_model: bool, dry_run: bool, limit: int | None) -> list[str]:
    if not MEMORY_INDEX.exists():
        return [f"SKIP memory: {MEMORY_INDEX} missing"]
    targets = memory_targets()
    log = [f"  memory targets: {len(targets)} (user_* and the private section excluded)"]
    state = B.load_ingest_state()
    done = 0
    for fn, section in sorted(targets.items()):
        if limit and done >= limit:
            log.append(f"  (stopped at --limit {limit})")
            break
        src = MEMORY_DIR / fn
        if not src.exists():
            log.append(f"  ! missing source {fn}")
            continue
        raw = src.read_text(encoding="utf-8", errors="replace")
        stem = fn[:-3]
        is_law = stem.startswith("feedback_")
        pid = ("laws/" if is_law else "projects/") + B.slug(stem)
        h = B.body_hash(raw)
        key = f"memory:{fn}"
        if state["sources"].get(key, {}).get("hash") == h and B.page_path(pid).exists():
            log.append(f"  unchanged  {pid}")
            continue
        fm_src, body_src = B.parse_page(raw)
        desc = str(fm_src.get("description", ""))[:600]
        summary = ""
        if use_model:
            try:
                summary = B.ask_model(
                    "\u05dc\u05d4\u05dc\u05df \u05e7\u05d5\u05d1\u05e5 \u05d6\u05d9\u05db\u05e8\u05d5\u05df \u05e9\u05dc \u05d4\u05e4\u05e8\u05d5\u05d9\u05e7\u05d8 (\u05e9\u05dd: " + stem + ").\n\n"
                    + body_src[:9000] +
                    "\n\n---\n\u05db\u05ea\u05d5\u05d1 \u05d3\u05e3 \u05d5\u05d9\u05e7\u05d9 \u05e7\u05e6\u05e8:\n"
                    "1) \u05e9\u05d5\u05e8\u05d4 \u05d0\u05d7\u05ea \u05d1\u05e2\u05d1\u05e8\u05d9\u05ea: \u05de\u05d4 \u05d6\u05d4.\n"
                    "2) 3-6 \u05e9\u05d5\u05e8\u05d5\u05ea \u05d1\u05e2\u05d1\u05e8\u05d9\u05ea: \u05de\u05e6\u05d1 \u05e0\u05d5\u05db\u05d7\u05d9, \u05d4\u05d7\u05dc\u05d8\u05d5\u05ea, \u05de\u05d4 \u05e4\u05ea\u05d5\u05d7.\n"
                    "3) '## English' \u05d5\u05d0\u05d6 3-6 \u05e9\u05d5\u05e8\u05d5\u05ea \u05d1\u05d0\u05e0\u05d2\u05dc\u05d9\u05ea \u05e2\u05dd \u05d0\u05d5\u05ea\u05d5 \u05ea\u05d5\u05db\u05df.\n"
                    "\u05d0\u05dc \u05ea\u05de\u05e6\u05d9\u05d0 \u05e2\u05d5\u05d1\u05d3\u05d5\u05ea. \u05d0\u05dd \u05de\u05e9\u05d4\u05d5 \u05dc\u05d0 \u05d9\u05d3\u05d5\u05e2 \u2014 \u05db\u05ea\u05d5\u05d1 '\u05dc\u05d0 \u05d9\u05d3\u05d5\u05e2'.",
                    system=SYSTEM, max_tokens=800,
                )
            except B.ModelEmpty as exc:
                log.append(f"  ! model empty for {pid}: {exc}")
        confidence = "model-summary" if summary else "raw-only"
        lines = [BANNER, f"# {stem}", ""]
        if desc:
            lines += [f"**\u05ea\u05d9\u05d0\u05d5\u05e8 \u05de\u05d4\u05de\u05e7\u05d5\u05e8 / source description:** {desc}", ""]
        if summary:
            lines += [summary.strip(), ""]
        else:
            lines += ["*(\u05d0\u05d9\u05df \u05e1\u05d9\u05db\u05d5\u05dd \u05de\u05d5\u05d3\u05dc \u2014 \u05d4\u05d3\u05e3 \u05de\u05e6\u05d9\u05d2 \u05d0\u05ea \u05d4\u05de\u05e7\u05d5\u05e8 \u05d1\u05dc\u05d1\u05d3. "
                      "/ no model summary \u2014 raw source only.)*", ""]
        if is_law:
            lines += ["> \u26d4 **\u05d3\u05e3 \u05d7\u05d5\u05e7 \u2014 \u05dc\u05e7\u05e8\u05d9\u05d0\u05d4 \u05d1\u05dc\u05d1\u05d3 \u05dc\u05e1\u05d5\u05db\u05e0\u05d9\u05dd.** "
                      "\u05e8\u05e7 \u05de\u05d9\u05dc\u05d4 \u05e9\u05dc \u05e2\u05d9\u05d3\u05d5 \u05de\u05e9\u05e0\u05d4 \u05d7\u05d5\u05e7. "
                      "/ **LAW PAGE \u2014 read-only for agents.** Only Iddo's word changes a law.", ""]
        lines += ["## \u05d4\u05de\u05e7\u05d5\u05e8 \u05d4\u05de\u05dc\u05d0 / Full source", "", "<details><summary>"
                  + fn + "</summary>", "", body_src.strip()[:20000], "", "</details>"]
        fm = {
            "name": stem,
            "section": "laws" if is_law else "projects",
            "from_index_section": section,
            "confidence": confidence,
            "lang": "he+en",
            "sources": [f"memory/{fn} (Claude private memory dir, mirrored 2026-09-11)"],
        }
        if is_law:
            fm["policy"] = "read-only-for-agents"
        status = B.write_page(pid, fm, "\n".join(lines), dry_run=dry_run)
        log.append(f"  {status:9} {pid}")
        state["sources"][key] = {"hash": h, "page": pid, "at": B.now_iso()}
        done += 1
    if not dry_run:
        B.save_ingest_state(state)
    return log


# --------------------------------------------------------------------------
# source 3 — RAMCHAT
# --------------------------------------------------------------------------


# RAMCHAT posts carry only "HH:MM" — no date. Measured 2026-09-11: all 500
# messages, every one of them. So the day has to be INFERRED by walking
# backwards and noticing the clock go backwards. Every page built this way says
# so in its front matter; an inferred date must never be presented as a read one.
NOISE_AUTHORS = ("sibling-watchdog", "keshev-guard", "keshev-delivery", "fleet-inventory")


def _msg(m: dict) -> tuple[str, str, str]:
    return (
        str(m.get("who") or m.get("author") or m.get("from") or "unknown"),
        str(m.get("text") or m.get("message") or ""),
        str(m.get("at") or m.get("ts") or m.get("time") or ""),
    )


def _family(who: str) -> str:
    """`claude-cli-FABLE-A1fix` and `claude-cli-FABLE-wa2` are two task sessions
    of ONE worker. Twenty near-empty pages is not a wiki; one page with the
    sessions listed is. Keep the first two dash-segments."""
    parts = who.split("-")
    return "-".join(parts[:3]) if parts[:2] == ["claude", "cli"] else "-".join(parts[:2]) or who


def _infer_days(msgs: list[dict]) -> list[str]:
    """Assign a date to each message by walking backwards from today; a clock
    that jumps forward as we go back means we crossed midnight."""
    from datetime import date, timedelta

    day = date.today()
    days: list[str] = []
    prev_hhmm = None
    for m in reversed(msgs):
        _, _, at = _msg(m)
        hhmm = at[:5] if re.match(r"^\d\d:\d\d", at) else None
        if hhmm and prev_hhmm and hhmm > prev_hhmm:
            day = day - timedelta(days=1)
        if hhmm:
            prev_hhmm = hhmm
        days.append(day.isoformat())
    return list(reversed(days))


def ingest_ramchat(use_model: bool, dry_run: bool, tail: int = 200) -> list[str]:
    if not RAMCHAT_SESSION.exists():
        return [f"SKIP ramchat: {RAMCHAT_SESSION} missing"]
    raw = json.loads(RAMCHAT_SESSION.read_text(encoding="utf-8"))
    msgs = raw if isinstance(raw, list) else raw.get("conversation", [])
    msgs = [m for m in msgs if isinstance(m, dict)][-tail:]
    log = [f"  ramchat messages considered: {len(msgs)} (dates INFERRED - RAMCHAT stores only HH:MM)"]

    days = _infer_days(msgs)
    by_day: dict[str, list[dict]] = {}
    by_author: dict[str, list[dict]] = {}
    for m, day in zip(msgs, days):
        m = dict(m, _day=day)
        by_day.setdefault(day, []).append(m)
        by_author.setdefault(_family(_msg(m)[0]), []).append(m)

    # decisions/ — one page per day of council traffic
    for day, items in sorted(by_day.items()):
        pid = f"decisions/ramchat-{day}"
        signal = [m for m in items if _msg(m)[0] not in NOISE_AUTHORS]
        noise = len(items) - len(signal)
        digest = "\n".join(
            f"- [{_msg(m)[2]}] {_msg(m)[0]}: " + " ".join(_msg(m)[1].split())[:400]
            for m in signal
        )
        summary = ""
        if use_model and digest.strip():
            try:
                summary = B.ask_model(
                    "\u05dc\u05d4\u05dc\u05df \u05d4\u05d5\u05d3\u05e2\u05d5\u05ea \u05de\u05dc\u05d5\u05d7 \u05d4\u05de\u05d5\u05d3\u05e2\u05d5\u05ea \u05d4\u05de\u05e9\u05d5\u05ea\u05e3 \u05e9\u05dc \u05e6\u05d5\u05d5\u05ea \u05d4\u05e1\u05d5\u05db\u05e0\u05d9\u05dd \u05d1\u05ea\u05d0\u05e8\u05d9\u05da "
                    + day + ":\n\n" + digest[:12000] +
                    "\n\n---\n\u05db\u05ea\u05d5\u05d1: (\u05d0) '## \u05d4\u05d7\u05dc\u05d8\u05d5\u05ea' \u2014 \u05e8\u05e9\u05d9\u05de\u05d4 \u05e9\u05dc \u05d4\u05d7\u05dc\u05d8\u05d5\u05ea \u05e9\u05d4\u05ea\u05e7\u05d1\u05dc\u05d5 \u05d1\u05e4\u05d5\u05e2\u05dc, "
                    "\u05db\u05dc \u05d0\u05d7\u05ea \u05e2\u05dd \u05de\u05d9 \u05d4\u05d7\u05dc\u05d9\u05d8 \u05d5\u05de\u05d4 \u05d4\u05e9\u05ea\u05e0\u05d4. (\u05d1) '## \u05e4\u05ea\u05d5\u05d7' \u2014 \u05de\u05d4 \u05e0\u05d5\u05ea\u05e8 \u05e4\u05ea\u05d5\u05d7 \u05d0\u05d5 \u05e9\u05d1\u05d5\u05e8. "
                    "(\u05d2) '## English' \u2014 \u05d0\u05d5\u05ea\u05d5 \u05d3\u05d1\u05e8 \u05d1\u05d0\u05e0\u05d2\u05dc\u05d9\u05ea, \u05e7\u05e6\u05e8. \u05e8\u05e7 \u05de\u05d4 \u05e9\u05db\u05ea\u05d5\u05d1. \u05dc\u05dc\u05d0 \u05d4\u05de\u05e6\u05d0\u05d5\u05ea.",
                    system=SYSTEM, max_tokens=1100,
                )
            except B.ModelEmpty as exc:
                log.append(f"  ! model empty for {pid}: {exc}")
        lines = [BANNER, f"# \u05de\u05d5\u05e2\u05e6\u05ea \u05d4\u05e1\u05d5\u05db\u05e0\u05d9\u05dd \u2014 {day} / Agent council \u2014 {day}", ""]
        lines.append(f"**{len(items)} \u05d4\u05d5\u05d3\u05e2\u05d5\u05ea / messages** ({len(signal)} \u05de\u05e1\u05d5\u05db\u05e0\u05d9\u05dd, "
                     f"{noise} \u05de\u05e9\u05d5\u05de\u05e8\u05d9\u05dd \u05d0\u05d5\u05d8\u05d5\u05de\u05d8\u05d9\u05d9\u05dd / {noise} automated watchdog posts). "
                     "\u05de\u05e7\u05d5\u05e8: RAMCHAT `ramchat_session.json`.")
        lines.append("")
        lines.append("> \u26a0\ufe0f **\u05d4\u05ea\u05d0\u05e8\u05d9\u05da \u05de\u05e9\u05d5\u05e2\u05e8, \u05dc\u05d0 \u05e0\u05e7\u05e8\u05d0.** RAMCHAT \u05e9\u05d5\u05de\u05e8 \u05e8\u05e7 `HH:MM`. "
                     "\u05d4\u05d9\u05d5\u05dd \u05e0\u05d2\u05d6\u05e8 \u05de\u05d4\u05dc\u05d9\u05db\u05d4 \u05d0\u05d7\u05d5\u05e8\u05d4 \u05d1\u05d6\u05de\u05df. / "
                     "**The date is INFERRED, not read.** RAMCHAT stores only `HH:MM`; the day is "
                     "derived by walking backwards. Treat it as approximate.")
        lines.append("")
        if summary:
            lines += [summary.strip(), ""]
        lines += ["## \u05d4\u05d9\u05d5\u05de\u05df \u05d4\u05d2\u05d5\u05dc\u05de\u05d9 / Raw log", "", digest, ""]
        fm = {
            "name": f"ramchat-{day}",
            "section": "decisions",
            "date": day,
            "date_source": "inferred (RAMCHAT stores only HH:MM)",
            "messages": str(len(items)),
            "confidence": "model-summary" if summary else "raw-only",
            "lang": "he+en",
            "sources": ["D:/CLAUDE/RAMCHAT/ramchat_session.json (shared agent council transcript)"],
        }
        log.append(f"  {B.write_page(pid, fm, chr(10).join(lines), dry_run=dry_run):9} {pid}")

    # people-of-the-project/ — PROJECT ROLES ONLY. Never private life.
    for author, items in sorted(by_author.items()):
        if author == "unknown":
            continue
        pid = f"people-of-the-project/{B.slug(author)}"
        sessions = sorted({_msg(m)[0] for m in items})
        lines = [BANNER, f"# {author}", "",
                 "\u05ea\u05e4\u05e7\u05d9\u05d3 \u05d1\u05e4\u05e8\u05d5\u05d9\u05e7\u05d8 \u05d1\u05dc\u05d1\u05d3 \u2014 \u05d0\u05d9\u05df \u05db\u05d0\u05df \u05e9\u05d5\u05dd \u05de\u05d9\u05d3\u05e2 \u05d0\u05d9\u05e9\u05d9. "
                 "/ Project role only \u2014 no private information on this page.", "",
                 f"**\u05d4\u05d5\u05d3\u05e2\u05d5\u05ea \u05d1-{tail} \u05d4\u05d0\u05d7\u05e8\u05d5\u05e0\u05d5\u05ea / messages in the last {tail}:** {len(items)}", ""]
        if len(sessions) > 1:
            lines += [f"**\u05de\u05d6\u05d4\u05d9 \u05e1\u05e9\u05df / session identities ({len(sessions)}):** "
                      + ", ".join(f"`{s}`" for s in sessions), ""]
        lines += ["## \u05de\u05d4 \u05d4\u05d5\u05d0 \u05e2\u05e9\u05d4 \u05dc\u05d0\u05d7\u05e8\u05d5\u05e0\u05d4 / Recent work", ""]
        for m in items[-10:]:
            who, text, at = _msg(m)
            lines.append(f"- `{m.get('_day','')} {at}` **{who}** \u2014 " + " ".join(text.split())[:300])
        fm = {
            "name": author,
            "section": "people-of-the-project",
            "kind": "automated-watchdog" if author in NOISE_AUTHORS else "agent",
            "sessions": str(len(sessions)),
            "messages": str(len(items)),
            "confidence": "measured",
            "privacy": "project-role-only",
            "lang": "he+en",
            "sources": ["D:/CLAUDE/RAMCHAT/ramchat_session.json"],
        }
        log.append(f"  {B.write_page(pid, fm, chr(10).join(lines), dry_run=dry_run):9} {pid}")

    # today
    day = B.today()
    items = by_day.get(day, [])
    lines = [BANNER, f"# \u05d4\u05d9\u05d5\u05dd \u2014 {day} / Today \u2014 {day}", "",
             f"**{len(items)} \u05d4\u05d5\u05d3\u05e2\u05d5\u05ea \u05d1\u05de\u05d5\u05e2\u05e6\u05d4 \u05d4\u05d9\u05d5\u05dd / council messages today.**", "",
             "\u05d4\u05d3\u05e3 \u05d4\u05d6\u05d4 \u05e0\u05db\u05ea\u05d1 \u05de\u05d7\u05d3\u05e9 \u05d1\u05db\u05dc \u05d4\u05e8\u05e6\u05d4 \u05e9\u05dc \u05d4\u05de\u05ea\u05d7\u05d6\u05e7. "
             "/ Rewritten on every maintainer run.", ""]
    for m in [x for x in items if _msg(x)[0] not in NOISE_AUTHORS][-25:]:
        who, text, at = _msg(m)
        lines.append(f"- `{at}` **{who}** \u2014 " + " ".join(text.split())[:260])
    lines += ["", f"\u05e8\u05d0\u05d4 \u05d2\u05dd / see also: [decisions/ramchat-{day}](decisions/ramchat-{day}.md)"]
    fm = {"name": "today", "section": "decisions", "date": day, "confidence": "measured",
          "lang": "he+en", "sources": ["D:/CLAUDE/RAMCHAT/ramchat_session.json"]}
    log.append(f"  {B.write_page('today', fm, chr(10).join(lines), dry_run=dry_run):9} today")
    return log


# --------------------------------------------------------------------------
# source 4 — the measured fleet inventory (devices/ + models/)
# --------------------------------------------------------------------------


def ingest_fleet(dry_run: bool) -> list[str]:
    if not FLEET_INVENTORY.exists():
        return [f"SKIP fleet: {FLEET_INVENTORY} missing"]
    inv = json.loads(FLEET_INVENTORY.read_text(encoding="utf-8"))
    log = []
    measured = inv.get("measured_at", "")
    for name, h in inv.get("hosts", {}).items():
        pid = f"devices/{B.slug(name)}"
        doors = [f"- `{k}` \u2014 {v.get('url','')} ({v.get('purpose','')})"
                 for k, v in inv.get("doors", {}).items() if v.get("host") == name]
        lines = [BANNER, f"# {name} \u2014 {h.get('role','')}", "",
                 "\u05db\u05dc \u05d4\u05db\u05ea\u05d5\u05d1\u05d5\u05ea \u05db\u05d0\u05df \u05e0\u05de\u05d3\u05d3\u05d5, \u05dc\u05d0 \u05e0\u05d6\u05db\u05e8\u05d5. \u05db\u05ea\u05d5\u05d1\u05d5\u05ea LAN \u05de\u05e9\u05ea\u05e0\u05d5\u05ea \u05d1\u05db\u05dc \u05d0\u05ea\u05d7\u05d5\u05dc \u05e8\u05d0\u05d5\u05d8\u05e8 \u2014 "
                 "\u05d4\u05e2\u05d3\u05e3 tailnet. / Measured, not remembered. LAN drifts with every router reboot \u2014 prefer tailnet.", "",
                 "| \u05e9\u05d3\u05d4 / field | \u05e2\u05e8\u05da / value |", "|---|---|"]
        for k in ("os", "os_hostname", "lan_ip", "tailnet_ip", "magicdns", "ssh",
                  "fabric_ips", "tailnet_online", "reachable", "measured_at"):
            if h.get(k) not in (None, "", []):
                lines.append(f"| {k} | `{h[k]}` |")
        if h.get("note"):
            lines += ["", f"**\u05d4\u05e2\u05e8\u05d4 / note:** {h['note']}"]
        if doors:
            lines += ["", "## \u05d3\u05dc\u05ea\u05d5\u05ea / Doors", ""] + doors
        fm = {"name": name, "section": "devices", "role": h.get("role", ""),
              "confidence": "measured", "measured_at": measured, "lang": "he+en",
              "sources": [f"D:/CLAUDE/fleet_inventory.json (measured {measured} by {inv.get('measured_by','')})"]}
        log.append(f"  {B.write_page(pid, fm, chr(10).join(lines), dry_run=dry_run):9} {pid}")

    # models/ — what brain2 itself can actually reach
    probe = B.model_alive()
    lines = [BANNER, "# gpt-oss-120b \u2014 \u05d4\u05de\u05d5\u05d7 \u05d4\u05d6\u05d5\u05dc \u05e9\u05dc \u05d4\u05e6\u05d9 / the fleet's cheap brain", "",
             "\u05d4\u05de\u05d5\u05d3\u05dc \u05e9\u05de\u05ea\u05d7\u05d6\u05e7 \u05d4\u05d5\u05d5\u05d9\u05e7\u05d9 \u05de\u05e9\u05ea\u05de\u05e9 \u05d1\u05d5 \u05db\u05d1\u05e8\u05d9\u05e8\u05ea \u05de\u05d7\u05d3\u05dc. \u05d7\u05d9\u05e0\u05dd, \u05d1\u05dc\u05d9 \u05de\u05e4\u05ea\u05d7, \u05e2\u05dc eran2. "
             "/ The default brain of the maintainer. Free, no key, on eran2.", "",
             f"- **\u05d3\u05dc\u05ea / door:** `{B.DEFAULT_MODEL_BASE}` (OpenAI-compatible)",
             f"- **\u05e0\u05d1\u05d3\u05e7 / probed:** {B.now_iso()} \u2014 `{'reachable' if probe['ok'] else 'UNREACHABLE'}`",
             f"- **\u05de\u05d5\u05d3\u05dc\u05d9\u05dd / models:** `{probe.get('models') or probe.get('error')}`", "",
             "## \u05e6\u05dc\u05e7\u05d4 \u05e9\u05d7\u05d9\u05d9\u05d1\u05d9\u05dd \u05dc\u05d3\u05e2\u05ea / A scar you must know", "",
             "gpt-oss \u05de\u05d7\u05d6\u05d9\u05e8 \u05d0\u05ea \u05d4\u05d7\u05e9\u05d9\u05d1\u05d4 \u05e9\u05dc\u05d5 \u05d1-`reasoning_content`. \u05d0\u05dd \u05ea\u05e7\u05e6\u05d9\u05d1 \u05d4\u05d8\u05d5\u05e7\u05e0\u05d9\u05dd \u05e7\u05d8\u05df, "
             "`content` \u05d7\u05d5\u05d6\u05e8 **\u05e8\u05d9\u05e7** \u05d5\u05d4\u05e7\u05e8\u05d9\u05d0\u05d4 \u05e0\u05e8\u05d0\u05d9\u05ea \u05de\u05d5\u05e6\u05dc\u05d7\u05ea. \u05e0\u05de\u05d3\u05d3 2026-09-11.", "",
             "gpt-oss puts its thinking in `reasoning_content`. With a small token budget "
             "`content` comes back **empty** while the HTTP call still looks like a success. "
             "`brain2_lib.ask_model` raises `ModelEmpty` rather than writing an empty page.", ""]
    fm = {"name": "gpt-oss-120b", "section": "models", "confidence": "measured",
          "lang": "he+en", "sources": [f"live probe of {B.DEFAULT_MODEL_BASE}/models at {B.now_iso()}"]}
    log.append(f"  {B.write_page('models/gpt-oss-120b', fm, chr(10).join(lines), dry_run=dry_run):9} models/gpt-oss-120b")
    return log


# --------------------------------------------------------------------------
# proposals
# --------------------------------------------------------------------------

AGENT_BLOCK = "## \u05e2\u05d3\u05db\u05d5\u05e0\u05d9 \u05e1\u05d5\u05db\u05e0\u05d9\u05dd / Agent updates"


def apply_proposals(dry_run: bool) -> list[str]:
    log = []
    for item in B.open_proposals():
        page = item["page"]
        section = page.split("/")[0]
        if section in B.READ_ONLY_FOR_AGENTS:
            log.append(f"  REFUSED   {item['proposal_id']} -> {page}: laws/ is read-only for agents. "
                       "Only Iddo's word changes a law. Recorded, not applied.")
            if not dry_run:
                B.close_proposal(item["proposal_id"], "refused: laws/ is read-only for agents")
            continue
        existing = B.read_page(page)
        if existing is None:
            log.append(f"  REFUSED   {item['proposal_id']} -> {page}: no such page. "
                       "The maintainer creates pages from sources, not from proposals.")
            if not dry_run:
                B.close_proposal(item["proposal_id"], "refused: no such page")
            continue
        fm, body = existing
        if AGENT_BLOCK not in body:
            body = body.rstrip() + "\n\n" + AGENT_BLOCK + "\n"
        body = body.rstrip() + (
            f"\n\n### {B.today()} \u2014 {item['author']}\n\n{item['change'].strip()}\n"
        )
        if item.get("rationale"):
            body += f"\n*\u05e0\u05d9\u05de\u05d5\u05e7 / rationale:* {item['rationale'].strip()}\n"
        body += f"\n*(proposal `{item['proposal_id']}`)*\n"
        srcs = fm.get("sources") or []
        if isinstance(srcs, str):
            srcs = [srcs]
        tag = f"proposal {item['proposal_id']} by {item['author']}"
        if tag not in srcs:
            srcs.append(tag)
        fm["sources"] = srcs
        status = B.write_page(page, fm, body, dry_run=dry_run)
        if not dry_run:
            B.close_proposal(item["proposal_id"], status)
        log.append(f"  {status:9} {page}  <- proposal {item['proposal_id']} ({item['author']})")
    if not log:
        log.append("  (no open proposals)")
    return log


# --------------------------------------------------------------------------
# index
# --------------------------------------------------------------------------


def rebuild_index(dry_run: bool) -> list[str]:
    buckets: dict[str, list[tuple[str, dict]]] = {s: [] for s in B.SECTIONS}
    loose: list[tuple[str, dict]] = []
    for path in B.all_pages():
        pid = B.page_id_of(path)
        if pid == "index":
            continue
        fm, _ = B.parse_page(path.read_text(encoding="utf-8"))
        sec = pid.split("/")[0] if "/" in pid else ""
        (buckets[sec] if sec in buckets else loose).append((pid, fm))

    total = sum(len(v) for v in buckets.values()) + len(loose)
    he = {
        "projects": "\u05e4\u05e8\u05d5\u05d9\u05e7\u05d8\u05d9\u05dd", "scars": "\u05e6\u05dc\u05e7\u05d5\u05ea",
        "decisions": "\u05d4\u05d7\u05dc\u05d8\u05d5\u05ea", "laws": "\u05d7\u05d5\u05e7\u05d9\u05dd",
        "devices": "\u05de\u05db\u05e9\u05d9\u05e8\u05d9\u05dd", "models": "\u05de\u05d5\u05d3\u05dc\u05d9\u05dd",
        "people-of-the-project": "\u05d0\u05e0\u05e9\u05d9 \u05d4\u05e4\u05e8\u05d5\u05d9\u05e7\u05d8",
    }
    L = [BANNER,
         "# \u05d4\u05de\u05d5\u05d7 \u05d4\u05e9\u05e0\u05d9 \u2014 \u05d0\u05d9\u05e0\u05d3\u05e7\u05e1 / ALMA SECOND BRAIN \u2014 index", "",
         f"**{total} \u05d3\u05e4\u05d9\u05dd \u00b7 \u05e2\u05d5\u05d3\u05db\u05df {B.today()} \u00b7 \u05d3\u05dc\u05ea: http://127.0.0.1:8897** \u2014 "
         f"{total} pages, updated {B.today()}.", "",
         "\u05d6\u05d4 \u05dc\u05d0 \u05de\u05e0\u05d5\u05e2 \u05d7\u05d9\u05e4\u05d5\u05e9. \u05d6\u05d4 \u05d5\u05d9\u05e7\u05d9 \u05e9\u05d4\u05de\u05d5\u05d3\u05dc \u05de\u05ea\u05d7\u05d6\u05e7: \u05de\u05e7\u05d5\u05e8\u05d5\u05ea \u05e0\u05db\u05e0\u05e1\u05d9\u05dd, "
         "\u05d3\u05e4\u05d9\u05dd \u05e0\u05db\u05ea\u05d1\u05d9\u05dd \u05d5\u05de\u05ea\u05e2\u05d3\u05db\u05e0\u05d9\u05dd, \u05d5\u05db\u05dc \u05e1\u05d5\u05db\u05df \u05e7\u05d5\u05e8\u05d0 \u05d5\u05db\u05d5\u05ea\u05d1 \u05d3\u05e8\u05da \u05d3\u05dc\u05ea \u05d0\u05d7\u05ea.", "",
         "Not a search engine. A wiki the model MAINTAINS: raw sources in, pages written and kept "
         "current, every agent reading and writing through one door.", "",
         "**\u05d7\u05d5\u05e7\u05d9\u05dd / rules:** `laws/` \u05dc\u05e7\u05e8\u05d9\u05d0\u05d4 \u05d1\u05dc\u05d1\u05d3 \u05dc\u05e1\u05d5\u05db\u05e0\u05d9\u05dd \u00b7 `scars/` append-only \u00b7 "
         "\u05db\u05dc \u05d3\u05e3 \u05e0\u05d5\u05e9\u05d0 `sources:` \u05d5\u05ea\u05d0\u05e8\u05d9\u05da \u00b7 \u05e1\u05ea\u05d9\u05e8\u05d5\u05ea \u05e0\u05e8\u05e9\u05de\u05d5\u05ea, \u05dc\u05d0 \u05de\u05d5\u05db\u05e8\u05e2\u05d5\u05ea \u05d1\u05e9\u05e7\u05d8.", ""]

    for sec in B.SECTIONS:
        rows = sorted(buckets[sec], key=lambda r: r[0])
        if not rows:
            continue
        L += [f"## {he.get(sec, sec)} / {sec} ({len(rows)})", ""]
        for pid, fm in rows:
            name = fm.get("name", pid)
            extra = []
            if fm.get("entries"):
                extra.append(f"{fm['entries']} entries")
            if fm.get("confidence"):
                extra.append(str(fm["confidence"]))
            if fm.get("updated"):
                extra.append(str(fm["updated"]))
            L.append(f"- [{name}]({pid}.md)" + (f" \u2014 <sub>{' \u00b7 '.join(extra)}</sub>" if extra else ""))
        L.append("")
    if loose:
        L += ["## \u05d0\u05d7\u05e8 / other", ""] + [f"- [{fm.get('name', pid)}]({pid}.md)" for pid, fm in sorted(loose)] + [""]

    L += ["## \u05de\u05d4 \u05d6\u05d4 \u05dc\u05d0 / What this is NOT", "",
          "- \u05dc\u05d0 \u05d7\u05d9\u05e4\u05d5\u05e9 \u05d1\u05ea\u05de\u05dc\u05d9\u05dc\u05d9 \u05e9\u05d9\u05d7\u05d5\u05ea \u2014 \u05dc\u05d6\u05d4 \u05d9\u05e9 alma-recall :8794. "
          "/ Not transcript search \u2014 that is alma-recall :8794.",
          "- \u05dc\u05d0 \u05d4\u05d6\u05d9\u05db\u05e8\u05d5\u05df \u05d4\u05e4\u05e8\u05d8\u05d9 \u05e9\u05dc \u05e7\u05dc\u05d5\u05d3 \u2014 \u05d4\u05d5\u05d0 \u05e0\u05e9\u05d0\u05e8 \u05e4\u05e8\u05d8\u05d9; \u05e8\u05e7 \u05e2\u05d5\u05d1\u05d3\u05d5\u05ea \u05dc\u05d0-\u05e4\u05e8\u05d8\u05d9\u05d5\u05ea \u05de\u05de\u05d5\u05e8\u05d0\u05d5\u05ea \u05dc\u05db\u05d0\u05df. "
          "/ Not Claude's private memory dir \u2014 that stays private; only its non-private facts are mirrored.",
          "- \u05dc\u05d0 \u05de\u05e7\u05d5\u05dd \u05dc\u05e7\u05d5\u05dc \u05e9\u05dc\u05d5, \u05dc\u05de\u05d3\u05d9\u05d4 \u05de\u05e9\u05e4\u05d7\u05ea\u05d9\u05ea \u05d0\u05d5 \u05dc\u05e1\u05d5\u05d3\u05d5\u05ea. "
          "/ Never his voice, family media, or secrets.", "",
          f"<sub>\u05e0\u05d1\u05e0\u05d4 \u05e2\u05dc \u05d9\u05d3\u05d9 `brain2_maintain.py` \u00b7 {B.now_iso()}</sub>"]

    fm = {"name": "index", "section": "index", "pages": str(total), "confidence": "measured",
          "lang": "he+en", "sources": ["generated from the wiki itself by brain2_maintain.py"]}
    status = B.write_page("index", fm, "\n".join(L), dry_run=dry_run)
    return [f"  {status:9} index  ({total} pages)"]


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description="brain2 maintainer")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--scars", action="store_true")
    ap.add_argument("--memory", action="store_true")
    ap.add_argument("--ramchat", action="store_true")
    ap.add_argument("--fleet", action="store_true")
    ap.add_argument("--apply-proposals", action="store_true")
    ap.add_argument("--index", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-model", action="store_true", help="deterministic only, no LLM call")
    ap.add_argument("--limit", type=int, default=0, help="cap memory pages this run")
    ap.add_argument("--no-commit", action="store_true")
    args = ap.parse_args()

    B.lower_priority()
    use_model = not args.no_model
    any_source = args.all or args.scars or args.memory or args.ramchat or args.fleet
    if not any_source and not args.apply_proposals and not args.index:
        args.all = any_source = True

    print(f"[brain2] {B.now_iso()}  wiki={B.WIKI}  model={'on' if use_model else 'off'}"
          f"{'  DRY-RUN' if args.dry_run else ''}")
    if use_model:
        probe = B.model_alive()
        print(f"[brain2] model door {probe['base']}: {'ok ' + str(probe.get('models')) if probe['ok'] else 'DOWN ' + probe.get('error', '')}")
        if not probe["ok"]:
            print("[brain2] the model is unreachable. Falling back to --no-model "
                  "(deterministic pages) rather than writing empty ones.")
            use_model = False

    out: list[str] = []
    if args.all or args.scars:
        print("[brain2] source 1/4: eran-coder-pack/10-FAILURES.md -> scars/")
        out += ingest_scars(use_model, args.dry_run)
        for line in out[-10:]:
            print(line)
    if args.all or args.memory:
        print("[brain2] source 2/4: memory MEMORY.md -> projects/ + laws/")
        got = ingest_memory(use_model, args.dry_run, args.limit or None)
        out += got
        for line in got:
            print(line)
    if args.all or args.ramchat:
        print("[brain2] source 3/4: RAMCHAT -> decisions/ + people-of-the-project/ + today")
        got = ingest_ramchat(use_model, args.dry_run)
        out += got
        for line in got:
            print(line)
    if args.all or args.fleet:
        print("[brain2] source 4/4: fleet_inventory.json -> devices/ + models/")
        got = ingest_fleet(args.dry_run)
        out += got
        for line in got:
            print(line)
    if args.apply_proposals:
        print("[brain2] draining the proposal queue")
        got = apply_proposals(args.dry_run)
        out += got
        for line in got:
            print(line)

    print("[brain2] rebuilding index")
    got = rebuild_index(args.dry_run)
    out += got
    for line in got:
        print(line)

    if args.dry_run:
        print("[brain2] DRY-RUN: nothing written, nothing committed.")
        return 0
    if args.no_commit:
        print("[brain2] --no-commit: files written, not committed.")
        return 0

    created = sum(1 for line in out if line.strip().startswith("created"))
    updated = sum(1 for line in out if line.strip().startswith("updated"))
    res = B.git_commit(f"brain2: maintainer run {B.now_iso()} (+{created} new, ~{updated} updated)")
    print(f"[brain2] git: {json.dumps(res, ensure_ascii=False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
