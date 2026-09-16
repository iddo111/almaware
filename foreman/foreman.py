"""FOREMAN — הנוגש. The 4 DGX models work 24/7 on real projects.

Iddo's order (2026-08-18 18:52): "אני רוצה ש-4 מודלים שרצים על 4 DGX יעבדו
24/7 על פרויקטים — לא חסר... תעביד אותם כמו נוגש מצרי."

The loop (one CYCLE, run by a scheduled task every 30 min, forever):
  for each model lane (qwen/glm/gpt-oss/nemotron):
    1. pick its next OPEN order from backlog.json
    2. dispatch through the 4D router (:8010), king-style module-only prompt
    3. validate: code orders run their unittest file; doc orders must not be
       truncated (finish_reason, mid-word ending), must cover every item they
       were ordered to cover, and must land inside an allowed root
    4. ACCEPT -> atomic write into the target + log; REJECT -> requeue with
       the reason (2 strikes -> status=escalate, lands in KING-REVIEW.md)
  post one cycle summary to RAMCHAT.

Laws: stdlib only; never touches live services; never restarts anything;
output lands ONLY inside ALLOWED_ROOTS (enforced by contained(), not by this
sentence); every event in log.jsonl.

2026-09-16 REPAIR. For 28 days this file reported success while shipping
half a book. Audit findings and what each fix answers:
  * 3 of 4 hard-coded lane names were 404 on the live router -> lanes are now
    read from GET /v1/models every cycle (live_lanes).
  * a router error was `except: continue` -- no strike, no escalation, not in
    the summary, so a dead lane meant a silent infinite retry -> it is now a
    normal failure and counts toward escalation.
  * the doc gate was len(text) + two substring checks. Of the 100 pages it
    accepted, 71 ended mid-word and 59 covered fewer ideas than ordered.
    finish_reason, which proves truncation, was in the reply and discarded.
    -> validate_doc now checks truncation, completeness and containment.
  * "output lands ONLY inside the target dir" was a comment -> contained().
  * 6000 max_tokens buys ~11,400 chars of Hebrew, against an order for ten
    full build pages -> IDEAS_PER_ORDER 10 -> 3, DOC_MAX_TOKENS 12000.
  * added halted(): Iddo's stop button, read before anything else.
Gates are demonstrated on decoys in test_gates.py -- an untested gate is not
a gate, and it is never tested against a living system.
"""
from __future__ import annotations

import datetime
import json
import pathlib
import re
import subprocess
import time
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent
BACKLOG = ROOT / "backlog.json"
LOG = ROOT / "log.jsonl"
REVIEW = ROOT / "KING-REVIEW.md"
ROUTER = "http://<lan-ip>:8010/v1/chat/completions"
PY = r"C:\Users\<user>\AppData\Local\Programs\Python\Python313\python.exe"
MODELS_URL = "http://<lan-ip>:8010/v1/models"
STATE = ROOT / "whip_state.json"

# 2026-08-18 list, kept ONLY as the label for "the router did not answer".
# On 2026-09-16 three of these four were 404 on the live router for 28 days:
# qwen3-coder-next-fp8 was retired, glm-4.7-flash and nemotron-3-super were
# renamed. Nothing noticed, because the router-error path was silent.
# One source of truth beats a fresher private copy -- ask the router.
LANES_FALLBACK = ["gpt-oss-120b"]

# Output may only ever land inside one of these. The docstring has claimed
# this since day one; until 2026-09-16 no code enforced it and a seeded
# "target" could write anywhere on the machine.
ALLOWED_ROOTS = [ROOT, pathlib.Path(r"D:\CLAUDE\keshev-4d")]

CODE_RE = re.compile(r"```(?:\w+)?\s*\n(.*?)```", re.S)
H2_RE = re.compile(r"^##\s+\S", re.M)
# A finished Hebrew/English page ends on punctuation or a closing fence.
ENDS_CLEAN_RE = re.compile(r"[.!?:;)\]\"'`\u05be\u05c3]\s*$|```\s*$")


def live_lanes() -> tuple[list[str], str]:
    """The lanes the router actually serves, right now.

    Returns (lanes, source). source is "router" or "fallback" so the caller
    can say which it used instead of pretending.
    """
    try:
        with urllib.request.urlopen(MODELS_URL, timeout=20) as r:
            ids = [m["id"] for m in json.load(r).get("data", []) if m.get("id")]
        if ids:
            return sorted(ids), "router"
        return LANES_FALLBACK, "fallback:empty-model-list"
    except Exception as e:  # noqa: BLE001
        return LANES_FALLBACK, "fallback:%s" % type(e).__name__


def halted() -> dict | None:
    """Iddo's stop button, read before anything else happens in a cycle."""
    try:
        st = json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - no file means running, which is the default
        return None
    return st if st.get("halt") else None


def contained(target: pathlib.Path) -> bool:
    """True only if target resolves inside an allowed root. Real gate, not a comment."""
    try:
        t = target.resolve()
    except Exception:  # noqa: BLE001
        return False
    for root in ALLOWED_ROOTS:
        try:
            if t.is_relative_to(root.resolve()):
                return True
        except Exception:  # noqa: BLE001
            continue
    return False


def log(evt: str, **kw) -> None:
    rec = {"ts": datetime.datetime.now().isoformat(timespec="seconds"),
           "evt": evt, **kw}
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def call(model: str, prompt: str, max_tokens: int = 6000) -> tuple[str, str]:
    body = json.dumps({"model": model,
                       "messages": [{"role": "user", "content": prompt}],
                       "max_tokens": max_tokens,
                       "temperature": 0.3}).encode()
    req = urllib.request.Request(ROUTER, data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        choice = json.load(r)["choices"][0]
        # finish_reason was always in the reply and was always thrown away.
        # "length" means the model was cut off mid-sentence at max_tokens --
        # the single fact that would have caught 69 truncated pages.
        return (choice["message"]["content"] or ""), (choice.get("finish_reason") or "")


def validate_code(order: dict, code: str) -> tuple[bool, str]:
    target = pathlib.Path(order["target"])
    if not contained(target):
        return False, ("BLOCKED: target %s is outside every allowed root %s"
                       % (target, [str(r) for r in ALLOWED_ROOTS]))
    target.parent.mkdir(parents=True, exist_ok=True)
    backup = target.read_text(encoding="utf-8") if target.exists() else None
    if backup is not None:
        # The in-memory restore is not enough: a kill or a power loss
        # mid-test leaves the model's broken code in a live project file.
        try:
            target.with_suffix(target.suffix + ".foreman-bak").write_text(
                backup, encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
    target.write_text(code, encoding="utf-8")
    try:
        proc = subprocess.run(
            [PY, "-m", "unittest", order["test_module"], "-q"],
            capture_output=True, text=True, timeout=300,
            cwd=order["project"],
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
        ok = proc.returncode == 0
        detail = (proc.stdout + proc.stderr)[-400:]
        if not ok and backup is not None:
            target.write_text(backup, encoding="utf-8")   # never leave broken
        elif not ok:
            target.unlink(missing_ok=True)
        return ok, detail
    except subprocess.TimeoutExpired:
        if backup is not None:
            target.write_text(backup, encoding="utf-8")
        return False, "tests timed out (300s)"


def validate_doc(order: dict, text: str, finish_reason: str = "") -> tuple[bool, str]:
    """The gate that used to be a rubber stamp.

    Until 2026-09-16 this was len(text) >= min_chars plus two substring
    searches. Measured against the 100 pages it had already accepted:
    69 ended mid-word (cut at max_tokens and passed anyway), 59 covered
    fewer ideas than they were ordered to cover, 24 had no headings at all,
    and the whole 28-day log contained exactly one rejection. It reported
    "1000 ideas done" while about half of them were never written.

    Each check below exists because it would have caught a real failure
    that shipped.
    """
    # 1. Truncation, stated by the model itself. Catches the 69.
    if finish_reason == "length":
        return False, ("truncated: the model hit max_tokens (finish_reason=length). "
                       "Split the order or raise max_tokens -- do not accept a cut page.")

    # 2. Truncation the model did not admit to: a page ending mid-word.
    tail = text.rstrip()
    if tail and not ENDS_CLEAN_RE.search(tail):
        return False, "ends mid-sentence (last 40 chars: %r)" % tail[-40:]

    # 3. Length, as before.
    if len(text) < order.get("min_chars", 800):
        return False, f"too short: {len(text)}"

    # 4. Required content, as before.
    missing = [m for m in order.get("must_contain", []) if m not in text]
    if missing:
        return False, f"missing required elements: {missing}"

    # 5. Structure: the order asked for one H2 per idea, so count them.
    #    Catches the 59 that silently covered fewer ideas than ordered.
    want = order.get("expect_sections")
    if want is None and order.get("idea_range"):
        lo, hi = order["idea_range"]
        want = hi - lo + 1
    if want:
        got = len(H2_RE.findall(text))
        if got < want:
            return False, (f"covered {got} of {want} ordered items "
                           f"(counted '## ' headings) -- the rest were silently dropped")

    # 6. Containment. The docstring promised this from day one; now it is code.
    target = pathlib.Path(order["target"])
    if not contained(target):
        return False, ("BLOCKED: target %s is outside every allowed root %s"
                       % (target, [str(r) for r in ALLOWED_ROOTS]))

    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(target)            # atomic, per the AUTOSAVE law
    sec = len(H2_RE.findall(text))
    return True, f"{len(text)} chars, {sec} sections, finish_reason={finish_reason or 'n/a'}"


BOOKDATA = ROOT / "bookdata"
# Three ideas per order, not ten: see the note in autoseed().
IDEAS_PER_ORDER = 3
DOC_MAX_TOKENS = 12000          # headroom, so finish_reason is "stop" not "length"
BOOK_NOTE = ("Write in Hebrew. For EACH idea give: מה צריך (materials, cheap), "
             "איך עושים (numbered concrete steps), זמן ועלות, טיפ של אלוף, "
             "בטיחות where relevant. Markdown, one H2 per idea. Min 4000 chars total.")


def _book_ideas() -> list[tuple[int, str]]:
    """All 1000 ideas, numbered, in book order."""
    import glob
    out, n = [], 1
    for f in sorted(glob.glob(str(BOOKDATA / "ch*.json"))):
        data = json.loads(pathlib.Path(f).read_text(encoding="utf-8"))
        for ch in data["chapters"]:
            for idea in ch["ideas"]:
                out.append((n, idea))
                n += 1
    return out


def autoseed(backlog: dict, lane: str) -> dict | None:
    """The encyclopedia writes itself: when a lane is idle, order build pages
    for the next 10 ideas nobody has claimed yet (Iddo 19:10: 'תעשה בילד
    ממש מכל אחד - זה יהיה אנציקלופדיה')."""
    claimed = set()
    for o in backlog["orders"]:
        rng = o.get("idea_range")
        if rng:
            claimed.update(range(rng[0], rng[1] + 1))
    ideas = _book_ideas()
    start = None
    for num, _ in ideas:
        if num not in claimed:
            start = num
            break
    if start is None:
        return None                      # all 1000 claimed - the book is full
    # Was 10 ideas per order. Measured 2026-09-16: max_tokens=6000 buys about
    # 11,400 chars of Hebrew, so ten "full build pages" got ~1,140 chars each
    # and 71 of 100 orders were cut off mid-word. The gate now rejects that,
    # which would have meant an infinite reject loop instead of a fix -- so
    # the order itself has to be achievable. Three ideas fits with headroom.
    batch = [(n, t) for n, t in ideas if start <= n < start + IDEAS_PER_ORDER]
    listing = "\n".join(f"{n}. {t}" for n, t in batch)
    oid = f"E{start:04d}"
    order = {
        "id": oid, "lane": lane, "status": "open", "kind": "doc",
        "title": f"Encyclopedia build-pages: ideas {start}-{batch[-1][0]}",
        "project": str(ROOT), "idea_range": [start, batch[-1][0]],
        "target": str(ROOT / "out" / f"encyclopedia-{start:04d}-{batch[-1][0]:04d}.md"),
        "min_chars": 1200 * len(batch), "must_contain": ["מה צריך", "איך עושים"],
        "max_tokens": DOC_MAX_TOKENS, "expect_sections": len(batch),
        "prompt": ("Expand each of these ideas from Iddo's 1000-idea book into a "
                   "FULL build page (this is the cool-as-hell encyclopedia):\n"
                   + listing + "\n\n" + BOOK_NOTE),
    }
    backlog["orders"].append(order)
    log("AUTOSEED", lane=lane, id=oid, range=order["idea_range"])
    return order


def run_cycle() -> dict:
    # Iddo's stop button comes first, before the backlog is even read, so it
    # can never interrupt a write. Halted is a normal state, not an error.
    stop = halted()
    if stop:
        log("HALTED", by=stop.get("by", "?"), at=stop.get("at", "?"))
        return {"accepted": 0, "rejected": 0, "escalated": 0, "idle": 0,
                "halted": True, "by": stop.get("by", "?")}

    lanes, lane_src = live_lanes()
    if lane_src != "router":
        log("LANES_FALLBACK", source=lane_src, using=lanes)

    backlog = json.loads(BACKLOG.read_text(encoding="utf-8"))
    summary = {"accepted": 0, "rejected": 0, "escalated": 0, "idle": 0,
               "router_errors": 0, "lanes": len(lanes), "lane_source": lane_src}

    # An order parked on a lane the router no longer serves can never run.
    # It used to sit "open" forever, re-dispatched into a 404 every 30 min.
    for o in backlog["orders"]:
        if o["status"] == "open" and o["lane"] not in lanes:
            o["status"] = "escalate"
            o["last_reason"] = ("lane %r is not served by the router "
                                "(live lanes: %s)" % (o["lane"], ", ".join(lanes)))
            summary["escalated"] += 1
            log("LANE_GONE", id=o["id"], lane=o["lane"])

    for lane in lanes:
        order = next((o for o in backlog["orders"]
                      if o["lane"] == lane and o["status"] == "open"), None)
        if order is None:
            order = autoseed(backlog, lane)
        if order is None:
            summary["idle"] += 1
            log("LANE_IDLE", lane=lane)
            continue
        log("DISPATCH", lane=lane, id=order["id"], title=order["title"])
        try:
            reply, finish = call(lane, order["prompt"],
                                 max_tokens=order.get("max_tokens", 6000))
        except Exception as e:  # noqa: BLE001
            # This used to be a bare `continue`: no strike, no escalation, not
            # counted in the summary. A dead lane meant the same order was
            # re-dispatched into the same 404 every 30 minutes, forever, in
            # silence. A router error is now a failure like any other.
            detail = "ROUTER ERROR: %s: %s" % (type(e).__name__, str(e)[:200])
            log("ROUTER_ERROR", lane=lane, id=order["id"], err=detail[:200])
            summary["router_errors"] += 1
            ok, finish = False, "router-error"
            reply = ""
        else:
            if order["kind"] == "code":
                blocks = CODE_RE.findall(reply)
                if not blocks:
                    ok, detail = False, "no code block in reply"
                else:
                    ok, detail = validate_code(order, blocks[0])
            else:
                ok, detail = validate_doc(order, reply.strip(), finish)

        if ok:
            order["status"] = "done"
            order["done_at"] = datetime.datetime.now().isoformat(timespec="minutes")
            summary["accepted"] += 1
            log("ACCEPT", lane=lane, id=order["id"], detail=detail[:200])
        else:
            order["strikes"] = order.get("strikes", 0) + 1
            order["last_reason"] = detail[:300]
            summary["rejected"] += 1
            log("REJECT", lane=lane, id=order["id"], strike=order["strikes"],
                detail=detail[:200])
            if order["strikes"] >= 2:
                order["status"] = "escalate"
                summary["escalated"] += 1
                with open(REVIEW, "a", encoding="utf-8") as f:
                    f.write(f"\n## {order['id']} — {order['title']} "
                            f"(lane {lane}, {order['strikes']} strikes)\n"
                            f"Last reason: {detail[:300]}\n")
            else:
                order["prompt"] += (f"\n\nPREVIOUS ATTEMPT REJECTED: {detail[:300]}"
                                    "\nFix exactly that and resubmit in full.")
    BACKLOG.write_text(json.dumps(backlog, ensure_ascii=False, indent=1),
                       encoding="utf-8")
    log("CYCLE_DONE", **summary)
    return summary


SEEN = ROOT / "last_posted.json"
IDLE_HEARTBEAT_S = 86400        # an idle whip says so once a day, not 48 times


def post_ramchat(summary: dict) -> None:
    """Post the truth, and only when it changed.

    2026-08-30: this said "The four lanes keep working" 538 cycles in a row while all
    four lanes were idle and the backlog had been exhausted for a day. A bot that
    writes a comforting lie into the team's shared memory every 30 minutes is worse
    than a silent one — RAMCHAT is where the other agents look to know what is true.
    """
    orders = json.loads(BACKLOG.read_text(encoding="utf-8"))["orders"]
    open_n = sum(1 for o in orders if o["status"] == "open")
    done_n = sum(1 for o in orders if o["status"] == "done")
    esc = [o["id"] for o in orders if o["status"] == "escalate"]
    moved = summary["accepted"] + summary["rejected"] + summary["escalated"]

    if moved == 0 and open_n == 0:
        msg = (f"FOREMAN idle: nothing to dispatch. {done_n} done, "
               f"{len(esc)} escalated ({', '.join(esc) or '-'}), 0 open. "
               f"All {summary['idle']} lanes had no work — the backlog is exhausted, "
               f"so no lane is 'working'. Seed orders or leave it quiet.")
    else:
        msg = (f"FOREMAN cycle: +{summary['accepted']} accepted, "
               f"{summary['rejected']} rejected, {summary['escalated']} escalated, "
               f"{open_n} orders open, {done_n} done.")

    # Say it once. Repeat only if it changed, or once a day so silence != death.
    try:
        prev = json.loads(SEEN.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        prev = {}
    now = time.time()
    if prev.get("msg") == msg and (now - float(prev.get("ts") or 0)) < IDLE_HEARTBEAT_S:
        return
    try:
        SEEN.write_text(json.dumps({"msg": msg, "ts": now}), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

    try:
        subprocess.run(
            ["python", r"D:\CLAUDE\RAMCHAT\ramlink.py", "post",
             "foreman", msg],
            env={"PYTHONIOENCODING": "utf-8", "PATH": "C:\\Windows\\System32",
                 "SYSTEMROOT": "C:\\Windows"},
            capture_output=True, timeout=60, cwd=r"D:\CLAUDE\RAMCHAT",
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
    except Exception:  # noqa: BLE001 — RAMCHAT down never stops the whip
        pass


if __name__ == "__main__":
    s = run_cycle()
    post_ramchat(s)
    print(json.dumps(s))
    sys.exit(0)
