#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""KOF (קוף) -- ultra vibe-coding ping-pong machine.

Iddo's earliest Claude days: it gave him something to run, he
copy-pasted the error back, repeat until done. This app IS the
monkey: it rallies with a fleet brain automatically, runs each
shot, feeds the output back, until DONE. TRUE YOLO: every step
auto-approves on a 3-2-1 countdown -- the Stop button is the
only brake. One hardcoded never-run list (disk killers) pauses
the rally instead; everything else goes.

Backends (fleet, no keys): router :8010, gpt-oss :8000, ollama.
GUI: tkinter (stdlib). Single file.

Run:   python D:\\CLAUDE\\kof\\kof.py
Prove: python D:\\CLAUDE\\kof\\kof.py --selftest
"""
import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
import urllib.request

APP_DIR = os.path.dirname(os.path.abspath(__file__))
RALLY_LOG = os.path.join(APP_DIR, "rally.jsonl")

BACKENDS = {
    "window": (None, None),
    "router": ("http://<tailnet-ip>:8010/v1/chat/completions",
               "maverick"),
    "gptoss": ("http://<tailnet-ip>:8000/v1/chat/completions",
               "gpt-oss-120b"),
}
INBOX = os.path.join(APP_DIR, "inbox")
OUTBOX = os.path.join(APP_DIR, "outbox")
for _d in (INBOX, OUTBOX):
    os.makedirs(_d, exist_ok=True)
DEFAULT_ROUNDS = 12
COUNTDOWN_S = 3

NEVER = ("format ", "mkfs", "rm -rf /", "rd /s /q c:",
         ":(){:|:&};:", "diskpart", "del /f /s /q c:\\windows")

# ----------------------------------------------------------------------------
# Rally engine (no GUI imports -- selftestable)
# ----------------------------------------------------------------------------
SYSTEM = ("You are the coder in a ping-pong loop. Token budget is "
          "tight: BATCH aggressively -- put up to 5 independent shell "
          "commands in ONE reply, one per line. Reply with:\n"
          "RUN:<shell command>  (repeat the RUN line per command, "
          "windows cmd)\n"
          "ASK:<question>       (you need the human)\n"
          "DONE:<summary>       (goal achieved)\n"
          "One reply per round -- batch, don't dribble.")


def kinfer(history, backend="router", timeout=180):
    url, model = BACKENDS[backend]
    payload = {"model": model, "messages": history,
               "max_tokens": 800, "temperature": 0.3}
    if backend == "gptoss":
        payload["chat_template_kwargs"] = {"reasoning_effort": "low"}
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read().decode("utf-8"))
    return d["choices"][0]["message"]["content"] or ""


def parse_step(text):
    """One reply may hold a BATCH of RUN lines. Returns (kind, payload):
    kind RUN -> payload is the list of commands (max 5)."""
    runs = []
    for line in text.strip().splitlines():
        m = re.match(r"^\s*RUN\s*:\s*(.+?)\s*$", line)
        if m:
            runs.append(m.group(1))
    if runs:
        return ("RUN", runs[:5])
    m = re.search(r"^\s*(ASK|DONE)\s*:\s*(.*)\s*$",
                  text.strip(), re.S)
    if not m:
        return ("ASK", "no RUN/ASK/DONE verdict -- clarify: " + text[:200])
    return (m.group(1), m.group(2).strip())


def is_forbidden(cmd):
    c = cmd.lower()
    return any(n in c for n in NEVER)


def run_step(cmd, timeout=120):
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True,
                           text=True, timeout=timeout,
                           errors="replace")
        out = (p.stdout or "") + (p.stderr or "")
        return p.returncode, out[-4000:] or "(no output)"
    except subprocess.TimeoutExpired:
        return 124, "(timed out after %ds)" % timeout
    except Exception as e:
        return 127, "(launch failed: %s)" % e

def rally(goal, backend="router", max_rounds=DEFAULT_ROUNDS,
          on_event=None, stop=None, infer=None, runner=None,
          human=None):
    """The ping-pong loop. on_event(dict) gets every beat.
    human(question)->answer plugs a person (Muse) in as the
    final brain: on ASK the loop waits for the human answer
    and rallies on instead of stopping."""
    infer = infer or (lambda h: kinfer(h, backend))
    runner = runner or run_step
    hist = [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": "GOAL: " + goal}]
    log = []

    def emit(ev):
        log.append(ev)
        with open(RALLY_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
        if on_event:
            on_event(ev)

    for rnd in range(1, max_rounds + 1):
        if stop and stop():
            emit({"t": "stop", "round": rnd})
            return log
        try:
            text = infer(hist)
        except Exception as e:
            emit({"t": "brain_error", "round": rnd,
                  "error": str(e)[:200]})
            return log
        kind, body = parse_step(text)
        preview = (" | ".join(body) if isinstance(body, list)
                   else body)[:500]
        emit({"t": "brain", "round": rnd, "kind": kind, "text": preview})
        hist.append({"role": "assistant", "content": text})
        if kind == "DONE":
            emit({"t": "done", "round": rnd, "summary": body[:500]})
            return log
        if kind == "ASK":
            emit({"t": "ask", "round": rnd, "question": body[:2000]})
            if human is not None:
                ans = human(body[:2000], hist)
                if ans is None:
                    return log
                emit({"t": "human", "round": rnd,
                      "answer": ans[:2000]})
                hist.append({"role": "user", "content":
                             "HUMAN (Muse) SAYS:\n" + ans})
                continue
            return log
        cmds = [c for c in body if not is_forbidden(c)]
        bad = [c for c in body if is_forbidden(c)]
        for c in bad:
            emit({"t": "forbidden", "round": rnd, "cmd": c[:200]})
        if not cmds:
            hist.append({"role": "user",
                         "content": "REFUSED: forbidden command(s). "
                                    "Propose safe alternatives."})
            continue
        label = ("+%d more" % (len(cmds) - 1)) if len(cmds) > 1 else ""
        for n in range(COUNTDOWN_S, 0, -1):
            emit({"t": "approve", "round": rnd, "n": n,
                  "cmd": (cmds[0][:160] + " " + label).strip()})
            time.sleep(1)
            if stop and stop():
                emit({"t": "stop", "round": rnd})
                return log
        outs = []
        worst = 0
        for c in cmds:
            emit({"t": "run", "round": rnd, "cmd": c[:300]})
            rc, out = runner(c)
            worst = max(worst, rc)
            emit({"t": "output", "round": rnd, "rc": rc,
                  "out": out[-2000:]})
            outs.append("### %s\nrc=%d\n%s" % (c[:200], rc, out[-1500:]))
        hist.append({"role": "user", "content":
                     "ROUND %d batch=%d worst_rc=%d OUTPUT:\n%s"
                     % (rnd, len(cmds), worst, "\n".join(outs)[-3000:])})
    emit({"t": "rounds_out", "rounds": max_rounds})
    return log

# ----------------------------------------------------------------------------
# GUI (tkinter). Big Start, bigger Stop, rally feed.
# ----------------------------------------------------------------------------
def launch_gui():
    import tkinter as tk
    from tkinter import scrolledtext
    stop_flag = {"v": False}
    q = queue.Queue()

    root = tk.Tk()
    root.title("KOF · ping-pong")
    root.geometry("560x640")

    top = tk.Frame(root)
    top.pack(fill="x", padx=10, pady=8)
    tk.Label(top, text="GOAL:", font=("Segoe UI", 11, "bold")).pack(
        anchor="w")
    goal = tk.Entry(top, font=("Segoe UI", 12))
    goal.pack(fill="x", pady=4)
    goal.insert(0, "prove python works: print version and date")

    row = tk.Frame(root)
    row.pack(fill="x", padx=10)
    backend = tk.StringVar(value="gptoss")
    tk.OptionMenu(row, backend, *BACKENDS.keys()).pack(side="left")
    rnds = tk.StringVar(value=str(DEFAULT_ROUNDS))
    tk.Entry(row, textvariable=rnds, width=4,
             font=("Segoe UI", 12)).pack(side="left", padx=6)
    tk.Label(row, text="rounds").pack(side="left")

    btns = tk.Frame(root)
    btns.pack(fill="x", padx=10, pady=8)
    start_b = tk.Button(btns, text="▶ START RALLY",
                        font=("Segoe UI", 14, "bold"),
                        bg="#2f9e44", fg="white", height=2)
    start_b.pack(side="left", expand=True, fill="x", padx=(0, 5))
    stop_b = tk.Button(btns, text="■ STOP",
                       font=("Segoe UI", 14, "bold"),
                       bg="#c94c4c", fg="white", height=2,
                       command=lambda: stop_flag.update(v=True))
    stop_b.pack(side="left", expand=True, fill="x", padx=(5, 0))

    feed = scrolledtext.ScrolledText(root, font=("Consolas", 10),
                                     state="disabled", height=24)
    feed.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    def say(s):
        feed.configure(state="normal")
        feed.insert("end", s + "\n")
        feed.see("end")
        feed.configure(state="disabled")

    def pump():
        while True:
            try:
                ev = q.get_nowait()
            except queue.Empty:
                break
            t = ev.get("t")
            if t == "brain":
                say("🧠 [%d] %s: %s" % (
                    ev["round"], ev["kind"], ev["text"][:160]))
            elif t == "approve":
                say("  %d… %s" % (ev["n"], ev["cmd"][:100]))
            elif t == "run":
                say("▶ RUN: %s" % ev["cmd"][:160])
            elif t == "output":
                say("  rc=%s :: %s" % (
                    ev["rc"], ev["out"][-300:].replace("\n", " | ")))
            elif t == "done":
                say("✅ DONE: %s" % ev["summary"][:200])
            elif t in ("ask", "stop", "forbidden", "rounds_out",
                       "brain_error", "human"):
                say("■ %s: %s" % (
                    t, ev.get("question") or ev.get("cmd") or
                    ev.get("error") or ev.get("summary") or
                    ev.get("answer", "")[:160]))
        root.after(300, pump)

    def go():
        g = goal.get().strip()
        if not g:
            return
        stop_flag["v"] = False
        say("== rally: %s" % g)
        human = make_human(root, goal.get, say,
                           lambda: stop_flag["v"])
        threading.Thread(
            target=rally,
            kwargs={"goal": g, "backend": backend.get(),
                    "max_rounds": int(rnds.get() or DEFAULT_ROUNDS),
                    "on_event": q.put,
                    "stop": lambda: stop_flag["v"],
                    "human": human},
            daemon=True).start()

    start_b.configure(command=go)
    root.after(300, pump)
    root.mainloop()

# ----------------------------------------------------------------------------
# Selftest: full rally against a fake brain, real runner, no GUI, no fleet.
# ----------------------------------------------------------------------------
def selftest():
    script = [
        "RUN:echo hello-kof",
        "RUN:echo second-shot",
        "DONE:printed twice, goal met",
    ]
    calls = {"n": 0}

    def fake_infer(hist):
        calls["n"] += 1
        return script[min(calls["n"] - 1, len(script) - 1)]

    seen = []

    def fast_runner(cmd):
        rc, out = run_step(cmd, timeout=30)
        return rc, out

    import time as _t
    global COUNTDOWN_S
    real_cd = COUNTDOWN_S
    COUNTDOWN_S = 0
    # zero countdown: patch sleep
    orig_sleep = _t.sleep
    _t.sleep = lambda s: None
    try:
        log = rally("say hello twice", max_rounds=6,
                    on_event=seen.append, infer=fake_infer,
                    runner=fast_runner)
    finally:
        _t.sleep = orig_sleep
        COUNTDOWN_S = real_cd
    kinds = [e["t"] for e in log]
    assert "done" in kinds, kinds
    outs = [e for e in log if e["t"] == "output"]
    assert len(outs) == 2 and all(e["rc"] == 0 for e in outs), outs
    assert "hello-kof" in outs[0]["out"], outs[0]
    # forbidden path
    assert is_forbidden("format c: /q") and not is_forbidden("echo hi")
    assert parse_step("RUN:echo x")[0] == "RUN"
    assert parse_step("DONE:fin")[0] == "DONE"
    assert parse_step("blah")[0] == "ASK"
    # single-use-ish: rounds_out when brain never finishes
    log2 = rally("x", max_rounds=1,
                 infer=lambda h: "RUN:echo zzz-never-done",
                 runner=fast_runner)
    assert log2[-1]["t"] == "rounds_out", log2[-1]
    # human plug: ASK -> human answers -> rally continues -> DONE
    script3 = ["ASK:what is the magic word?",
               "RUN:echo magic-handled",
               "DONE:human guided, done"]
    c3 = {"n": 0}

    def fake3(h):
        c3["n"] += 1
        return script3[min(c3["n"] - 1, len(script3) - 1)]

    got_q = {}
    log3 = rally("human test", max_rounds=5,
                 on_event=lambda e: None, infer=fake3,
                 runner=fast_runner,
                 human=lambda q, h: got_q.setdefault("q", q)
                 or "the magic word is DONE, carry on")
    ts = [e["t"] for e in log3]
    assert "ask" in ts and "human" in ts and log3[-1]["t"] == "done", ts
    assert "magic word" in got_q["q"], got_q
    p = build_prompt("g", "q?", [{"role": "user",
                                  "content": "ROUND 1 rc=0 OUTPUT:\nhi"}])
    assert "GOAL: g" in p and "hi" in p, p
    # batch: one reply, three shots, one inference
    inf = {"n": 0}

    def fake_batch(h):
        inf["n"] += 1
        if inf["n"] == 1:
            return "RUN:echo batch-one\nRUN:echo batch-two\nRUN:echo batch-three"
        return "DONE:batched, done"

    log4 = rally("batch test", max_rounds=4,
                 on_event=lambda e: None, infer=fake_batch,
                 runner=fast_runner)
    runs4 = [e for e in log4 if e["t"] == "run"]
    assert inf["n"] == 2 and len(runs4) == 3 and \
        log4[-1]["t"] == "done", (inf["n"], len(runs4), log4[-1])
    assert parse_step("RUN:echo a\nRUN:echo b")[1] == ["echo a", "echo b"]
    print("SELFTEST-OK turns=%d outputs=%d human=ok batch=ok"
          % (len(log), len(outs)))


def main():
    if "--selftest" in sys.argv:
        return selftest()
    return launch_gui()

# ----------------------------------------------------------------------------
# Human-in-the-loop: the monkey phones Muse. Copy prompt -> any window
# (this chat, Claude, anywhere) -> paste the answer back -> rally on.
# ----------------------------------------------------------------------------
def build_prompt(goal, question, hist):
    parts = ["KOF rally needs its human.",
             "GOAL: " + goal,
             "MONKEY ASKS: " + question,
             "LAST OUTPUTS:"]
    seen = 0
    for m in reversed(hist):
        if m.get("role") == "user" and m.get("content", "").startswith(
                "ROUND"):
            parts.append(m["content"][:600])
            seen += 1
            if seen >= 3:
                break
    parts.append("Answer with the next step (a command or guidance).")
    return "\n".join(parts)


def make_human(root, goal_fn, say, stop):
    import tkinter as tk

    def human(question, hist):
        box = {}
        done = threading.Event()

        def show():
            d = tk.Toplevel(root)
            d.title("KOF phones home")
            d.geometry("520x560")
            prompt = build_prompt(goal_fn(), question, hist)
            box["prompt"] = prompt
            tk.Label(d, text="MONKEY IS STUCK — paste this to Muse:",
                     font=("Segoe UI", 11, "bold")).pack(
                         anchor="w", padx=10, pady=(8, 0))
            q = tk.Text(d, height=12, font=("Consolas", 10))
            q.pack(fill="both", expand=True, padx=10, pady=6)
            q.insert("1.0", prompt)

            def copy():
                root.clipboard_clear()
                root.clipboard_append(prompt)
                say("copied — paste it to Muse, then drop the answer below")

            tk.Button(d, text="COPY PROMPT",
                      font=("Segoe UI", 12, "bold"),
                      bg="#2f9e44", fg="white",
                      command=copy).pack(fill="x", padx=10)
            tk.Label(d, text="MUSE ANSWERS:",
                     font=("Segoe UI", 11, "bold")).pack(
                         anchor="w", padx=10, pady=(8, 0))
            a = tk.Text(d, height=8, font=("Consolas", 10))
            a.pack(fill="both", expand=True, padx=10, pady=6)

            def submit():
                box["answer"] = a.get("1.0", "end").strip() or None
                d.destroy()
                done.set()

            def skip():
                box["answer"] = None
                d.destroy()
                done.set()

            r = tk.Frame(d)
            r.pack(fill="x", padx=10, pady=(0, 10))
            tk.Button(r, text="RALLY ON",
                      font=("Segoe UI", 12, "bold"),
                      bg="#c8792f", fg="white",
                      command=submit).pack(
                          side="left", expand=True, fill="x")
            tk.Button(r, text="STOP", command=skip).pack(
                side="left", padx=(6, 0))

        root.after(0, show)
        while not done.is_set():
            if stop():
                return None
            time.sleep(0.2)
        return box.get("answer")

    return human


if __name__ == "__main__":
    main()
