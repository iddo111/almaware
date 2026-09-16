"""Pre-flight for KESHEV 6: never hand the engine a decoder that cannot answer.

app/main.py calls decoder.wait_until_ready() before it opens the microphone, and
that call BLOCKS FOREVER by design (decoder.py:83-100 -- "a mic that is listening
into a server that cannot answer is not a mic, it is a shredder"). It probes ONLY
the primary URL's /health; the fallback is never consulted there. So if
KESHEV_STT_URL points at a dead server, THE MICROPHONE NEVER OPENS -- and it
looks completely normal while it doesn't, because main.py prints its
"[mic] device=..." banner BEFORE the gate and its 15 s "waiting" lines keep
trial.log's mtime fresh enough to hold the alive dot green.

This script is what stands between Iddo and that. It runs BEFORE the window.

=============================================================================
2026-09-05 -- THE DECODER MOVED TO THE DGX. Iddo, 18:45:
    "קח פיקוד ... מה הבעיה לשים מודל חדש וטוב על ערן"
The choice used to be "the good model on his PC" or "the old model on the DGX".
It is now the GOOD MODEL ON THE DGX: eran1:8739 runs exactly the model :8738
ran -- ivrit-ai/whisper-large-v3-turbo-ct2, same weights (md5 identical), same
int8_float16, same beam 5, same lexicon prompt, same repair map.

MEASURED before the switch, 209 of HIS OWN segments (the same okset the 09-04
report used), all three servers, same audio, same request, 209/209 HTTP 200 on
each. Names = Chinchilla / Sonnet / OpenClaw / Hermes / psytrance, counted by
eye with no reference decoder involved; CER on the 109 real sentences:

    eran1 :8737 old model    0 names right, 14 garbled, CER 43.0%, wall p50 235 ms
    PC    :8738 KESHEV 6    13 names right,  0 garbled, CER 18.5%, wall p50 375 ms
    eran1 :8739 KESHEV 6    13 names right,  0 garbled, CER 18.5%, wall p50 250 ms

They are NOT byte-identical, and pretending otherwise would be the easy lie
here: the two copies produce the same normalised text on 170 of 209 segments
(81.3%), because a beam search on GB10's kernels is not bit-for-bit the same
search as on an Ampere card. So the honest test is who is CLOSER TO THE
REFERENCE on the segments where they differ, and that is a dead heat:
    all rows  n=174 -> DGX 7, PC 6, tie 161
    sentences n=109 -> DGX 6, PC 4, tie  99
Equal, with the DGX a hair ahead. That is a tie, not a win, and it is enough.

LATENCY, honestly split: the DGX DECODES in 185 ms p50 and the LAN round trip
adds 57 ms (a fresh connection per segment, exactly what decoder.py does), for
250 ms at the client. The PC measured 375 ms in this run -- but it was serving
his live microphone AND the benchmark at the same time, which is the real load
it lives under; uncontended on 09-04 it was 202 ms. So: the DGX is ~50 ms
slower than an idle PC and ~125 ms faster than the PC he actually has, its p90
is 281 ms against 484, and its worst segment was 750 ms against 1,516.
No quality trade, no meaningful latency trade, and his 8 GB card comes back.

THE ORDER IS NOW:
  1. eran1:8739 -- the good model, on the DGX. PRIMARY.
  2. the PC's :8738 -- the same good model, on his own GPU. Started ONLY if
     eran1 does not answer, because the whole point of the move was to stop
     spending his GPU on it. This is the disaster path, not the normal one.
  3. eran1:8737 -- the old, measurably worse model. Offered by name, as a
     question, never silently.
And the running fallback (what decoder.py reaches for mid-segment) is eran1:8737
whenever the primary is a KESHEV 6 server: a different process on a different
port, so a decoder crash is covered, and the window turns amber and shouts
"גיבוי!" the moment one segment is answered by it. A downgrade he can see is a
trade-off; a downgrade he cannot see is the bug this whole file exists to fix.
=============================================================================

Everything a human reads goes to stderr, so it stays visible while this runs.
The machine answer is written to state\\keshev6-env.cmd, which the launcher CALLs
(a `for /f` around this script would have swallowed the countdown).

Exit 0 -> go, and the env fragment exists.  Exit 1 -> refuse; open no window.
"""

import ctypes
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_FRAGMENT = os.path.join(ROOT, "state", "keshev6-env.cmd")

KESHEV6 = r"D:\CLAUDE\keshev-6"
STARTER = os.path.join(KESHEV6, "run_hidden.vbs")
TOKEN_FILE = r"D:/CLAUDE/mic-rebuild/state/stt-token"

# 2026-09-15 06:26, Iddo: "תעביר את פענוח המיק לערן2" -- eran1's GPU is ~83% busy
# (vipass, targ, comfyui) and gpt-oss-120b is coming up there next. eran2:8739
# runs the SAME KESHEV 6 model (model.bin sha256 db2a2265... identical on both
# boxes, same int8_float16, same token), measured 10/10 identical text on his
# own clips, p50 312 ms on eran2 vs 445 ms on the busy eran1. So the order is
# now: eran2:8739 -> eran1:8739 (same model, the fallback) -> PC:8738 (rescue)
# -> eran1:8737 (old model, asked by name). Addresses = fleet_inventory.json
# (eran2 lan <lan-ip>, eran1 lan <lan-ip>) on 2026-09-15.
# Rollback: tools\preflight6.py.bak-sttmove-20260915.
ERAN2 = "http://<lan-ip>:8739/v1/transcribe"    # KESHEV 6 on eran2 - PRIMARY
DGX = "http://<lan-ip>:8739/v1/transcribe"      # KESHEV 6 on eran1 - the fallback
PC = "http://127.0.0.1:8738/v1/transcribe"           # KESHEV 6 on the PC - rescue only
OLD = "http://<lan-ip>:8737/v1/transcribe"      # eran1's old model - last question

NAME = {ERAN2: "eran2:8739 (KESHEV 6 on eran2)",
        DGX: "eran1:8739 (KESHEV 6 on eran1)",
        PC: "PC:8738 (KESHEV 6 on this PC)",
        OLD: "eran1:8737 (the older model)"}

BOOT_WAIT_S = 180.0
PROBE_TIMEOUT_S = 4.0


def token():
    tok = os.environ.get("KESHEV_STT_TOKEN", "").strip()
    if tok:
        return tok
    try:
        with open(TOKEN_FILE, encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return ""


def health(url, timeout=PROBE_TIMEOUT_S):
    """('READY'|'LOADING'|<the server's own word>|'UNREACHABLE', detail dict).

    On the KESHEV 6 server /health answers 200 only when a real clip really
    decoded (its canary), so a 200 here is proof of a decode, not of a socket.
    """
    if url.endswith("/v1/transcribe"):
        base = url[: -len("/v1/transcribe")]
    else:
        base = url.rsplit("/", 1)[0]
    req = urllib.request.Request(base + "/health",
                                 headers={"Authorization": "Bearer " + token()})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body, code = r.read(65536), r.status
    except urllib.error.HTTPError as exc:
        code = exc.code
        try:
            body = exc.read(65536)
        except Exception:
            body = b""
        if code not in (200, 503):
            return "HTTP %d" % code, {}
    except Exception as exc:
        return "UNREACHABLE", {"error": type(exc).__name__}
    try:
        data = json.loads(body.decode("utf-8", errors="replace"))
    except Exception:
        return ("READY" if code == 200 else "LOADING"), {}
    return str(data.get("state") or ("READY" if code == 200 else "LOADING")), data


def say(msg):
    try:
        sys.stderr.write(msg + "\n")
        sys.stderr.flush()
    except Exception:
        pass


DECODER_JSON = os.path.join(ROOT, "state", "decoder.json")
PC_LAST_RESORT = "http://127.0.0.1:8738/v1/transcribe"


def emit(primary, fallback):
    """Hand the launcher the decision as a .cmd fragment it can CALL -- and the
    RUNNING engine the same decision as state\\decoder.json.

    2026-09-11: the .cmd fragment alone is a decision frozen at launch. On
    09-11 03:28 eran1 was rebooted, both doors it names live on eran1, and the
    engine had no way to be told about anywhere else. app/decoder.py now re-reads
    decoder.json per segment, so this probe writes BOTH: the same two doors, plus
    the PC's :8738 as a LAST RESORT the decoder dials only when both eran1 doors
    are dead and its port actually answers.
    """
    os.makedirs(os.path.dirname(ENV_FRAGMENT), exist_ok=True)
    with open(ENV_FRAGMENT, "w", encoding="ascii") as fh:
        fh.write("@echo off\n")
        fh.write("set KESHEV_STT_URL=%s\n" % primary)
        fh.write("set KESHEV_STT_FALLBACK_URL=%s\n" % fallback)
    try:
        import json as _json
        import time as _time
        with open(DECODER_JSON, "w", encoding="utf-8") as fh:
            _json.dump({"primary": primary, "fallback": fallback,
                        "last_resort": PC_LAST_RESORT,
                        "updated_at": _time.strftime("%Y-%m-%dT%H:%M:%S"),
                        "by": "tools/preflight6.py (launch)"},
                       fh, ensure_ascii=False, indent=2)
    except Exception as exc:
        say("  (could not write decoder.json: %s -- the engine will use the "
            "environment, exactly as it did before)" % exc)


def ask_yes_no(text, caption):
    """MB_YESNO | MB_ICONWARNING | MB_TOPMOST, defaulting to No."""
    try:
        MB = 0x00000004 | 0x00000030 | 0x00040000 | 0x00000100   # DEFBUTTON2
        return ctypes.WinDLL("user32").MessageBoxW(None, text, caption, MB) == 6
    except Exception:
        return False


def tell(text, caption):
    try:
        ctypes.WinDLL("user32").MessageBoxW(None, text, caption, 0x00040010)
    except Exception:
        pass


def announce(url, data, fb_state, fb_url=OLD):
    """The two lines Iddo is meant to read: which model, and what happens if it dies."""
    models = data.get("models") or ["?"]
    say("  [OK]  %s - READY   (%s, p50 %s ms, canary %ss)"
        % (NAME[url], str(models[0]).split("/")[-1],
           data.get("decode_p50_ms", "?"), data.get("canary_age_s", "?")))
    say("")
    say("  מפענח / decoder:  %s" % NAME[url])
    say("  גיבוי  / fallback: %s  [%s]" % (NAME.get(fb_url, fb_url or "-"), fb_state))
    if fb_state != "READY":
        say("  [! ]  הגיבוי לא עונה. אם המפענח ייפול באמצע, החלון יצעק 'ממתין למפענח'.")
        say("        No fallback. A mid-session death will show as NOT LISTENING.")
    say("")


def start_pc_server():
    """Start the PC's :8738. The rescue path only -- see the header."""
    if not os.path.exists(STARTER):
        say("  [!!]  לא נמצא / not found: %s" % STARTER)
        return
    try:
        subprocess.Popen(["wscript.exe", STARTER], cwd=KESHEV6,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception as exc:
        say("  [!!]  ההפעלה נכשלה / start failed: %s: %s" % (type(exc).__name__, exc))


def wait_ready(url, seconds):
    deadline = time.monotonic() + seconds
    state, data, last = "UNREACHABLE", {}, ""
    while time.monotonic() < deadline:
        state, data = health(url, timeout=3.0)
        if state == "READY":
            return state, data
        left = max(0, int(deadline - time.monotonic()))
        line = "\r  [..]  %-12s  עוד %3ds / %ds left   " % (state, left, left)
        if line != last:
            try:
                sys.stderr.write(line)
                sys.stderr.flush()
            except Exception:
                pass
            last = line
        time.sleep(2.0)
    try:
        sys.stderr.write("\r" + " " * 64 + "\r")
        sys.stderr.flush()
    except Exception:
        pass
    return state, data


def main():
    try:
        if os.path.exists(ENV_FRAGMENT):
            os.remove(ENV_FRAGMENT)      # a stale answer must not survive a failure
    except OSError:
        pass

    say("")
    say("  ==========================================================")
    say("   KESHEV 6 / קשב 6  -  בדיקת מפענח לפני שהמיקרופון נפתח")
    say("   checking the decoder BEFORE the microphone opens")
    say("  ==========================================================")
    say("")

    # ---- 0. eran2, where the good model lives since 2026-09-15 -------------
    state, data = health(ERAN2)
    if state != "READY":
        say("  [..]  %s - %s. מנסה שוב / retrying..." % (NAME[ERAN2], state))
        state, data = wait_ready(ERAN2, 20.0)  # short: a live service, not a cold boot
    if state == "READY":
        # the running fallback is eran1's copy of the SAME model; the old model
        # only stands in when that copy does not answer
        fb, fb_state = DGX, health(DGX, timeout=3.0)[0]
        if fb_state != "READY":
            old_state = health(OLD, timeout=3.0)[0]
            if old_state == "READY":
                fb, fb_state = OLD, old_state
        announce(ERAN2, data, fb_state, fb)
        emit(ERAN2, fb if fb_state == "READY" else "")
        return 0
    say("  [XX]  %s לא עונה / not answering (%s). מנסה את eran1 / trying eran1."
        % (NAME[ERAN2], state))

    # ---- 1. eran1, the same model on the other DGX -------------------------
    state, data = health(DGX)
    if state != "READY":
        say("  [..]  %s - %s. מנסה שוב / retrying..." % (NAME[DGX], state))
        state, data = wait_ready(DGX, 20.0)   # short: a live service, not a cold boot
    if state == "READY":
        fb_state, _ = health(OLD, timeout=3.0)
        announce(DGX, data, fb_state)
        emit(DGX, OLD if fb_state == "READY" else "")
        return 0

    # ---- 2. the PC's own copy of the same model: the rescue path -----------
    say("  [XX]  %s לא עונה / not answering (%s)." % (NAME[DGX], state))
    say("  [..]  נופל אחורה ל-%s / falling back to it, and STARTING it." % NAME[PC])
    state, data = health(PC)
    if state != "READY":
        start_pc_server()
        state, data = wait_ready(PC, BOOT_WAIT_S)
    if state == "READY":
        fb_state, _ = health(OLD, timeout=3.0)
        say("  [! ]  ערן2 וערן1 לא זמינים - המפענח רץ על הכרטיס שלך, כמו פעם.")
        say("        eran2 and eran1 are unreachable, so the decoder is back on YOUR GPU.")
        announce(PC, data, fb_state)
        emit(PC, OLD if fb_state == "READY" else "")
        return 0

    # ---- 3. neither copy of the good model. Ask, in words. -----------------
    say("  [XX]  %s לא עלה / did not come up (%s)." % (NAME[PC], state))
    fb_state, _ = health(OLD, timeout=4.0)
    say("  ..    %s: %s" % (NAME[OLD], fb_state))
    say("")

    if fb_state == "READY":
        if ask_yes_no(
                "שני השרתים של המודל הטוב לא עונים —\n"
                "לא ערן (:8739) ולא המחשב שלך (:8738).\n\n"
                "לפתוח את המיקרופון על המודל הישן של eran1 (:8737) במקום?\n"
                "הוא פחות מדויק (CER 28.4% מול 18.7%, 0 שמות נכונים מול 13),\n"
                "אבל הוא עונה, והחלון יראה בגדול על איזה מפענח אתה יושב.\n\n"
                "לא = לא נפתח מיקרופון בכלל.\n\n"
                "Neither KESHEV 6 server answers - not eran1:8739, not this PC's "
                ":8738.\nOpen the mic on eran1's older, measurably worse model instead?",
                "קשב 6 · KESHEV 6"):
            say("  ->    נפתח על %s לפי בחירתך / opening on it at your choice." % NAME[OLD])
            say("        החלון יציג את זה בגדול / the window will show it plainly.")
            emit(OLD, "")
            return 0
        say("  ->    ביטלת. המיקרופון לא נפתח / cancelled: the mic was not opened.")
    else:
        tell("אף מפענח לא עונה — לא ערן (:8739), לא המחשב (:8738), ולא eran1:8737.\n\n"
             "המיקרופון לא ייפתח: הוא היה נתקע בהמתנה לנצח,\n"
             "וזה נראה בדיוק כמו מיקרופון תקין.\n\n"
             "בדוק: ssh eran1 'systemctl --user status keshev6-stt'\n"
             "או:   D:\\CLAUDE\\keshev-6\\state\\keshev6.log\n\n"
             "No decoder answers - not eran1:8739, not :8738, not eran1:8737. "
             "Refusing to open a window over a microphone that can never start.",
             "קשב 6 · KESHEV 6")
        say("  ->    אף מפענח לא עונה. מסרב לפתוח חלון מת.")
        say("        No decoder answers. Refusing to open a dead window.")

    say("")
    say("  לוג ערן / DGX log:    ssh eran1 'tail ~/keshev6/state/keshev6.log'")
    say("  לוג המחשב / PC log:   D:\\CLAUDE\\keshev-6\\state\\keshev6.log")
    say("  להפעיל ידנית / by hand:  D:\\CLAUDE\\keshev-6\\RUN-KESHEV6-SERVER.cmd")
    say("")
    return 1


if __name__ == "__main__":
    sys.exit(main())
