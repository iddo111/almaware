import argparse
import sys
import os
import time
import queue
import threading
import math
import wave
import tempfile
from segmenter import Segmenter
from langroute import route_language
import textguard
import corpus6          # the collector -- see corpus6.py (restored 2026-09-12)
import postcorrect
import logstamp
import outbox

# 2026-09-11 -- A CLOCK ON EVERY LINE. trial.log carried no timestamps at all,
# so "when did the last word actually reach his chat" was unanswerable and
# every night-scare of the last month was diagnosed by counting lines
# backwards. This wraps ONLY stderr (stdout carries the --list-devices JSON
# the window's chooser parses, and stamping that would break the mic chooser).
# Readers strip it through logread6.unstamp(); an unstamped line still parses.
logstamp.install("stderr")


AUTO_ENTER = True
# 2026-08-22 04:25 -- re-armed at 600 against silence hallucinations ("תודה רבה"
# out of dead air). That floor caught SILENCE but not FAR-FIELD speech, which is a
# different disease: Iddo talking from across the room decodes into fluent-looking
# Hebrew nonsense and KESHEV types it (INQUIRY-garble-20260826.md, ~8 such messages
# in one evening).
#
# 2026-08-27 -- raised to 2500 on Iddo's "fix mic", measured on the segment files
# themselves, computing exactly the quantity this gate uses (peak RMS over 64 ms
# frames, the live frame size) rather than the inquiry's segment-mean dBFS:
#
#   confirmed-good segments (22:21, decoded correctly)   peak RMS 6982 - 14442
#   confirmed-garble segments (5 timestamps that typed nonsense)   median 1568
#
#   floor 1200 -> kills 32% of garble      floor 2500 -> kills 72%, 0/4 good
#   floor 1800 -> kills 52%                floor 3000 -> kills 76%, no better after
#
# 2500 sits 2.8x under the QUIETEST confirmed-good segment and silences 57% of the
# day's 1,634 segments, nearly all of them empty room. Chosen over 3000 because the
# good sample is only n=4 and the 2022-08-22 calibration claimed his ordinary speech
# can sit near RMS 904 -- if that older number is ever right, headroom is what saves
# a quiet real sentence. The loud garble a floor cannot reach (max 14445, inside the
# good range) is the LOGPROB_FLOOR's job, below.
# 2026-08-28 01:36 -- REVERTED to 600. Raising it to 2500 that morning BLOCKED HIS
# SPEECH: the log shows his real sentences at peak RMS 840 / 1004 / 1351 / 1438 all
# discarded as "too-quiet", while the only segments loud enough to pass decoded as
# the silence-hallucination "תודה". From where he sat the mic had simply died.
#
# The error was mine and it was a sampling error: I set 2500 from four
# confirmed-good segments that happened to be loud (6982-14442) and ignored the
# 2026-08-22 note directly above, which warned his ordinary speech sits near 904.
#
# The deeper lesson, measured: garble spans 632-14445 and his real speech spans
# ~840-14442. THEY OVERLAP ALMOST ENTIRELY. No RMS floor can separate them, so the
# floor's only honest job is killing true silence. Garble is LOGPROB_FLOOR's job and
# textguard's blocklist -- which is already catching the "תודה" hallucination.
RMS_FLOOR = float(os.environ.get("KESHEV_RMS_FLOOR", "600"))
# 2026-08-30: measured on one night of his real speech -- 1240 of 2252 segments were
# thrown out by the RMS floor (median peak_rms 278 against a floor of 600), and once
# that was opened the VAD gate took over: samples of him actually talking came in at
# vad 0.29-0.30 against a hard 0.40. Both gates were set for a louder signal than he
# produces. Made tunable so this never needs a code edit again.
VAD_MIN_RATIO = float(os.environ.get("KESHEV_VAD_MIN", "0.30"))

# The owner gate observes and logs by default; it does not block. See the note at
# its call site in process_full_segment for the measurement that demoted it.
OWNER_GATE_BLOCKING = os.environ.get("KESHEV_OWNER_GATE", "observe").lower() == "block"

# ── THE CONFIDENCE FLOOR ────────────────────────────────────────────────────
# production AVG_LOGPROB_DROP: below this the decode is a guess, not speech.
#
# -1.2 is the OLD model's (:8737) number and it stays the default. It was the
# only constant of its family that was not tunable, which is why fixing the
# 2026-09-04 hallucination flood needed a code edit instead of a launcher line.
# RUN-KESHEV.cmd already learned this lesson out loud: "Tunable now, so this is
# a number, never an edit."
#
# CALIBRATED 2026-09-04 on 1,799 labelled decodes (1,571 non-speech, 228 of his
# real speech). avg_logprob is the ONE signal that separates on the new decoder
# :8738 -- and it is a property of the MODEL, not of the problem:
#
#     :8738  hallucination p50 -1.109   |   his real speech p50 -0.251
#     :8737  decoder.py's 2026-08-30 note says the opposite, and it is right
#            for :8737 -- silence scored -0.41/-0.20 against his -0.39/-0.29.
#
# Both error rates at each floor, marginal on top of the rest of the pipeline.
# "held-out" = the 1,360 segments :8737 returned empty for on the 09-03 evening,
# a set never used to choose any threshold here:
#
#   floor   this morning (19 he saw)   held-out (431)   his real speech (228)
#   -1.20            0                       0                  0      <- today
#   -1.05            5                     142                  0
#   -0.95           10                     214                  1
#   -0.90           12                     235                  2
#   -0.80           16                     278                  5
#   -0.50           19                     394                 35
#
# -0.95 is the recommended operating point WITH KESHEV_GUARD_V2=1, and it is
# safe on the rollback path too: :8737's avg_logprob over the same 209 real
# sentences has min -0.945, so a -0.95 floor costs 0 of them on the old server.
# That is "harmless on :8737", NOT "helpful on :8737" -- nobody has measured
# :8737 against non-speech, so do not claim the floor protects the rollback.
#
# IF HIS QUIET SPEECH EVER STARTS DISAPPEARING, RAISE THIS NUMBER TOWARD -1.2
# BEFORE TOUCHING ANY CODE. Every positive in the calibration came from one loud
# evening (real-word peak_rms p10 = 5,476) and the 2026-08-28 scar 60 lines above
# is what a threshold set on a loud sample does to a quiet morning.
LOGPROB_FLOOR = float(os.environ.get("KESHEV_LOGPROB_FLOOR", "-1.2"))

STATE_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "state"))
PAUSE_FILE = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "state", "PAUSED"))
HEARTBEAT_FILE = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                               "..", "state", "gui.heartbeat"))


# --- THE DEAD-MAN SWITCH (2026-09-01) --------------------------------------
# Iddo, 15:26: "יש בעיה - המיק פועל בלי קשר לגואי. סדר מיד."
# He was right, and it was structural. gui.py DOES kill this engine on
# WM_DELETE_WINDOW and again in a finally - but that is COOPERATION. Kill the
# window from Task Manager, crash it, or lose it to a logoff race and this
# process lived on recording him with no window and no off switch. Worse:
# gui.py starts us with CREATE_NEW_PROCESS_GROUP, which deliberately detaches
# us from the parent's console signals, so an orphan was the LIKELY outcome,
# not the rare one. Measured today: an orphaned engine was still writing
# segments at 15:50 with no window anywhere on the machine.
#
# A microphone must never outlive its owner. So the engine now watches its own
# owner and stops ITSELF:
#   * KESHEV_OWNER_PID - the window's pid, handed to us in the environment.
#     Owner gone -> we exit. This is instant and is the primary guard.
#   * gui.heartbeat    - touched by the window every few seconds. Stale ->
#     we exit. This also catches a FROZEN window, which the pid check cannot.
#
# Gated on purpose: if neither the env var nor the heartbeat file is present
# we are being run standalone (--list-devices, a test, a console run) and the
# switch stays out of the way. Fail-open there is correct; fail-closed here
# would break every legitimate headless use.
DEADMAN_POLL_S = 3.0
# 2026-09-03 19:50: was 30.0. The window beats every 8 s; on a 100%-CPU evening the
# Tk loop stalled >30 s three times and a LIVE mic was killed for a dead window.
# 60 s still catches a frozen window (the reason this switch exists) and stops
# killing a starved one. Pairs with HIGH/ABOVE_NORMAL priority set in gui.py.
DEADMAN_STALE_S = 60.0


def _pid_alive_win(pid: int) -> bool:
    """True if pid exists. ctypes OpenProcess, NOT os.kill - on Windows
    os.kill(pid, 0) calls TerminateProcess and would KILL the window."""
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False
    import ctypes
    # PROCESS_QUERY_LIMITED_INFORMATION, so we can also ask HOW it ended.
    # OpenProcess alone is NOT enough and this was a real bug caught by the
    # switch's own test on 2026-09-01: on Windows a terminated process keeps a
    # live kernel object for as long as ANYONE holds a handle to it (the parent
    # Popen does), so OpenProcess kept succeeding on a corpse and the switch
    # never fired. A guard that cannot fire is worse than no guard.
    h = ctypes.windll.kernel32.OpenProcess(0x1000, False, int(pid))
    if not h:
        return False
    try:
        code = ctypes.c_ulong()
        ok = ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code))
        if not ok:
            return False
        STILL_ACTIVE = 259
        return code.value == STILL_ACTIVE
    finally:
        ctypes.windll.kernel32.CloseHandle(h)


def start_deadman():
    """Stop the microphone the moment its owner is gone. Daemon thread."""
    owner = os.environ.get("KESHEV_OWNER_PID", "").strip()
    try:
        owner_pid = int(owner) if owner else 0
    except ValueError:
        owner_pid = 0
    if not owner_pid and not os.path.exists(HEARTBEAT_FILE):
        print("[deadman] no owner and no heartbeat - standalone run, switch idle",
              file=sys.stderr)
        return

    def watch():
        while True:
            time.sleep(DEADMAN_POLL_S)
            if owner_pid and not _pid_alive_win(owner_pid):
                print("[deadman] owner pid %d is gone - stopping the microphone"
                      % owner_pid, file=sys.stderr)
                sys.stderr.flush()
                os._exit(0)
            try:
                age = time.time() - os.path.getmtime(HEARTBEAT_FILE)
            except OSError:
                age = None
            if age is not None and age > DEADMAN_STALE_S:
                print("[deadman] heartbeat %.0fs stale - stopping the microphone"
                      % age, file=sys.stderr)
                sys.stderr.flush()
                os._exit(0)

    threading.Thread(target=watch, daemon=True, name="deadman").start()
    print("[deadman] armed: owner=%s heartbeat=%s"
          % (owner_pid or "-", os.path.basename(HEARTBEAT_FILE)), file=sys.stderr)

# The mic chooser (2026-08-29). Iddo: "אין בכלל אפשרות לבחור - תוסיף".
# The window writes {"mode":"default"} or {"mode":"pick","name":...,"hostapi":...}
# here and restarts the engine. The fence still refuses forbidden devices whatever
# this file says -- a chooser is a preference, not a licence to open a headset.
MIC_CHOICE_FILE = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "state", "mic-choice.json"))


def read_mic_choice():
    try:
        import json
        with open(MIC_CHOICE_FILE, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


# ---- THE ONE FENCE (2026-09-09 22:50) ---------------------------------------
# Until tonight this file carried the refuse list TWICE: one copy here for the
# window's dropdown, one inside the engine, and neither read voice-input/
# config.json's never_use_devices. They drifted: the engine learned "usbaudio"
# at 18:13 while the dropdown kept offering 'Microphone (USBAudio1.0)' -- the
# silent Jieli dongle -- as a legitimate choice. One list, one predicate, both
# callers.
_REFUSE_BASE = ("vive", "wh-1000", "hands-free", "handsfree", "headset", "bluetooth",
                "index", "quest", "rift", "oculus", "virtual", "stereo mix",
                "what u hear", "wave out", "loopback",
                # 2026-09-09 18:13 -- the BRIO left the bus when the Quest cable went in
                # and the chooser fell back to 'Microphone (USBAudio1.0)', a Jieli USB
                # dongle that delivers digital silence: DEAF for four hours, reopening
                # every 2 min. Name the known dead ends.
                "usbaudio", "audiorelay", "sound mapper", "bigscreen",
                # 2026-09-09 22:40 -- also present on this PC and none of them a mic:
                # DirectSound's alias for "whatever the default is" (we ask Windows for
                # its default explicitly, with the fence, in _windows_default), the Meta
                # and Bigscreen virtual-audio kernel pins, and a nameless KS pin.
                "primary sound capture", "mrvad", "bsvad", "input ()")


def _config_never_use():
    """never_use_devices from voice-input/config.json, lower-cased; [] if absent."""
    try:
        import json as _json
        p = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))), "voice-input", "config.json")
        with open(p, encoding="utf-8") as f:
            return [str(x).lower() for x in _json.load(f).get("never_use_devices", [])]
    except Exception:
        return []


def refuse_list():
    return tuple(_REFUSE_BASE) + tuple(_config_never_use())


def device_allowed(d, api_name, explicit=False, _refuse=None):
    """May the Sacred Audio Law open this PortAudio input device?

    `explicit` is True only for the device Iddo picked by name in the window's
    chooser. It lifts ONE rule -- the WDM-KS exclusion -- never the refuse list.

    WDM-KS is excluded by default (2026-09-09 22:45): kernel-streaming pins are
    exclusive-mode, KESHEV has never run on one, and they can be ghosts -- tonight
    'Microphone (Scarlett Solo USB)' existed ONLY as a WDM-KS pin (no MMDevice
    endpoint at all) and opening it answered PaErrorCode -9996 'Invalid device'.
    The prefer list would have chosen it and the engine would have died with a
    traceback every 20 s.
    """
    if d["max_input_channels"] <= 0:
        return False
    n = d["name"].lower()
    refuse = _refuse if _refuse is not None else refuse_list()
    if any(r in n for r in refuse):
        return False
    if api_name == "Windows WDM-KS" and not explicit:
        return False
    return True


def list_allowed_devices():
    """JSON for the window's dropdown. Same fence the engine itself obeys."""
    import json
    import sounddevice as sd
    apis = sd.query_hostapis()
    try:
        default_idx = sd.default.device[0]
    except Exception:
        default_idx = -1
    refuse = refuse_list()
    out = []
    for i, d in enumerate(sd.query_devices()):
        api = apis[d["hostapi"]]["name"]
        if not device_allowed(d, api, _refuse=refuse):
            continue
        out.append({"index": i, "name": d["name"],
                    "hostapi": api,
                    "is_pc_default": (i == default_idx)})
    print(json.dumps(out, ensure_ascii=False))


class SegmentPipeline:
    def __init__(self, segmenter, decode_fn, type_fn, frame_ms, owner_gate_fn=None, debug_dump=False, dump_dir=None, rms_floor=0.0, vad_fn=None, vad_min_ratio=0.0, pause_file=None, defer_queue=None, frame_voiced_fn=None, corpus=None):
        self.segmenter = segmenter
        self.decode_fn = decode_fn
        self.type_fn = type_fn
        self.frame_ms = frame_ms
        # Per-FRAME voice verdict for the segmenter's voice endpoint (2026-08-31).
        # vad_fn above judges a whole finished segment; this one judges each 64 ms
        # block as it arrives, so the segmenter can refuse to OPEN on the fan and can
        # CLOSE when the voice stops. None = segmenter behaves exactly as before.
        # (frame_voiced_fn is kept as the on/off switch; the verdict itself comes from
        # the idle-floor tracker in handle_block -- webrtcvad measured blind here.)
        self.frame_voiced_fn = frame_voiced_fn
        from collections import deque
        self._idle_rms = deque(maxlen=300)   # ~19 s of idle frames at 64 ms
        self._voice_over_floor = float(os.environ.get("KESHEV_VOICE_OVER_FLOOR", "1.7"))
        self.owner_gate_fn = owner_gate_fn
        self.debug_dump = debug_dump
        self.dump_dir = dump_dir
        # THE COLLECTOR. None = off. Only TYPED utterances are ever offered
        # to it (see below), which is the whole admission rule.
        self.corpus = corpus
        self.rms_floor = rms_floor
        self.vad_fn = vad_fn
        self.vad_min_ratio = vad_min_ratio
        self.pause_file = pause_file
        # 2026-08-29 -- Iddo: "זה שומע אבל לא מקליד, זה כאילו ממלא מחסנית ליפו".
        # He was right about the shape even if not the data structure. Decoding a
        # segment means a network round trip to the STT server and then typing the
        # text keystroke by keystroke -- and BOTH ran on the very thread that drains
        # the audio queue. While one sentence was being decoded and typed, live audio
        # piled up behind it; the backlog only ever grew, so his words came out long
        # after he said them and the newest blocks were dropped at the 64-block cap.
        # Now the audio thread only resamples and segments. Closed segments go onto
        # this queue and a separate worker decodes and types them, strictly in order.
        self.defer_queue = defer_queue
        self.accumulating = False
        self.audio_buffer = bytearray()
        self.max_buffer_size = 16000 * 2 * 16  # 16 seconds of 16kHz 16-bit PCM
        self.seg_peak_rms = 0.0

    def handle_block(self, block_bytes: bytes, rms: float):
        self.seg_peak_rms = max(self.seg_peak_rms, rms)
        # THE ROOM'S OWN FLOOR (2026-08-31 19:10). webrtcvad was measured blind here --
        # the fan scores 1.00 at every aggressiveness -- so "voice" is defined against
        # the room itself: the mic learns the idle loudness (median of ~19 s of frames
        # collected only while NO segment is open, so speech never teaches the floor),
        # and a frame is voice when it clears KESHEV_VOICE_OVER_FLOOR times that.
        # Measured this evening: idle floor ~990, his speech 4000-17500. The fan can
        # no longer OPEN a segment, and a sentence CLOSES ~1 s after he stops.
        voiced = True
        if self.frame_voiced_fn is not None:
            if self.segmenter._state == "IDLE":
                self._idle_rms.append(rms)
            if len(self._idle_rms) >= 100:
                floor = sorted(self._idle_rms)[len(self._idle_rms) // 2]
                voiced = rms > self._voice_over_floor * max(1.0, floor)
        seg = self.segmenter.feed(self.frame_ms, rms, voiced=voiced)

        # Start accumulating if we just entered SPEAKING state
        if not self.accumulating and self.segmenter._state == "SPEAKING":
            self.accumulating = True
            self.audio_buffer.clear()
            self.seg_peak_rms = 0.0

        # Accumulate every block while in SPEAKING or SILENCE state
        if self.accumulating:
            self.audio_buffer.extend(block_bytes)
            if len(self.audio_buffer) > self.max_buffer_size:
                # Cap the buffer size
                del self.audio_buffer[:len(block_bytes)]

        # If a segment was closed
        if seg is not None:
            if self.accumulating:
                full_audio = bytes(self.audio_buffer)
                self.audio_buffer.clear()
                self.accumulating = False
                peak_rms = self.seg_peak_rms
                self.seg_peak_rms = 0.0
                if self.defer_queue is not None:
                    try:
                        self.defer_queue.put_nowait((full_audio, peak_rms))
                    except queue.Full:
                        print(f"[segment] DROPPED: the decode worker is more than "
                              f"{self.defer_queue.maxsize} segments behind",
                              file=sys.stderr)
                else:
                    self.process_full_segment(full_audio, peak_rms)
        elif self.segmenter._state == "IDLE" and self.accumulating:
            # Discard short noise
            self.audio_buffer.clear()
            self.accumulating = False
            self.seg_peak_rms = 0.0

    def process_full_segment(self, pcm_bytes: bytes, peak_rms: float = 0.0):
        if self.pause_file is not None and os.path.exists(self.pause_file):
            if self.debug_dump:
                print(f"[paused] segment dropped ({len(pcm_bytes)} bytes)", file=sys.stderr)
            return

        if self.vad_fn is not None and self.vad_min_ratio > 0:
            vr = self.vad_fn(pcm_bytes)
            if vr < self.vad_min_ratio:
                if self.debug_dump:
                    n = len(pcm_bytes)
                    print(f"[segment] bytes={n} secs={n / 32000:.2f} peak_rms={peak_rms:.0f} vad={vr:.2f} SKIP", file=sys.stderr)
                return

        # Second fence (2026-08-31): loudness that does not BREATHE is the room, not him.
        # webrtcvad scores the fan 1.00, but modulation separates cleanly: fan 0.26-0.29,
        # his voice 0.77-3.29, measured on 60 real dumps. 0 disables.
        mod_min = float(os.environ.get("KESHEV_MOD_MIN", "0.5"))
        if mod_min > 0:
            import vad
            mod = vad.modulation_ratio(pcm_bytes)
            if mod < mod_min:
                n = len(pcm_bytes)
                print(f"[segment] bytes={n} secs={n / 32000:.2f} peak_rms={peak_rms:.0f} mod={mod:.2f} SKIP steady-noise", file=sys.stderr)
                return

        if self.rms_floor > 0 and peak_rms < self.rms_floor:
            # always announced, not only under --debug-dump: a silently dropped
            # segment is indistinguishable from a dead microphone, and that
            # ambiguity is what cost a whole night.
            n = len(pcm_bytes)
            print(f"[segment] bytes={n} secs={n / 32000:.2f} peak_rms={peak_rms:.0f} floor={self.rms_floor:.0f} SKIP too-quiet", file=sys.stderr)
            return

        gate_score = 0.0
        gate_allowed = False
        decode_ok = False
        decode_text = ""
        decode_lang = ""
        decode_prob = 0.0
        routed = "-"

        if self.debug_dump and self.dump_dir:
            os.makedirs(self.dump_dir, exist_ok=True)
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            millis = int(time.time() * 1000) % 1000
            filename = f"{timestamp}-{millis:03d}.wav"
            filepath = os.path.join(self.dump_dir, filename)
            with wave.open(filepath, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(pcm_bytes)

        if self.owner_gate_fn is not None:
            gate_allowed, gate_score = self.owner_gate_fn(pcm_bytes)
            # 2026-08-22 04:50 -- demoted to OBSERVE-ONLY by default.
            # Evidence: ownergate --selftest scores random NOISE at 0.596 against
            # the stored voiceprint while the threshold is 0.65. A 0.054 margin
            # between noise and the owner is not a decision, it is a coin toss;
            # and in the live path it returned 0.000 on real speech (resemblyzer
            # trims a segment below its 0.4 s minimum) so it blocked EVERYTHING.
            # The score is still measured and logged on every segment, which is
            # exactly the labelled data a learned owner-model needs. Re-arm the
            # block with KESHEV_OWNER_GATE=block once such a model exists.
            if not gate_allowed and OWNER_GATE_BLOCKING:
                if self.debug_dump:
                    n = len(pcm_bytes)
                    print(f"[segment] bytes={n} secs={n / 32000:.2f} peak_rms={peak_rms:.0f} gate={gate_score:.3f}/BLOCK decode=- route=- text=-", file=sys.stderr)
                return

        decode_ok, decode_text, decode_lang, decode_prob = self.decode_fn(pcm_bytes)
        if not decode_ok or not decode_text.strip():
            if self.debug_dump:
                n = len(pcm_bytes)
                gate_str = f"{gate_score:.3f}/PASS" if self.owner_gate_fn else "-"
                # 2026-09-01 03:45: one label hid two different truths and cost a
                # night-scare twice. decode=empty is the HONESTY GUARD working
                # (hallucination dropped, server answered 200); decode=fail is the
                # transport actually failing. Never conflate them again.
                label = "empty" if decode_ok else "fail"
                print(f"[segment] bytes={n} secs={n / 32000:.2f} peak_rms={peak_rms:.0f} gate={gate_str} decode={label} route=- text=-", file=sys.stderr)
            return

        # Confidence floor check (production truth: AVG_LOGPROB_DROP = -1.2)
        if decode_prob < LOGPROB_FLOOR:
            if self.debug_dump:
                # 2026-09-05 00:20: this line logged a NUMBER and threw the WORDS away,
                # so the floor could never be calibrated against what it was eating.
                # 838 of 1028 decoded segments were dropped here in one stretch -- 82%
                # of everything the decoder actually transcribed -- and not one of them
                # left a trace of what Iddo had said. Print the text.
                print(f"[confidence] dropped ({len(pcm_bytes)} bytes, lp={decode_prob:.2f}) text={ascii(decode_text)[:100]}", file=sys.stderr)
            return

        routed = route_language(decode_text, decode_lang, decode_prob)
        if routed is not None:
            # POST-CORRECTION (2026-09-12) -- OFF unless KESHEV_POSTCORRECT=1.
            # Measured on 34 real utterances of his from tonight (02:42-03:43):
            # fixes 2 of 7 known garbles, changed 0 of 18 correct ones, +1.17 s
            # at p50. OFF because a decode is ~200 ms and he dictates in real
            # time. Disarmed this is a no-op returning the text unchanged; armed
            # it fails open on any error, timeout or refusal. route_language
            # above deliberately still sees the RAW text, so arming this can
            # never change the he/en routing decision.
            decode_text = postcorrect.repair(decode_text)
            guard_ok, guard_reason = textguard.text_verdict(decode_text)
            if guard_ok:
                typed = self.type_fn(decode_text)
                # --- corpus capture (2026-09-12) -------------------------------
                # An utterance may enter the training corpus ONLY if it was
                # actually typed into his window: that is the admission rule
                # the original collector used, and it is what keeps room audio
                # out. Best-effort, never raises -- a collector must not be
                # able to break the microphone.
                if self.corpus is not None and typed:
                    self.corpus.add(pcm_bytes, decode_text, engine=routed or '?')
                # 2026-09-06 (Iddo: "the mic must type into the CLI too"): the typer
                # REFUSES an elevated (Run-as-administrator) window instead of letting
                # Windows eat the keys -- and until now this line threw that answer
                # away, so the [segment] line below still read decode=ok route=he and
                # the window counted the sentence as typed. Same shape as the
                # [textguard] line, paired by byte count, so gui6 shows נחסם + why.
                if typed is not None and not typed and getattr(typed, "reason", "") == "elevated":
                    print(f"[typer] refused segment ({len(pcm_bytes)} bytes): elevated "
                          f"proc={typed.proc or '?'} integrity={typed.integrity} | "
                          f"{typed.message_he} | {typed.message_en}", file=sys.stderr, flush=True)
            elif self.debug_dump:
                n = len(pcm_bytes)
                print(f"[textguard] dropped segment ({n} bytes): {guard_reason}", file=sys.stderr)

        if self.debug_dump:
            n = len(pcm_bytes)
            gate_str = f"{gate_score:.3f}/PASS" if self.owner_gate_fn else "-"
            print(f"[segment] bytes={n} secs={n / 32000:.2f} peak_rms={peak_rms:.0f} gate={gate_str} lp={decode_prob:.2f} decode=ok route={routed} text={ascii(decode_text)[:80]}", file=sys.stderr)


def decode_file_once(wav_path, do_type=False, debug_dump=True):
    r"""One WAV -> the REAL decoder -> (optionally) the REAL typer. No microphone.

    2026-09-11. The standing question this exists to answer is the one nothing
    could answer before: *does a sentence still get all the way from audio to his
    chat?* `/health: READY` cannot answer it -- on 2026-09-10 the decoder said
    READY for 310 minutes while its own canary was empty. Only pushing real audio
    through the real path and reading the text out of the target window can.

    The segmenter and the audio device are the only things skipped: the PCM goes
    straight into the same SegmentPipeline every live segment goes through, so
    the RMS floor, the modulation fence, the owner gate, the confidence floor,
    the language router, textguard and the typer are all the live ones.

    Exit code 0 = decoded (and typed, if asked). 1 = it did not arrive.
    """
    import json as _json
    import decoder
    import typer
    import ownergate
    import vad

    try:
        with wave.open(wav_path, "rb") as wf:
            ch, width, rate, nframes = (wf.getnchannels(), wf.getsampwidth(),
                                        wf.getframerate(), wf.getnframes())
            pcm = wf.readframes(nframes)
    except Exception as exc:
        print(_json.dumps({"ok": False, "error": "%s: %s" % (type(exc).__name__, exc)}))
        return 1
    if (ch, width, rate) != (1, 2, 16000):
        print(_json.dumps({"ok": False, "error": "need 16 kHz mono 16-bit, got "
                                                 "%dch/%dbit/%dHz" % (ch, width * 8, rate)}))
        return 1

    # peak RMS over 64 ms blocks -- EXACTLY the quantity the live gate uses
    # (main.py's audio callback), so the floor sees the same number it would see
    # if these samples had come off the BRIO.
    import array as _array
    frame_samples = 16000 * 64 // 1000
    samples = _array.array("h")
    samples.frombytes(pcm[: len(pcm) // 2 * 2])
    peak = 0.0
    for i in range(0, max(0, len(samples) - frame_samples), frame_samples):
        block = samples[i:i + frame_samples]
        peak = max(peak, math.sqrt(sum(float(v) * v for v in block) / len(block)))

    typed_texts = []
    t0 = time.monotonic()
    decoded = {"ok": False, "text": "", "lang": "", "lp": 0.0}

    def _decode(pcm_bytes):
        r = decoder.transcribe_hebrew_pcm(pcm_bytes)
        decoded.update({"ok": bool(r[0]), "text": r[1], "lang": r[2], "lp": float(r[3])})
        return r

    def _type(text):
        typed_texts.append(text)
        if not do_type:
            return True
        answer = typer.type_string(text, auto_enter=False)
        if answer is not None and not answer:
            print("[accept] the typer REFUSED: %s" % getattr(answer, "reason", "?"),
                  file=sys.stderr, flush=True)
        return answer

    # The owner gate is OBSERVE-ONLY in the live engine (it was demoted on
    # 2026-08-22 after it scored random noise at 0.596 against a 0.65 threshold
    # and returned 0.000 on real speech). It cannot change the outcome of this
    # test, and including it would load resemblyzer/torch on every run -- CPU
    # that belongs to his microphone. Off by default, honestly named.
    gate_fn = None
    if os.environ.get("KESHEV_ACCEPT_OWNER_GATE", "0") == "1":
        gate_fn = ownergate.OwnerGate().identify

    pipeline = SegmentPipeline(
        None, _decode, _type, frame_ms=64,
        owner_gate_fn=gate_fn,
        debug_dump=debug_dump, dump_dir=None,
        rms_floor=RMS_FLOOR, vad_fn=vad.voiced_ratio, vad_min_ratio=VAD_MIN_RATIO,
        # PAUSED is NOT honoured here on purpose: this path opens no microphone
        # and types only into a decoy the caller focused. The caller (mic_accept)
        # is the one that refuses to run while he is paused.
        pause_file=None)
    pipeline.process_full_segment(pcm, peak_rms=peak)
    ms = int((time.monotonic() - t0) * 1000)

    print(_json.dumps({"ok": bool(decoded["ok"] and typed_texts),
                       "decoded": decoded["text"], "lang": decoded["lang"],
                       "lp": round(decoded["lp"], 3), "typed": typed_texts[0] if typed_texts else "",
                       "peak_rms": round(peak), "secs": round(len(pcm) / 32000.0, 2),
                       "ms": ms, "door": decoder._base_url()}, ensure_ascii=False))
    return 0 if (decoded["ok"] and typed_texts) else 1


def main():
    parser = argparse.ArgumentParser(description="KESHEV mic wiring pipeline")
    parser.add_argument('--selftest', action='store_true', help="Run pipeline self-test")
    parser.add_argument('--debug-dump', action=argparse.BooleanOptionalAction, default=True, help="Dump segments to WAV files and log details")
    parser.add_argument('--list-devices', action='store_true',
                        help="Print the allowed input devices as JSON and exit (the window's chooser uses this)")
    # 2026-09-11 -- the injectable path the standing acceptance test needs
    # (tools\mic_accept.py). A WAV goes in, the REAL decoder decodes it and the
    # REAL typer types it into whatever window has the focus. NO AUDIO DEVICE IS
    # OPENED -- that is the whole point: a gate is tested on a decoy, never on
    # the living microphone, and the mic is never taken from Iddo to run a test.
    parser.add_argument('--decode-file', metavar='WAV', default=None,
                        help="Decode one 16 kHz mono WAV through the real pipeline and exit. "
                             "Opens no microphone.")
    parser.add_argument('--type', action='store_true',
                        help="With --decode-file: also TYPE the result into the focused window "
                             "(the acceptance test focuses its own decoy window first).")
    args = parser.parse_args()

    if args.list_devices:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        list_allowed_devices()
        return

    if args.decode_file:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        return decode_file_once(args.decode_file, do_type=args.type,
                                debug_dump=args.debug_dump)

    if args.selftest:
        # Self-test mode
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

        # The modulation fence first, on its own synthetic audio -- then OFF for the
        # legacy cases below, whose constant-amplitude tones score mod 0.00 by design
        # (synthetic audio does not breathe; real speech does).
        import vad as _vad
        import struct as _struct
        _flat = b"".join(_struct.pack("<h", int(3000 * math.sin(i * 0.5)))
                         for i in range(16000 * 3))                       # steady tone
        _breathing = b"".join(_struct.pack("<h", int((3000 if (i // 8000) % 2 else 150)
                              * math.sin(i * 0.5))) for i in range(16000 * 3))
        assert _vad.modulation_ratio(_flat) < 0.5, "flat tone must read as steady noise"
        assert _vad.modulation_ratio(_breathing) >= 0.5, "breathing tone must read as voice"
        print("MODULATION FENCE OK (flat %.2f < 0.5 <= breathing %.2f)"
              % (_vad.modulation_ratio(_flat), _vad.modulation_ratio(_breathing)))
        os.environ["KESHEV_MOD_MIN"] = "0"

        decode_calls = []
        typed_texts = []
        gate_calls = []

        def stub_decode(pcm_bytes):
            decode_calls.append(pcm_bytes)
            return (True, "שלום עולם", "he", -0.3)

        def stub_type(text):
            typed_texts.append(text)
            print(text)

        def stub_gate(pcm):
            gate_calls.append(pcm)
            return (True, 0.99)

        segmenter = Segmenter(min_ms=300, max_ms=15000, silence_ms=1000, gate=0.02)
        pipeline = SegmentPipeline(segmenter, stub_decode, stub_type, frame_ms=64, owner_gate_fn=stub_gate, debug_dump=False)

        block_bytes = b"\x00" * 2048  # 1024 int16 samples

        # 3 silence blocks
        for _ in range(3):
            pipeline.handle_block(block_bytes, rms=0.0)

        # 10 speech blocks
        for _ in range(10):
            pipeline.handle_block(block_bytes, rms=0.5)

        # 25 silence blocks
        for _ in range(25):
            pipeline.handle_block(block_bytes, rms=0.0)

        # Verification of passing gate run
        try:
            assert len(decode_calls) == 1, f"Decoder called {len(decode_calls)} times, expected 1"
            assert len(gate_calls) == 1, f"Gate called {len(gate_calls)} times, expected 1"
            expected_length = 27 * 2048  # 10 speech blocks + 17 silence-tail blocks (incl. the closing block)
            actual_length = len(decode_calls[0])
            assert actual_length == expected_length, f"PCM length mismatch: got {actual_length}, expected {expected_length}"
            assert len(gate_calls[0]) == expected_length, f"Gate saw {len(gate_calls[0])} bytes, expected {expected_length}"
            assert route_language("שלום עולם", "he", -0.3) == "he", "Language routing failed"
            assert typed_texts == ["שלום עולם"], f"Typed texts mismatch: got {typed_texts}, expected ['שלום עולם']"
        except AssertionError as e:
            print(f"PIPELINE FAIL: {e}")
            sys.exit(1)

        # Blocking gate test.
        # 2026-08-22 04:50 the owner gate was demoted to observe-only by default
        # (OWNER_GATE_BLOCKING), but this case was left asserting that it blocks, so
        # --selftest has printed PIPELINE FAIL ever since -- and a selftest that always
        # fails guards nothing. It now arms the flag it is testing, and a fourth case
        # below pins the default: observing must NOT block.
        global OWNER_GATE_BLOCKING
        _gate_flag_saved = OWNER_GATE_BLOCKING
        OWNER_GATE_BLOCKING = True
        decode_calls2 = []
        typed_texts2 = []
        gate_calls2 = []

        def stub_decode2(pcm_bytes):
            decode_calls2.append(pcm_bytes)
            return (True, "שלום עולם", "he", -0.3)

        def stub_type2(text):
            typed_texts2.append(text)
            print(text)

        def stub_gate2(pcm):
            gate_calls2.append(pcm)
            return (False, 0.1)

        segmenter2 = Segmenter(min_ms=300, max_ms=15000, silence_ms=1000, gate=0.02)
        pipeline2 = SegmentPipeline(segmenter2, stub_decode2, stub_type2, frame_ms=64, owner_gate_fn=stub_gate2, debug_dump=False)

        # Reuse the same synthetic schedule
        # 3 silence blocks
        for _ in range(3):
            pipeline2.handle_block(block_bytes, rms=0.0)

        # 10 speech blocks
        for _ in range(10):
            pipeline2.handle_block(block_bytes, rms=0.5)

        # 25 silence blocks
        for _ in range(25):
            pipeline2.handle_block(block_bytes, rms=0.0)

        # Verification of blocking gate run
        try:
            assert len(gate_calls2) == 1, f"Blocking gate called {len(gate_calls2)} times, expected 1"
            assert len(decode_calls2) == 0, f"Decoder called {len(decode_calls2)} times, expected 0"
            assert len(typed_texts2) == 0, f"Typed texts count {len(typed_texts2)}, expected 0"
        except AssertionError as e:
            OWNER_GATE_BLOCKING = _gate_flag_saved
            print(f"PIPELINE FAIL: {e}")
            sys.exit(1)
        OWNER_GATE_BLOCKING = _gate_flag_saved

        # Observing gate must NOT block -- the shipped default.
        decode_calls2b = []
        pipeline2b = SegmentPipeline(
            Segmenter(min_ms=300, max_ms=15000, silence_ms=1000, gate=0.02),
            lambda pcm: (decode_calls2b.append(pcm), (True, "shalom", "he", -0.3))[1],
            lambda text: None,
            frame_ms=64, owner_gate_fn=lambda pcm: (False, 0.1), debug_dump=False)
        for _ in range(3):
            pipeline2b.handle_block(block_bytes, rms=0.0)
        for _ in range(10):
            pipeline2b.handle_block(block_bytes, rms=0.5)
        for _ in range(25):
            pipeline2b.handle_block(block_bytes, rms=0.0)
        try:
            assert OWNER_GATE_BLOCKING is False, "shipped default must be observe-only"
            assert len(decode_calls2b) == 1, (
                f"Observing gate blocked the decode ({len(decode_calls2b)} calls, expected 1)")
        except AssertionError as e:
            print(f"PIPELINE FAIL: {e}")
            sys.exit(1)

        # VAD front door test
        decode_calls3 = []
        typed_texts3 = []
        gate_calls3 = []
        vad_calls3 = []

        def stub_decode3(pcm_bytes):
            decode_calls3.append(pcm_bytes)
            return (True, "שלום עולם", "he", -0.3)

        def stub_type3(text):
            typed_texts3.append(text)
            print(text)

        def stub_gate3(pcm):
            gate_calls3.append(pcm)
            return (True, 0.99)

        def stub_vad3(pcm_bytes):
            vad_calls3.append(pcm_bytes)
            return 0.1

        segmenter3 = Segmenter(min_ms=300, max_ms=15000, silence_ms=1000, gate=0.02)
        pipeline3 = SegmentPipeline(segmenter3, stub_decode3, stub_type3, frame_ms=64, owner_gate_fn=stub_gate3, debug_dump=False, vad_fn=stub_vad3, vad_min_ratio=0.4)

        # Reuse the same synthetic schedule
        # 3 silence blocks
        for _ in range(3):
            pipeline3.handle_block(block_bytes, rms=0.0)

        # 10 speech blocks
        for _ in range(10):
            pipeline3.handle_block(block_bytes, rms=0.5)

        # 25 silence blocks
        for _ in range(25):
            pipeline3.handle_block(block_bytes, rms=0.0)

        # Verification of VAD front door run
        try:
            assert len(vad_calls3) == 1, f"VAD called {len(vad_calls3)} times, expected 1"
            expected_vad_length = 27 * 2048
            assert len(vad_calls3[0]) == expected_vad_length, f"VAD PCM length mismatch: got {len(vad_calls3[0])}, expected {expected_vad_length}"
            assert len(gate_calls3) == 0, f"Gate called {len(gate_calls3)} times, expected 0"
            assert len(decode_calls3) == 0, f"Decoder called {len(decode_calls3)} times, expected 0"
            assert len(typed_texts3) == 0, f"Typed texts count {len(typed_texts3)}, expected 0"
        except AssertionError as e:
            print(f"PIPELINE FAIL: {e}")
            sys.exit(1)

        # TextGuard test
        decode_calls4 = []
        typed_texts4 = []
        gate_calls4 = []

        def stub_decode4(pcm_bytes):
            decode_calls4.append(pcm_bytes)
            return (True, "תודה.", "he", -0.1)

        def stub_type4(text):
            typed_texts4.append(text)
            print(text)

        def stub_gate4(pcm):
            gate_calls4.append(pcm)
            return (True, 0.99)

        segmenter4 = Segmenter(min_ms=300, max_ms=15000, silence_ms=1000, gate=0.02)
        pipeline4 = SegmentPipeline(segmenter4, stub_decode4, stub_type4, frame_ms=64, owner_gate_fn=stub_gate4, debug_dump=False)

        # Reuse the same synthetic schedule
        # 3 silence blocks
        for _ in range(3):
            pipeline4.handle_block(block_bytes, rms=0.0)

        # 10 speech blocks
        for _ in range(10):
            pipeline4.handle_block(block_bytes, rms=0.5)

        # 25 silence blocks
        for _ in range(25):
            pipeline4.handle_block(block_bytes, rms=0.0)

        # Verification of textguard run
        try:
            assert len(decode_calls4) == 1, f"TextGuard decoder called {len(decode_calls4)} times, expected 1"
            assert len(gate_calls4) == 1, f"TextGuard gate called {len(gate_calls4)} times, expected 1"
            expected_length4 = 27 * 2048
            assert len(decode_calls4[0]) == expected_length4, f"TextGuard PCM length mismatch: got {len(decode_calls4[0])}, expected {expected_length4}"
            assert len(gate_calls4[0]) == expected_length4, f"TextGuard gate saw {len(gate_calls4[0])} bytes, expected {expected_length4}"
            assert typed_texts4 == [], f"TextGuard typed texts should be empty, got {typed_texts4}"
            assert textguard.text_allowed("תגיד לי מה המצב בערן 4") is True, "Real sentence should be allowed"
            assert textguard.text_allowed("תודה.") is False, "Whisper silence hallucination should be blocked"
        except AssertionError as e:
            print(f"PIPELINE FAIL: {e}")
            sys.exit(1)

        # Pause test
        fd, pause_path = tempfile.mkstemp()
        os.close(fd)  # the pause file EXISTS now

        decode_calls5 = []
        typed_texts5 = []
        gate_calls5 = []

        def stub_decode5(pcm_bytes):
            decode_calls5.append(pcm_bytes)
            return (True, "שלום עולם", "he", -0.3)

        def stub_type5(text):
            typed_texts5.append(text)
            print(text)

        def stub_gate5(pcm):
            gate_calls5.append(pcm)
            return (True, 0.99)

        segmenter5 = Segmenter(min_ms=300, max_ms=15000, silence_ms=1000, gate=0.02)
        pipeline5 = SegmentPipeline(segmenter5, stub_decode5, stub_type5, frame_ms=64, owner_gate_fn=stub_gate5, debug_dump=False, pause_file=pause_path)

        # Reuse the same synthetic schedule
        # 3 silence blocks
        for _ in range(3):
            pipeline5.handle_block(block_bytes, rms=0.0)

        # 10 speech blocks
        for _ in range(10):
            pipeline5.handle_block(block_bytes, rms=0.5)

        # 25 silence blocks
        for _ in range(25):
            pipeline5.handle_block(block_bytes, rms=0.0)

        # Verification of pause run (paused -> all dropped)
        try:
            assert len(gate_calls5) == 0, f"Gate called {len(gate_calls5)} times while paused, expected 0"
            assert len(decode_calls5) == 0, f"Decoder called {len(decode_calls5)} times while paused, expected 0"
            assert len(typed_texts5) == 0, f"Typed texts count {len(typed_texts5)} while paused, expected 0"
        except AssertionError as e:
            print(f"PIPELINE FAIL: {e}")
            sys.exit(1)

        os.remove(pause_path)  # unpause

        # Feed the SAME schedule again on the SAME pipeline
        # 3 silence blocks
        for _ in range(3):
            pipeline5.handle_block(block_bytes, rms=0.0)

        # 10 speech blocks
        for _ in range(10):
            pipeline5.handle_block(block_bytes, rms=0.5)

        # 25 silence blocks
        for _ in range(25):
            pipeline5.handle_block(block_bytes, rms=0.0)

        # Verification of unpaused run (flows end to end)
        try:
            assert len(decode_calls5) == 1, f"Decoder called {len(decode_calls5)} times after unpause, expected 1"
            assert len(gate_calls5) == 1, f"Gate called {len(gate_calls5)} times after unpause, expected 1"
            expected_length5 = 27 * 2048
            assert len(decode_calls5[0]) == expected_length5, f"PCM length mismatch: got {len(decode_calls5[0])}, expected {expected_length5}"
            assert len(gate_calls5[0]) == expected_length5, f"Gate saw {len(gate_calls5[0])} bytes, expected {expected_length5}"
            assert typed_texts5 == ["שלום עולם"], f"Typed texts mismatch: got {typed_texts5}, expected ['שלום עולם']"
        except AssertionError as e:
            print(f"PIPELINE FAIL: {e}")
            sys.exit(1)

        # Confidence floor test (sixth verification)
        decode_calls6 = []
        typed_texts6 = []

        def stub_decode6(pcm_bytes):
            decode_calls6.append(pcm_bytes)
            return (True, "מלמול לא ברור בכלל", "he", -1.5)

        def stub_type6(text):
            typed_texts6.append(text)
            print(text)

        def stub_gate6(pcm):
            return (True, 0.99)

        segmenter6 = Segmenter(min_ms=300, max_ms=15000, silence_ms=1000, gate=0.02)
        pipeline6 = SegmentPipeline(segmenter6, stub_decode6, stub_type6, frame_ms=64, owner_gate_fn=stub_gate6, debug_dump=False)

        # Reuse the same synthetic schedule
        # 3 silence blocks
        for _ in range(3):
            pipeline6.handle_block(block_bytes, rms=0.0)

        # 10 speech blocks
        for _ in range(10):
            pipeline6.handle_block(block_bytes, rms=0.5)

        # 25 silence blocks
        for _ in range(25):
            pipeline6.handle_block(block_bytes, rms=0.0)

        # Verification of confidence floor run (decode_prob = -1.5 < LOGPROB_FLOOR = -1.2)
        try:
            assert len(decode_calls6) == 1, f"Decoder called {len(decode_calls6)} times for low-confidence segment, expected 1"
            assert len(typed_texts6) == 0, f"Typed texts should be empty due to confidence floor, got {typed_texts6}"
        except AssertionError as e:
            print(f"PIPELINE FAIL: {e}")
            sys.exit(1)

        print("PIPELINE OK")
        sys.exit(0)

    else:
        # Mic path
        import sounddevice as sd
        import numpy as np
        from scipy.signal import resample_poly
        import decoder
        import typer
        import wintarget       # 2026-09-12: window TARGET LOCK -- see wintarget.py
        import ownergate
        import vad

        # ---- THE MIC FENCE (2026-08-28) ----------------------------------
        # This used to be a bare `sd.query_devices(kind="input")` -- whatever Windows
        # happened to call the default. Tonight SteamVR started and Windows silently
        # made the HEADSET the default: the log read
        #     [mic] device='Microphone (2- HTC Vive)'
        # A headset is NEVER a microphone here (Sacred Audio Law): opening a Bluetooth
        # headset's mic flips it to HFP telephone quality and wrecks Iddo's sound. The
        # law names USB mics only -- BRIO first, then Scarlett, then any wired USB --
        # and says that with no good mic the app stays OFF rather than falling back.
        # So: prefer by name, refuse by name, and idle if neither matches.
        PREFER = ("brio", "scarlett", "usb")
        # The refuse list and the predicate live at module level now (device_allowed,
        # 2026-09-09 22:50) so the window's dropdown and this engine can never
        # disagree. Re-read the config each pick: it is cheap and the list may grow.

        def _every_input():
            apis = sd.query_hostapis()
            return [(i, d, apis[d["hostapi"]]["name"])
                    for i, d in enumerate(sd.query_devices())]

        def _allowed():
            """Every input device the Sacred Audio Law lets us open, in list order."""
            refuse = refuse_list()
            return [(i, d, api) for i, d, api in _every_input()
                    if device_allowed(d, api, _refuse=refuse)]

        def _windows_default():
            """The mic the PC itself is set to right now, or None if it is not usable.

            2026-08-29, Iddo: "תוסיף שיבחר את המיק הנוכחי של הפיסי כברירת מחדל".
            So we ask Windows first -- but the fence still has the last word. On the
            morning he asked, Windows' own default was STUCK on the HTC Vive with the
            headset switched off and the endpoint gone; obeying it blindly is how the
            deaf night happened. Honour the PC's choice only when it is a real, allowed,
            present device.
            """
            try:
                idx = sd.default.device[0]
            except Exception:
                return None
            if idx is None or idx < 0:
                return None
            try:
                d = sd.query_devices(idx)
                api = sd.query_hostapis()[d["hostapi"]]["name"]
            except Exception:
                return None
            if not device_allowed(d, api):
                return None
            return idx, d

        def _pick_input():
            """Choice order: what Iddo picked > what the PC is set to > the prefer list."""
            good = _allowed()

            # 1. An explicit choice from the window's mic chooser always wins.
            want = read_mic_choice()
            if want and want.get("mode") != "default":
                # His pick may be a WDM-KS device (explicit lifts that one rule);
                # it may never be a refused one.
                for i, d, api in _every_input():
                    if (d["name"] == want.get("name") and api == want.get("hostapi")
                            and device_allowed(d, api, explicit=True)):
                        print(f"[mic] chooser: using Iddo's pick {d['name']!r} [{api}]",
                              file=sys.stderr)
                        return i, d
                print(f"[mic] chooser: {want.get('name')!r} [{want.get('hostapi')}] is "
                      f"not here right now -- falling back to the PC default.",
                      file=sys.stderr)

            # 2. Whatever the PC itself is set to, if the fence allows it.
            wd = _windows_default()
            if wd is not None:
                print(f"[mic] using the PC's own default input: {wd[1]['name']!r}",
                      file=sys.stderr)
                return wd

            # 3. The prefer list -- BRIO, then Scarlett, then any wired USB.
            for pref in PREFER:
                for i, d, api in good:
                    if pref in d["name"].lower():
                        print(f"[mic] PC default unusable; prefer-list picked "
                              f"{d['name']!r} [{api}]", file=sys.stderr)
                        return i, d
            # No BRIO, no Scarlett, no named USB mic: idle_if_no_good_mic. The old
            # `return good[0]` here handed the stream to whatever input was left
            # (2026-09-09: a silent dongle) -- the exact fallback the Sacred Audio
            # Law forbids. Staying OFF is the correct state; the GUI keeps retrying.
            return None, None

        dev_index, dev_info = _pick_input()
        # 2026-08-29 -- THE DEAF NIGHT. The fence above resolved an INDEX out of
        # sd.query_devices() and handed that integer to InputStream. An index is not
        # an identity: the list grows and shrinks as SteamVR, Bluetooth headsets and
        # USB mics come and go. On 08-28 23:44 SteamVR was up, the fence correctly
        # refused the Vive and picked the BRIO -- at index 4 OF THAT MOMENT'S LIST.
        # SteamVR then closed, the list shrank, and the stream was left pointing at
        # something that is not the BRIO. It never errored. It just went silent:
        # 0 segments in 3h45m, against 466 on the previous identical empty-room night.
        # A name is re-resolved by sounddevice at open time, so it cannot go stale.
        # A bare name is ambiguous -- the BRIO appears under MME, DirectSound, WASAPI
        # and WDM-KS at once, and sounddevice rightly refuses to guess. So the identity
        # is (name, host API), and the INDEX is looked up fresh at open time.
        dev_api = sd.query_hostapis()[dev_info['hostapi']]['name'] if dev_info else None
        dev_name = dev_info['name'] if dev_info else None

        def _resolve_now():
            """Find today's index for the mic we chose. Never trust a stale one."""
            for i, d in enumerate(sd.query_devices()):
                if (d['max_input_channels'] > 0 and d['name'] == dev_name
                        and sd.query_hostapis()[d['hostapi']]['name'] == dev_api):
                    return i
            return None

        if dev_info is None:
            print("[mic] NO ALLOWED USB MIC. Every input device is on the refuse list "
                  "(headset / bluetooth / loopback). Staying OFF rather than opening one "
                  "-- Sacred Audio Law, idle_if_no_good_mic.", file=sys.stderr)
            sys.exit(3)
        name = dev_info['name']
        default_sr = dev_info['default_samplerate']
        native = int(round(default_sr))
        g = math.gcd(16000, native)
        up = 16000 // g
        down = native // g

        print(f"[mic] device={name!r} [{dev_api}] (index {dev_index} at pick time, "
              f"re-resolved at open, fenced) native={native}Hz "
              f"resample={up}/{down} -> 16000Hz block=64ms", file=sys.stderr)

        # Setup
        q = queue.Queue(maxsize=64)
        status_count = 0
        drop_count = 0
        heard = {"chunks": 0, "peak": 0.0}
        # Closed segments waiting to be decoded and typed. 32 is far more backlog
        # than a person can create by speaking; if it ever fills, something upstream
        # is wrong and the log says so rather than silently swallowing speech.
        seg_q = queue.Queue(maxsize=32)
        last_status_reported = 0
        last_drop_reported = 0

        # silence_ms was 1000: the segment could not close until a full second of
        # silence had passed, so a whole second of the felt lag before anything is
        # typed was pure waiting, before the ~400 ms decode even started. 600 ms is
        # still longer than a breath inside a sentence, so it should not chop
        # sentences in half. Tunable without a code change.
        #
        # 2026-08-30 01:38 -- Iddo: "יש לו פשוט לג גדול מדי". Measured the whole
        # budget before touching anything, from state\stt-pc.log (n=500 live
        # requests) and the segment dumps: decode p50 472 ms / p90 672 / p99 2065 /
        # max 5566, typing ~0 (typer.type_string is one bulk SendInput, no per-char
        # delay), and this window. End to end, mouth-stop to text on screen, was
        # ~1.5 s typical. Of that, 600 ms -- 40% -- was this constant, spent waiting
        # on a man who had already finished his sentence. Cut to 350: a breath
        # inside a sentence is 200-400 ms, so this is the floor before it starts
        # chopping him mid-thought. If sentences DO start splitting, the honest fix
        # is back to 500, not down further. Set KESHEV_SILENCE_MS to override.
        #
        # What this does NOT fix, and nobody should pretend otherwise: Whisper pays
        # a near-constant cost per clip -- a 1.0 s clip measured 989/448/580/595 ms
        # while a 5.6 s clip measured 704 ms -- so short utterances stay the worst
        # case. The real cure for that is streaming/partial decode, which KESHEV
        # does not do. This is 250 ms off a 1.5 s wall, not a new architecture.
        # 2026-08-30 22:45 -- Iddo: "יש לו לאג אחושרמוטה". MEASURED, and the cause was
        # not the decoder at all:
        #
        #   stt-pc.log, his live requests:  bytes=481280 = 15.04 s, ms=1891/3906/4367
        #
        # EVERY segment was running to the 15 s cap. Twelve seconds of his room, recorded
        # from the BRIO and measured in this gate's own units, explains why:
        #
        #   p5 1026   p50 1187   p95 1352   max 1554      the gate: 300
        #   blocks above the gate: 100.0%
        #
        # The room never falls below the gate, so the segment can never close on silence.
        # It waits the full fifteen seconds, then spends 2-4 s decoding fifteen seconds of
        # audio. His real lag was up to NINETEEN seconds, not the 1.5 s in the record.
        # (The floor is flat -- p5 to p95 spans 30% -- so it is steady broadband noise, a
        # fan or the machine itself. Music would swing far wider.)
        #
        # What is fixed here is only the part that cannot hurt him: the CAP. Five seconds
        # bounds the wait at ~7 s instead of ~19 s and costs nothing but a long unbroken
        # sentence being split, which is recoverable. THE GATE IS DELIBERATELY LEFT AT 300:
        # raising it to 2500 on 2026-08-28 BLOCKED HIS SPEECH and had to be reverted the
        # same morning, and his room now sits at 1187 -- too close to his far-field voice
        # to separate by loudness at all. **Loudness cannot solve this room.** The real
        # cure is to endpoint on vad.voiced_ratio, which the pipeline already computes and
        # the Segmenter still ignores, or to lower the mic's Windows capture level so the
        # room drops below his voice. Both are changes that need his ear on them, not mine.
        # 2026-08-31, Iddo: "סדר את קשב בפעם ה-". The cure this comment block has been
        # prescribing -- "endpoint on vad" -- is now BUILT: segments OPEN only on frames
        # webrtcvad calls voice (the ~1187-RMS fan can no longer open one; it had been
        # opening a 5.06 s segment every ~4 s all day, 1196 "תודה" decodes), and CLOSE
        # after KESHEV_VAD_SILENCE_MS of continuous non-voice even though the room never
        # drops under the 300 gate. 900 ms, not 350: his far-field speech scores only
        # ~0.3 voiced ratio, so short unvoiced runs live INSIDE his sentences.
        # KESHEV_ENDPOINT_VAD=0 gives back yesterday's mic exactly.
        endpoint_vad = os.environ.get("KESHEV_ENDPOINT_VAD", "1").strip() != "0"
        segmenter = Segmenter(min_ms=300,
                              max_ms=int(os.environ.get("KESHEV_MAX_MS", "5000")),
                              silence_ms=int(os.environ.get("KESHEV_SILENCE_MS", "350")),
                              gate=300.0,
                              vad_silence_ms=int(os.environ.get("KESHEV_VAD_SILENCE_MS", "900")) if endpoint_vad else 0)
        gate = ownergate.OwnerGate()
        dump_dir = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "segments"))

        # 2026-09-12 -- WINDOW TARGET LOCK (Iddo 04:12: "בחר יעד: נעילה לחלון").
        # _delivery wraps `typer` and is, byte-for-byte, `typer` itself as long as
        # state\target-lock.json says {"mode":"foreground"} (the default, and
        # today's only behaviour until gui6.py's picker is used). When Iddo locks
        # onto a specific window, _delivery raises THAT window before every burst
        # and restores whatever was in front afterward -- and if the locked window
        # is gone, it signs a PAUSE (same shape the pause button uses) instead of
        # ever typing into a substitute window. See app/wintarget.py.
        _delivery = wintarget.LockAwareTyper(typer, pause_file=PAUSE_FILE)

        # 2026-09-11 -- THE OUTBOX. A refusal is a verdict on the window that
        # happened to have the focus, not on the sentence. Until tonight the
        # sentence was simply dropped (09-03 "types everywhere except the CLI",
        # 09-06 the same again). Now it waits up to 60 s for a window that will
        # take it, and if it never comes it is lost OUT LOUD. See app/outbox.py.
        # 2026-09-12: given _delivery, not raw `typer` -- so a retry after a
        # refusal keeps respecting the SAME lock instead of drifting onto
        # whatever the OS foreground happens to be a second time.
        _outbox = outbox.Outbox(os.path.join(STATE_DIR, "outbox.jsonl"), _delivery)

        # The collector. OFF unless KESHEV_CORPUS=1 -- an absent switch means no.
        _corpus = corpus6.from_env(STATE_DIR)
        if _corpus.enabled:
            print("[corpus] capture ON -> %s" % _corpus.root, file=sys.stderr, flush=True)

        def type_with_enter(text):
            # 2026-09-06: hand the typer's answer back -- a TypeRefusal (falsy) when
            # Windows would have eaten the keys, so handle_block can log it honestly.
            answer = _delivery.type_string(text, auto_enter=AUTO_ENTER)
            if answer is not None and not answer:
                _outbox.submit(text, answer, auto_enter=AUTO_ENTER)
            return answer

        pipeline = SegmentPipeline(
            segmenter,
            decoder.transcribe_hebrew_pcm,
            type_with_enter,
            frame_ms=64,
            owner_gate_fn=gate.identify,
            debug_dump=args.debug_dump,
            dump_dir=dump_dir if args.debug_dump else None,
            rms_floor=RMS_FLOOR,
            vad_fn=vad.voiced_ratio,
            vad_min_ratio=VAD_MIN_RATIO,
            pause_file=PAUSE_FILE,
            defer_queue=seg_q,
            frame_voiced_fn=vad.frame_voiced if endpoint_vad else None,
            corpus=_corpus
        )

        # Strictly FIFO: the oldest closed segment is always decoded and typed first,
        # so what Iddo said first reaches the screen first.
        def decode_worker():
            while True:
                item = seg_q.get()
                if item is None:
                    break
                pcm, peak = item
                try:
                    pipeline.process_full_segment(pcm, peak)
                except Exception as exc:
                    print(f"[segment] decode worker error: {type(exc).__name__}: {exc}",
                          file=sys.stderr)

        threading.Thread(target=decode_worker, daemon=True).start()

        leftover = np.array([], dtype=np.int16)

        def audio_callback(indata, frames, time, status):
            nonlocal status_count, drop_count
            if status:
                status_count += 1
            try:
                q.put_nowait(indata.copy())
            except queue.Full:
                drop_count += 1

        def consumer_worker():
            nonlocal last_status_reported, last_drop_reported, leftover
            while True:
                try:
                    block = q.get()
                    if block is None:
                        break
                    if drop_count != last_drop_reported or status_count != last_status_reported:
                        print(f"[mic] status_events={status_count} dropped_blocks={drop_count}", file=sys.stderr)
                        last_status_reported = status_count
                        last_drop_reported = drop_count
                    resampled = resample_poly(block[:, 0].astype(np.float32), up, down)
                    out16 = np.clip(resampled, -32768, 32767).astype(np.int16)
                    full_block = np.concatenate([leftover, out16])
                    n_samples = len(full_block)
                    n_complete = (n_samples // 1024) * 1024
                    leftover = full_block[n_complete:]
                    to_process = full_block[:n_complete]
                    for i in range(0, len(to_process), 1024):
                        chunk = to_process[i:i+1024]
                        rms = float(np.sqrt(np.mean(chunk.astype(np.float64) ** 2)))
                        heard["chunks"] += 1
                        if rms > heard["peak"]:
                            heard["peak"] = rms
                        pipeline.handle_block(chunk.tobytes(), rms)
                except Exception:
                    continue

        worker_thread = threading.Thread(target=consumer_worker, daemon=True)
        worker_thread.start()

        # Set by the watchdog, cleared by the main loop once the stream is back open.
        reopen = threading.Event()
        recovery = {"reopens": 0, "repick": False}

        # 2026-08-29 -- A mic that hears nothing must SAY SO. On the deaf night the
        # process sat at 4% CPU with an open stream and wrote not one line for 3h45m,
        # and nothing in the log distinguished "empty room" from "wrong device". The
        # log is now never silent: one heartbeat a minute with what actually arrived,
        # and an explicit DEAF verdict when the peak stays at the noise floor. A room
        # with a live mic in it always has a floor above zero -- flat zero is a lie.
        # 2026-09-05 02:05 -- THE SECOND DEAF NIGHT, and the one that showed the gap.
        # At 01:33 the stream was open and delivering nothing, and this watchdog said so
        # PERFECTLY: twelve consecutive "[mic] DEAF" lines, one a minute, each correct.
        # And that is all it did. Iddo lost twelve minutes of speech to a fault the
        # program had already diagnosed, and had to notice himself and ask for a
        # restart -- "תעלה קשב נדפקה".
        #
        # A watchdog that only narrates is not a watchdog. Detection without recovery is
        # the same broken window as `health: ok` on a dead service. So: after two silent
        # minutes it closes and reopens the stream, which re-resolves the device index --
        # and a stale index is the exact documented cause of the 2026-08-29 deaf night.
        # If two reopens do not restore it, the chosen device is genuinely gone and it
        # re-runs the whole fenced pick rather than reopening the same nothing forever.
        DEAF_REOPEN_AFTER = 2      # minutes of silence before closing the stream
        DEAF_REPICK_AFTER = 2      # failed reopens before choosing a different device

        def deaf_watchdog():
            silent_runs = 0
            while True:
                time.sleep(60)
                chunks = heard["chunks"]
                peak = heard["peak"]
                heard["chunks"] = 0
                heard["peak"] = 0.0
                if chunks == 0:
                    silent_runs += 1
                    print(f"[mic] DEAF: no audio blocks arrived in 60s "
                          f"({silent_runs} min running). The stream is open and "
                          f"delivering nothing.", file=sys.stderr)
                elif peak < 5.0:
                    silent_runs += 1
                    print(f"[mic] DEAF: {chunks} blocks in 60s but peak RMS {peak:.1f} "
                          f"-- digital silence, not a quiet room ({silent_runs} min). "
                          f"Wrong device or a dead endpoint.", file=sys.stderr)
                else:
                    if recovery["reopens"]:
                        print(f"[mic] RECOVERED: {chunks} blocks, peak RMS {peak:.0f} "
                              f"-- after {recovery['reopens']} reopen(s).", file=sys.stderr)
                        recovery["reopens"] = 0
                    silent_runs = 0
                    print(f"[mic] heartbeat: {chunks} blocks, peak RMS {peak:.0f}, "
                          f"floor {RMS_FLOOR:.0f}", file=sys.stderr)

                if silent_runs >= DEAF_REOPEN_AFTER and not reopen.is_set():
                    recovery["reopens"] += 1
                    if recovery["reopens"] > DEAF_REPICK_AFTER:
                        recovery["repick"] = True
                        print(f"[mic] {recovery['reopens'] - 1} reopens did not restore "
                              f"audio. Re-running the fenced device pick -- the chosen "
                              f"input is probably gone.", file=sys.stderr)
                    else:
                        print(f"[mic] RECOVERING: deaf {silent_runs} min -- closing and "
                              f"reopening the stream (attempt {recovery['reopens']}). "
                              f"A stale device index is the known cause.", file=sys.stderr)
                    silent_runs = 0
                    reopen.set()
                sys.stderr.flush()

        threading.Thread(target=deaf_watchdog, daemon=True).start()

        # The decoder must be able to answer BEFORE the stream opens. The STT server
        # binds :8737 and logs LISTENING while its models are still loading, and
        # answers 503 LOADING until they are -- 22s on a warm restart, 423s on the
        # cold boot of 2026-08-23. The mic used to capture straight through that
        # window and log every segment as `decode=fail`; seven minutes of speech
        # went in the bin. Now it waits, out loud, and starts deaf to nothing.
        def _report_wait(state, waited):
            nonlocal last_wait_log
            if waited - last_wait_log >= WAIT_LOG_EVERY_S or last_wait_log == 0.0:
                last_wait_log = waited
                print(f"[mic] waiting for the decoder: {state} ({waited:.0f}s)", file=sys.stderr)
                sys.stderr.flush()

        last_wait_log = 0.0
        WAIT_LOG_EVERY_S = 15.0
        decoder.wait_until_ready(poll_s=2.0, on_wait=_report_wait)
        if last_wait_log:
            print("[mic] decoder READY - listening", file=sys.stderr)
        else:
            print("[mic] decoder READY", file=sys.stderr)
        sys.stderr.flush()

        blocksize = int(native * 0.1)
        try:
            live_index = _resolve_now()
            if live_index is None:
                print(f"[mic] {dev_name!r} on {dev_api} has VANISHED since it was picked. "
                      f"Refusing to open whatever took its place.", file=sys.stderr)
                sys.exit(4)
            if live_index != dev_index:
                print(f"[mic] device list shifted: {dev_index} -> {live_index}. "
                      f"Opening the re-resolved index.", file=sys.stderr)
            # Arm the dead-man switch immediately before the microphone opens, so the
            # engine can never outlive the window that owns it (2026-09-01).
            # ONCE, outside the reopen loop -- a recovery must not spawn a second one.
            start_deadman()

            while True:
                try:
                    stream = sd.InputStream(device=live_index, samplerate=native, channels=1,
                                            dtype="int16", blocksize=blocksize,
                                            callback=audio_callback)
                except sd.PortAudioError as exc:
                    # 2026-09-09: a ghost WDM-KS pin answers -9996 'Invalid device'.
                    # Say which device and die cleanly (exit 5) instead of a traceback;
                    # the window restarts a fresh engine, which re-runs the fence.
                    print(f"[mic] could not open {dev_name!r} [{dev_api}] index {live_index}: "
                          f"{exc}. Not opening anything else in its place.", file=sys.stderr)
                    sys.stderr.flush()
                    sys.exit(5)
                with stream:
                    reopen.clear()
                    while not reopen.wait(1.0):
                        pass
                # Out of the `with`, so the stream is now genuinely closed and the
                # device handle released -- which is what lets Windows hand back a
                # working endpoint on the next open.
                if recovery["repick"]:
                    recovery["repick"] = False
                    recovery["reopens"] = 0
                    # PortAudio freezes its device list at initialisation. Without this
                    # a running engine could NEVER see the BRIO come back: tonight's
                    # two engines re-picked from a four-hour-old list and stayed on the
                    # silent dongle. The stream is closed here (we are outside the
                    # `with`), so re-initialising is safe and costs ~1 s.
                    try:
                        sd._terminate()
                        sd._initialize()
                        print("[mic] refreshed the device list before re-picking.",
                              file=sys.stderr)
                    except Exception as exc:
                        print(f"[mic] device-list refresh failed ({type(exc).__name__}: "
                              f"{exc}); re-picking from the old list.", file=sys.stderr)
                    dev_index, dev_info = _pick_input()
                    if dev_info is None:
                        # Not "continue": that re-entered the `while` and reopened the
                        # STALE live_index -- the very device that just went deaf.
                        # Exit 3 = idle_if_no_good_mic; the window starts a fresh
                        # engine every 20 s, which is how a replugged mic gets found.
                        print("[mic] no allowed input device at all after re-pick. "
                              "Staying OFF (idle_if_no_good_mic); the window will retry.",
                              file=sys.stderr)
                        sys.stderr.flush()
                        sys.exit(3)
                    dev_api = sd.query_hostapis()[dev_info['hostapi']]['name']
                    dev_name = dev_info['name']
                    print(f"[mic] re-picked {dev_name!r} [{dev_api}]", file=sys.stderr)

                time.sleep(1.0)
                live_index = _resolve_now()
                if live_index is None:
                    print(f"[mic] {dev_name!r} on {dev_api} is not present right now. "
                          f"Waiting 10s rather than opening whatever took its place.",
                          file=sys.stderr)
                    sys.stderr.flush()
                    time.sleep(10)
                    recovery["repick"] = True
                    reopen.set()
                    continue
                print(f"[mic] reopened on index {live_index}", file=sys.stderr)
                sys.stderr.flush()
        except KeyboardInterrupt:
            print("\nStopping...", file=sys.stderr)
            q.put(None)
            worker_thread.join(timeout=2)


if __name__ == "__main__":
    main()
