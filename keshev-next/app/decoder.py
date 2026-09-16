import requests
import os
import sys
import uuid
import time
import socket

_token_cache = None
FORCED_LANG = "he"  # Hebrew-first: the decode never auto-detects

# The STT server binds its port and logs LISTENING *before* the models are on the
# GPU, and answers 503 {"state":"LOADING"} until they are. Measured gaps between
# LISTENING and READY on this PC: 22s, 62s, 109s, and 423s on the cold boot of
# 2026-08-23 (load_s=247.3 alone). Until that morning this file could not tell a
# loading server from a broken one -- raise_for_status() turned the 503 into a
# RequestException, the segment was dropped, and main.py printed `decode=fail`.
# Seven minutes of Iddo's speech went in the bin without one honest word in the log.
NOT_READY_RETRY_S = float(os.environ.get("KESHEV_STT_NOT_READY_RETRY_S", "6.0"))
WAIT_LOG_EVERY_S = float(os.environ.get("KESHEV_STT_WAIT_LOG_EVERY_S", "15.0"))


def _get_token() -> str:
    global _token_cache
    if _token_cache is not None:
        return _token_cache

    try:
        token_from_env = os.environ.get("KESHEV_STT_TOKEN", "").strip()
        if token_from_env:
            _token_cache = token_from_env
            return _token_cache

        with open(r"D:/CLAUDE/mic-rebuild/state/stt-token", "r", encoding="utf-8") as f:
            _token_cache = f.read().strip()
            return _token_cache
    except Exception:
        _token_cache = ""
        return _token_cache


# ── RUNTIME DECODER FAILOVER (2026-09-11) ─────────────────────────────────────
# Until tonight the decoder's doors were frozen at LAUNCH: tools\preflight6.py
# probed the servers once, wrote state\keshev6-env.cmd, and the engine carried
# those two URLs in its environment block until somebody restarted it.
#
# 2026-09-11 03:28 is what that costs. eran1 was rebooted on Iddo's order, and
# BOTH doors -- primary :8739 and fallback :8737 -- live on eran1. The mic had
# nowhere to go and no way to be told about anywhere else; the PC's own :8738
# starts only from preflight, at launch, which had already happened.
#
# So the doors now live in a FILE the engine re-reads (one stat per segment,
# cached by mtime) and anything may update: state\decoder.json
#
#     {"primary": "...", "fallback": "...", "last_resort": "..."}
#
# and a door that fails is marked bad for BAD_FOR_S seconds so the next segment
# does not pay the same timeout again. The PC's :8738 is deliberately the
# LAST_RESORT and is used only when BOTH eran1 doors are bad AND something is
# actually listening on it -- starting a CUDA decoder next to the live mic for
# no reason is the 2026-08-25 "two Whispers on one 8 GB card" scar.
#
# With no file, the environment behaves exactly as it did before. Nothing that
# worked yesterday changes.
_STATE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "state")
DECODER_JSON = os.environ.get("KESHEV_DECODER_JSON") or os.path.join(_STATE_DIR, "decoder.json")
BAD_FOR_S = float(os.environ.get("KESHEV_DOOR_BAD_FOR_S", "60.0"))
LISTEN_CACHE_S = 30.0

_doors_cache = {"key": None, "doors": None}
_bad_until = {}          # url -> time.monotonic() deadline
_listen_cache = {}       # url -> (checked_at, listening)


def doors_path():
    """Read the env at CALL time, not import time: tests point this at a decoy
    and the guard may move it, and an import-time constant cannot be either."""
    return os.environ.get("KESHEV_DECODER_JSON") or DECODER_JSON


def reset_doors():
    """Forget the cached file and every bad-door mark (tests, and the guard)."""
    _doors_cache["key"] = None
    _doors_cache["doors"] = None
    _bad_until.clear()
    _listen_cache.clear()


def _read_doors_file():
    """{'primary':url,'fallback':url,'last_resort':url} or {} -- never raises."""
    path = doors_path()
    try:
        st = os.stat(path)
    except OSError:
        _doors_cache["key"] = None
        _doors_cache["doors"] = None
        return {}
    key = (path, st.st_mtime_ns, st.st_size)
    if _doors_cache["key"] == key and _doors_cache["doors"] is not None:
        return _doors_cache["doors"]
    try:
        import json as _json
        with open(path, encoding="utf-8") as fh:
            j = _json.load(fh)
        doors = {k: str(j.get(k, "") or "") for k in ("primary", "fallback", "last_resort")}
    except Exception:
        doors = {}
    _doors_cache["key"] = key
    _doors_cache["doors"] = doors
    return doors


def doors():
    """[(role, url), ...] in preference order, empty URLs removed."""
    f = _read_doors_file()
    primary = f.get("primary") or os.environ.get("KESHEV_STT_URL", "http://127.0.0.1:8737/v1/transcribe")
    fallback = f.get("fallback") if f else os.environ.get(
        "KESHEV_STT_FALLBACK_URL", "http://<lan-ip>:8737/v1/transcribe")
    if f and "fallback" not in f:
        fallback = ""
    last_resort = f.get("last_resort", "") if f else os.environ.get("KESHEV_STT_LAST_RESORT_URL", "")
    out = []
    for role, url in (("primary", primary), ("fallback", fallback), ("last_resort", last_resort)):
        if url:
            out.append((role, url))
    return out


def _is_bad(url):
    deadline = _bad_until.get(url)
    return deadline is not None and time.monotonic() < deadline


def mark_bad(url, why=""):
    _bad_until[url] = time.monotonic() + BAD_FOR_S
    print("[decoder] door marked bad for %.0fs: %s%s"
          % (BAD_FOR_S, url, (" (" + why + ")") if why else ""),
          file=sys.stderr, flush=True)


def mark_good(url):
    _bad_until.pop(url, None)


def _something_listens(url):
    """A 0.4 s TCP knock, cached. 'the port is open' is a far weaker claim than
    'the model is loaded' -- it is used ONLY to avoid dialling a door that was
    deliberately retired, never as a health check."""
    now = time.monotonic()
    hit = _listen_cache.get(url)
    if hit and now - hit[0] < LISTEN_CACHE_S:
        return hit[1]
    host, port = "", 0
    try:
        rest = url.split("//", 1)[-1].split("/", 1)[0]
        host, _, port_s = rest.partition(":")
        port = int(port_s or "80")
    except Exception:
        _listen_cache[url] = (now, False)
        return False
    try:
        with socket.create_connection((host, port), timeout=0.4):
            live = True
    except OSError:
        live = False
    _listen_cache[url] = (now, live)
    return live


def attempt_plan():
    """The exact sequence of (role, url) this segment will try, and why.

    primary twice (one quick retry absorbs a transient blip, as it always has),
    then the fallback once, and the last resort ONLY when both eran1 doors are
    bad and its port answers. If every door is marked bad we still try each one
    once -- a stale 60 s mark must never mean 'give up on his sentence'.
    """
    ds = dict(doors())
    plan = []
    primary, fallback, last = ds.get("primary", ""), ds.get("fallback", ""), ds.get("last_resort", "")
    if primary and not _is_bad(primary):
        plan.append(("primary", primary))
        plan.append(("primary", primary))
    if fallback and not _is_bad(fallback):
        plan.append(("fallback", fallback))
    both_dead = (not primary or _is_bad(primary)) and (not fallback or _is_bad(fallback))
    if last and both_dead and _something_listens(last):
        plan.append(("last_resort", last))
    if not plan:
        for role, url in (("primary", primary), ("fallback", fallback)):
            if url:
                plan.append((role, url))
    return plan


def _base_url() -> str:
    """The door we would try FIRST right now (also what /health is asked about)."""
    plan = attempt_plan()
    if plan:
        return plan[0][1]
    ds = dict(doors())
    return ds.get("primary", "") or os.environ.get(
        "KESHEV_STT_URL", "http://127.0.0.1:8737/v1/transcribe")


def _fallback_url() -> str:
    """eran1's STT (the rollback server, same token, same models). 2026-09-03 22:50:
    the PC server timed out 57 times today, every time while the PC was at 100% CPU.
    eran1 answered /health READY with the PC token. When the PC says nothing, ask eran1
    once instead of writing decode=fail. Empty string disables the fallback.

    2026-09-11: now comes from doors() -- state\\decoder.json first, environment
    second -- so it can be changed while the engine runs."""
    return dict(doors()).get("fallback", "")


def _health_url() -> str:
    """/health lives beside /v1/transcribe on the same server."""
    url = _base_url()
    marker = "/v1/transcribe"
    if url.endswith(marker):
        return url[: -len(marker)] + "/health"
    return url.rsplit("/", 1)[0] + "/health"


def server_state(timeout: float = 3.0) -> str:
    """'READY', 'LOADING' (or whatever else the server calls itself), or 'UNREACHABLE'.

    /health answers 200 when the models are decoding and 503 while they load, with
    the state in the body either way. Anything we cannot reach or parse is
    UNREACHABLE -- an honest third answer, not a guess at one of the other two.
    """
    try:
        r = requests.get(_health_url(),
                         headers={"Authorization": f"Bearer {_get_token()}"},
                         timeout=timeout)
        if r.status_code in (200, 503):
            try:
                return str(r.json().get("state", "READY" if r.status_code == 200 else "LOADING"))
            except ValueError:
                return "READY" if r.status_code == 200 else "LOADING"
        return "UNREACHABLE"
    except (requests.RequestException, socket.timeout, OSError):
        return "UNREACHABLE"


def wait_until_ready(poll_s: float = 2.0, on_wait=None, deadline_s: float = None) -> bool:
    """Block until the STT server can actually decode. True when it can.

    Called once by the mic before it opens the audio stream: a mic that is
    listening into a server that cannot answer is not a mic, it is a shredder.
    Waits forever by default -- a visible "waiting for the decoder" is the honest
    state, and far better than silently eating speech. deadline_s caps it for tests.
    """
    started = time.monotonic()
    while True:
        state = server_state()
        if state == "READY":
            return True
        if on_wait is not None:
            on_wait(state, time.monotonic() - started)
        if deadline_s is not None and time.monotonic() - started >= deadline_s:
            return False
        time.sleep(poll_s)


# ── THE POLITENESS HALLUCINATION ──────────────────────────────────────────────────
# Measured 2026-08-30, by feeding the live server things that contain no speech at all:
#
#     digital silence, 8 s   ->  "תודה."
#     faint white noise      ->  "תודה."
#     a pure 440 Hz tone     ->  "תודה רבה."
#
# This is Whisper's known failure on non-speech, in Hebrew: the model has no way to say
# "there was nothing there", so it emits the most common thing said into a microphone.
# It is very likely a real part of why the mic "does not work" for Iddo -- when he is not
# talking, or when music crosses the VAD, **the word תודה is typed into his chat.**
#
# avg_logprob does NOT separate it: silence scored -0.41 and -0.20 while his own room
# recordings scored -0.39 to -0.29. The ranges overlap, so a confidence threshold cannot
# do this job and I am not pretending otherwise.
#
# So the guard is a stop-list, and it is deliberately narrow: a decode is dropped only
# when the WHOLE utterance is one of these bare phrases. The cost is losing a genuine
# solitary "תודה"; the thing it prevents is a day of them.
HALLUCINATIONS = {
    "תודה", "תודה.", "תודה רבה", "תודה רבה.", "תודה לך", "תודה רבה לך",
    "thank you", "thank you.", "thanks for watching", "thanks for watching.",
    "כתוביות", "עברית", "המשך בפעם הבאה", "בהצלחה",
}


def _is_hallucination(text: str) -> bool:
    """True when the entire utterance is a phrase the model emits INSTEAD of silence."""
    t = (text or "").strip().strip("‏‎‫‬").strip()
    return t.lower() in HALLUCINATIONS


def transcribe_hebrew_pcm(pcm_data: bytes) -> tuple:
    url = _base_url()
    token = _get_token()
    request_id = uuid.uuid4().hex[:8] + "-" + str(int(time.time() * 1000))
    duration_ms = len(pcm_data) // 32
    timeout = 10.0

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "audio/x-raw",
        "X-Request-Id": request_id,
        "X-Audio-Duration-Ms": str(duration_ms),
        "X-Lang-Hint": FORCED_LANG
    }

    def _post(target=None):
        """(ok, text, lang, avg_logprob, not_ready) -- not_ready separates a server
        that is still loading from one that is broken. target: which server to ask."""
        try:
            response = requests.post(target or url, data=pcm_data, headers=headers, timeout=timeout)
            if response.status_code == 503:
                return False, "", "he", 0.0, True
            response.raise_for_status()
            data = response.json()
            return (
                True,
                data.get("text", ""),
                data.get("lang", "he"),
                data.get("avg_logprob", 0.0),
                False,
            )
        except (requests.RequestException, ValueError, socket.timeout, OSError):
            return False, "", "he", 0.0, False

    # Attempt, then one quick retry for a transient blip, exactly as before --
    # and if the PC still says nothing, ONE try on eran1 (2026-09-03, see
    # _fallback_url). 2026-09-11: the sequence is decided per segment by
    # attempt_plan(), which skips a door that failed in the last 60 s and can
    # reach the PC's last resort when both eran1 doors are gone.
    plan = attempt_plan()
    not_ready = False
    attempt = 0
    while attempt < len(plan):
        role, target = plan[attempt]
        ok, text, lang, avg_logprob, not_ready = _post(target)
        if ok:
            mark_good(target)
            if role != "primary":
                print("[decoder] answered by fallback " + target, file=sys.stderr, flush=True)
        elif not not_ready:
            # a door that cannot answer is marked, so the NEXT sentence does not
            # pay the same 10 s timeout before reaching a server that works
            is_last_try_on_this_door = (attempt + 1 >= len(plan)
                                        or plan[attempt + 1][1] != target)
            if is_last_try_on_this_door:
                mark_bad(target, "no answer")
        if ok:
            if _is_hallucination(text):
                # Non-speech reached the model and it answered politely. Drop it: an
                # empty result is the truth, and typing תודה into his chat is not.
                return True, "", lang, avg_logprob
            return ok, text, lang, avg_logprob
        if not_ready:
            break
        if attempt == 0:
            time.sleep(0.5)
        attempt += 1
        if attempt >= len(plan):
            # 2026-09-11 03:28 in one line: BOTH eran1 doors died during THIS
            # sentence. The plan was drawn before they were known dead, so ask
            # again -- the last resort only becomes eligible at this moment.
            known = {u for _r, u in plan}
            for r, u in attempt_plan():
                if u not in known:
                    plan.append((r, u))

    if not not_ready:
        return False, "", "he", 0.0

    # The server is up but still loading. Hold the sentence rather than bin it --
    # bounded, because the caller is the audio consumer thread and a long block
    # backs the capture queue up. Long outages are the startup gate's job, not ours.
    deadline = time.monotonic() + NOT_READY_RETRY_S
    while time.monotonic() < deadline:
        time.sleep(0.5)
        ok, text, lang, avg_logprob, not_ready = _post()
        if ok:
            if _is_hallucination(text):
                return True, "", lang, avg_logprob
            return ok, text, lang, avg_logprob
        if not not_ready:
            break

    return False, "", "he", 0.0
