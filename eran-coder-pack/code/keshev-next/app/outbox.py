r"""outbox -- the words the typer could not deliver are HELD, retried, and if they
are finally lost, LOST OUT LOUD.

🪟 BROKEN WINDOWS LAW: test the REAL output, not a proxy.

THE FAILURE THIS IS FOR
-----------------------
`typer.type_string()` is one bulk SendInput into whatever window has the focus.
When that window sits above us -- a terminal opened from an Administrator shell,
say -- Windows UIPI discards every keystroke AND REPORTS SUCCESS. Since
2026-09-06 the typer at least refuses honestly instead of pretending, but the
sentence was then simply **dropped**: Iddo spoke, the decoder decoded, and the
words went nowhere with one line in a log he does not read.

That happened on 09-03 ("she types everywhere except the CLI") and again on
09-06. A refusal is not a verdict on the sentence; it is a verdict on the window
that happened to be in front at that instant. So the sentence waits here for a
window that can take it.

THE RULES, AND WHY EACH ONE
---------------------------
* retry every RETRY_EVERY_S seconds, for at most MAX_AGE_S seconds. Then log
  `[outbox] DROPPED` with the reason. **Never silently.** A queue that quietly
  forgets is worse than no queue -- it also destroys the evidence.
* deliver only into a window that would ACCEPT the keys (typer.refusal_for_window
  says no) and that is not a password manager. That is the same fence the live
  typer already obeys; the outbox does not get a weaker one.
* ONE sentence per tick, in the order he said them. A burst of held text dumped
  into a chat box at once is its own kind of damage.
* everything older than MAX_AGE_S at load time is dropped, loudly. After an
  engine restart, yesterday's sentence must never appear in today's window --
  that is the 2026-08-15 "typed the room into his chat" shape.
* the queue is on disk (`state\outbox.jsonl`) so a crash leaves evidence, not a
  mystery. The file holds only what is still PENDING; deliveries and drops are
  announced in trial.log, which now carries timestamps.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import uuid

RETRY_EVERY_S = float(os.environ.get("KESHEV_OUTBOX_RETRY_S", "2.0"))
MAX_AGE_S = float(os.environ.get("KESHEV_OUTBOX_MAX_AGE_S", "60.0"))
MAX_PENDING = 50          # a runaway queue is a bug, not a backlog


def _now():
    return time.time()


class Outbox:
    """Holds refused sentences and retries them on its own thread.

    typer_mod is injected so the tests can drive a fake one; in the engine it is
    the real `typer`, the same module that refused in the first place.
    """

    def __init__(self, path, typer_mod, log=None, retry_every_s=RETRY_EVERY_S,
                 max_age_s=MAX_AGE_S, autostart=True):
        self.path = path
        self.typer = typer_mod
        self.retry_every_s = float(retry_every_s)
        self.max_age_s = float(max_age_s)
        self._lock = threading.Lock()
        self._items = []
        self._stop = threading.Event()
        self._thread = None
        self._log = log or (lambda msg: print(msg, file=sys.stderr, flush=True))
        self._load()
        if autostart:
            self.start()

    # ------------------------------------------------------------- storage
    def _load(self):
        items = []
        try:
            with open(self.path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        items.append(json.loads(line))
                    except ValueError:
                        continue
        except OSError:
            items = []
        keep, stale = [], []
        for it in items:
            if _now() - float(it.get("at", 0)) > self.max_age_s:
                stale.append(it)
            else:
                keep.append(it)
        self._items = keep
        for it in stale:
            self._log("[outbox] DROPPED id=%s age=%.0fs reason=stale-across-restart "
                      "text=%s" % (it.get("id", "?"), _now() - float(it.get("at", 0)),
                                   ascii(it.get("text", ""))[:80]))
        if stale or keep:
            self._flush()
        if keep:
            self._log("[outbox] loaded %d pending sentence(s) from the last run" % len(keep))

    def _flush(self):
        """Rewrite the pending file atomically. Never raises into the caller."""
        try:
            tmp = self.path + ".tmp"
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as fh:
                for it in self._items:
                    fh.write(json.dumps(it, ensure_ascii=False) + "\n")
            os.replace(tmp, self.path)
        except OSError as exc:
            # 2026-09-05: os.replace on a file another process holds is Errno 22
            # on Windows and it silently killed the heartbeat 162 times. Say it.
            self._log("[outbox] could not write the queue (%s: %s) -- the pending "
                      "sentences are in memory only" % (type(exc).__name__, exc))

    # --------------------------------------------------------------- queue
    def submit(self, text, refusal=None, auto_enter=False):
        """Hold one sentence the typer refused. Returns its id, or '' if dropped."""
        if not text or not text.strip():
            return ""
        item = {
            "id": uuid.uuid4().hex[:8],
            "at": _now(),
            "text": text,
            "auto_enter": bool(auto_enter),
            "reason": getattr(refusal, "reason", "") or "refused",
            "from_proc": getattr(refusal, "proc", "") or "",
            "from_integrity": getattr(refusal, "integrity", "") or "",
            "from_title": (getattr(refusal, "title", "") or "")[:60],
            "tries": 0,
        }
        with self._lock:
            if len(self._items) >= MAX_PENDING:
                oldest = self._items.pop(0)
                self._log("[outbox] DROPPED id=%s reason=queue-full(%d) text=%s"
                          % (oldest.get("id", "?"), MAX_PENDING,
                             ascii(oldest.get("text", ""))[:80]))
            self._items.append(item)
            self._flush()
        self._log("[outbox] queued id=%s reason=%s blocked-by=%s/%s text=%s"
                  % (item["id"], item["reason"], item["from_proc"] or "?",
                     item["from_integrity"] or "?", ascii(text)[:80]))
        return item["id"]

    def pending(self):
        with self._lock:
            return len(self._items)

    def snapshot(self):
        with self._lock:
            return [dict(it) for it in self._items]

    # ---------------------------------------------------------------- work
    def _target_ok(self):
        """(ok, why) for the window that has the focus RIGHT NOW."""
        try:
            hwnd = self.typer.user32.GetForegroundWindow()
        except Exception as exc:
            return False, "no-foreground(%s)" % type(exc).__name__
        if not hwnd:
            return False, "no-foreground"
        try:
            if self.typer.is_password_manager_window():
                return False, "password-manager"
        except Exception:
            pass
        try:
            refusal = self.typer.refusal_for_window(hwnd)
        except Exception as exc:
            return False, "probe-failed(%s)" % type(exc).__name__
        if refusal is not None:
            return False, "%s/%s" % (refusal.proc or "?", refusal.integrity)
        return True, ""

    def tick(self):
        """One pass. Returns ('delivered'|'dropped'|'waiting'|'idle', detail)."""
        with self._lock:
            if not self._items:
                return "idle", ""
            item = self._items[0]
            age = _now() - float(item.get("at", 0))
            if age > self.max_age_s:
                self._items.pop(0)
                self._flush()
                ok, why = self._target_ok()
                self._log("[outbox] DROPPED id=%s age=%.0fs tries=%d reason=%s "
                          "last-target=%s text=%s"
                          % (item["id"], age, item.get("tries", 0),
                             item.get("reason", "?"), why or "ok",
                             ascii(item.get("text", ""))[:80]))
                return "dropped", item["id"]

        ok, why = self._target_ok()
        if not ok:
            with self._lock:
                if self._items and self._items[0]["id"] == item["id"]:
                    self._items[0]["tries"] = self._items[0].get("tries", 0) + 1
            return "waiting", why

        # The window will take it. Type through the REAL typer -- the outbox
        # never has its own way into the desktop.
        try:
            typed = self.typer.type_string(item["text"], auto_enter=item.get("auto_enter", False))
        except Exception as exc:
            self._log("[outbox] retry id=%s raised %s: %s" % (item["id"], type(exc).__name__, exc))
            return "waiting", "raised"
        if not typed:
            with self._lock:
                if self._items and self._items[0]["id"] == item["id"]:
                    self._items[0]["tries"] = self._items[0].get("tries", 0) + 1
            return "waiting", getattr(typed, "reason", "refused-again")
        with self._lock:
            if self._items and self._items[0]["id"] == item["id"]:
                self._items.pop(0)
                self._flush()
        self._log("[outbox] delivered id=%s after=%.0fs tries=%d text=%s"
                  % (item["id"], _now() - float(item["at"]), item.get("tries", 0),
                     ascii(item["text"])[:80]))
        return "delivered", item["id"]

    def _run(self):
        while not self._stop.wait(self.retry_every_s):
            try:
                while True:
                    state, _ = self.tick()
                    # keep draining only while things are actually leaving
                    if state not in ("dropped",):
                        break
            except Exception as exc:
                self._log("[outbox] worker error %s: %s" % (type(exc).__name__, exc))

    def start(self):
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="keshev-outbox", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()


# --------------------------------------------------------------- selftest
if __name__ == "__main__":
    # python app/outbox.py --selftest : a FAKE typer that refuses, then accepts.
    # No window is touched, nothing is typed anywhere on the desktop.
    import tempfile

    class _FakeRefusal:
        reason, integrity, proc, title = "elevated", "HIGH", "windowsterminal.exe", "Admin"
        def __bool__(self):
            return False

    class _FakeTyper:
        def __init__(self):
            self.accept = False
            self.typed = []
            self.user32 = type("u", (), {"GetForegroundWindow": staticmethod(lambda: 1234)})()
        def is_password_manager_window(self):
            return False
        def refusal_for_window(self, hwnd):
            return None if self.accept else _FakeRefusal()
        def type_string(self, text, auto_enter=False):
            if not self.accept:
                return _FakeRefusal()
            self.typed.append(text)
            return True

    d = tempfile.mkdtemp(prefix="keshev-outbox-decoy-")
    path = os.path.join(d, "outbox.jsonl")
    lines = []
    t = _FakeTyper()
    box = Outbox(path, t, log=lines.append, retry_every_s=0.05, max_age_s=3.0,
                 autostart=False)

    ok = True
    box.submit("שלום עידו", _FakeRefusal())
    ok &= box.pending() == 1
    ok &= os.path.exists(path) and "שלום עידו" in open(path, encoding="utf-8").read()
    print("queued            -> pending=%d file=%s" % (box.pending(), os.path.basename(path)))

    state, why = box.tick()                       # window still refuses
    ok &= (state == "waiting" and box.pending() == 1 and not t.typed)
    print("refused target    -> %s (%s), still held" % (state, why))

    t.accept = True
    state, _ = box.tick()                         # window now accepts
    ok &= (state == "delivered" and box.pending() == 0 and t.typed == ["שלום עידו"])
    ok &= open(path, encoding="utf-8").read().strip() == ""
    print("window accepts    -> %s, typed=%r, queue empty" % (state, t.typed))

    # the DROP path, on the decoy: refused for longer than max_age
    t.accept = False
    box.submit("זה ייפול", _FakeRefusal())
    time.sleep(3.2)
    state, _ = box.tick()
    ok &= (state == "dropped" and box.pending() == 0)
    dropped_line = [l for l in lines if "DROPPED" in l]
    ok &= bool(dropped_line)
    print("held past 3 s     -> %s, said: %s" % (state, dropped_line[-1][:110] if dropped_line else "NOTHING"))

    # stale-across-restart: a new Outbox on the same file must not type old words
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"id": "old", "at": _now() - 999, "text": "אתמול",
                             "auto_enter": False}, ensure_ascii=False) + "\n")
    lines2 = []
    t2 = _FakeTyper(); t2.accept = True
    box2 = Outbox(path, t2, log=lines2.append, retry_every_s=0.05, max_age_s=3.0,
                  autostart=False)
    box2.tick()
    ok &= (box2.pending() == 0 and not t2.typed)
    ok &= any("stale-across-restart" in l for l in lines2)
    print("restart with old  -> pending=%d typed=%r (must be 0 and [])" % (box2.pending(), t2.typed))

    for line in lines + lines2:
        print("   |", line[:140])
    try:
        os.remove(path)
        os.rmdir(d)
    except OSError:
        pass
    print("OUTBOX OK" if ok else "OUTBOX FAIL")
    sys.exit(0 if ok else 1)
