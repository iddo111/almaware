"""darwish_life.py — the heartbeat of Chai the Songbird (חַי הזמיר).

    chemistry decays -> parent taps paid (if any) -> hungry? eat the most
    nutritious unfed shard -> sated? sing 32 bars, hear itself, be judged by
    the corpus-measured critic -> persist -> journal a beat line -> repeat.

Training IS living — there is no separate train.py. `sleep.py` does not exist
yet (v0.2 by design: attrition/scar-decay/chunking are designed, not built);
this loop skips sleep gracefully on its SLEEP_EVERY cadence rather than
importing a module that isn't there.

CRASH-PROOFING:
  * single-writer lock on state/.lock — real fcntl.flock on Linux (eran4);
    on Windows fcntl does not exist, so locking is a documented no-op and the
    process runs unlocked (this is only ever true on the PC, for tests).
  * every persist is atomic: write to a .tmp path, then os.replace().
  * SIGTERM/SIGINT set a stop flag; the current beat finishes, then a final
    checkpoint runs before exit.

ARCHIVE GUARD: assert_not_archive() refuses any path that resolves inside
~/darwish-ai — the archived pipeline stays untouched, enforced in code.

PACING: a beat that neither ate nor sang (energy between the hunger and
satiety lines) is real idle biology, not a bug — but nothing should spin a
CPU core doing nothing thousands of times a second, so an idle beat sleeps
briefly before the next chemistry tick.

REVISION 2026-09-06 — the .bak-rev-20260906 files beside this one are the code
that ran for 16 days:
  DW-01 satiety was arithmetically unreachable (eat only below 0.4, a meal adds
        <= 0.15, singing needs > 0.8): 12,092 meals, ONE song, and every feedback
        path behind singing dark for the whole life with no log line. Fixed by
        feeding hysteresis in drives.py, a boot gate, a song cadence cap, outbox
        rotation and a no-song liveness warning.
  DW-02 the meal was ranked[0] and the winner's nutrition never fell, so 97% of
        all meals were one track. The meal is now drawn, not argmaxed.
  DW-04 serotonin moved only on a human tap, and no tap was ever written, so mood
        was a constant 0.5; the critic's own verdict now moves it at a reduced
        gain.
  DW-07 a line was journalled every beat (237 MB, 99.3% idle, no rotation);
        events plus a heartbeat are journalled instead, rotating daily.

Flags:
  --feed-all        bootstrap: eat every train shard once (nutrition-ranked),
                     honoring split.json (heldout is NEVER fed), then measure
                     the critic's set-points from the same train split.
  --live            forever loop (the real life), until SIGTERM/SIGINT.
  --beats N         bounded loop of N heartbeats (tests, smoke runs).
  --ablate ENGINE   da | hunger | critic | parent — orchestration-level
                     ablation of one of the six biology engines (see
                     DESIGN.md §6); repeatable.
"""
import argparse
import collections
import datetime
import json
import os
import random
import signal
import sys
import time

for _stream in (sys.stdout, sys.stderr):           # Hebrew/emoji-safe console
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "body"))
sys.path.insert(0, os.path.join(ROOT, "voice"))

import genome                                     # noqa: E402
from brain import Brain                           # noqa: E402
from chemistry import Chemistry                   # noqa: E402
from drives import Drives, assert_satiety_reachable  # noqa: E402
from ears import Ears                              # noqa: E402
from critic import Critic, measure_setpoints       # noqa: E402
import voice                                       # noqa: E402
import midi_out                                    # noqa: E402
import synth                                       # noqa: E402
import parent                                      # noqa: E402
try:
    import psy_synth                                # noqa: E402 — the real voice (numpy/scipy; NOT the brain)
except ImportError as _e:                           # eran4 always has numpy+scipy; guard anyway
    psy_synth = None
    print(f"[life] psy_synth unavailable ({_e}); falling back to body/synth.py only", flush=True)

# --- the tree (repo-root-relative; identical on the PC mirror and on eran4) --
FOOD_DIR = os.path.join(ROOT, "food")
SPLIT_PATH = os.path.join(FOOD_DIR, "split.json")
STATE_DIR = os.path.join(ROOT, "state")
BRAIN_FILE = os.path.join(STATE_DIR, "brain.json.gz")
ORGANS_FILE = os.path.join(STATE_DIR, "organs.json")
METRICS_FILE = os.path.join(STATE_DIR, "metrics.jsonl")
SETPOINTS_PATH = os.path.join(STATE_DIR, "setpoints.json")
LOCK_FILE = os.path.join(STATE_DIR, ".lock")
OUTBOX_DIR = os.path.join(ROOT, "songs", "outbox")
INBOX_DIR = os.path.join(ROOT, "feedback", "inbox")
RESULTS_DIR = os.path.join(ROOT, "results")

IDLE_SLEEP_S = 0.25          # pacing: an idle beat (neither ate nor sang) rests


class SecondWriterError(RuntimeError):
    pass


# ------------------------------------------------------------- archive guard
def assert_not_archive(*paths):
    """Refuse any path resolving inside ~/darwish-ai. Enforced in code, not memory."""
    bad = os.path.normpath(os.path.abspath(os.path.expanduser(os.path.join("~", "darwish-ai"))))
    for p in paths:
        rp = os.path.normpath(os.path.abspath(p))
        if rp == bad or rp.startswith(bad + os.sep):
            raise RuntimeError(
                f"archive path-guard: refusing to touch {rp} — "
                f"~/darwish-ai is read-only, adopted by cp, never written to")


# ------------------------------------------------------------------ the lock
def acquire_lock(path=None):
    """Single-writer exclusion. Returns the open handle — hold it for life."""
    path = path or LOCK_FILE
    assert_not_archive(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    handle = open(path, "a+")
    try:
        import fcntl                              # Linux (eran4): the REAL lock
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            raise SecondWriterError(
                f"another writer holds {path} — one bird, one body")
    except ImportError:
        pass                                       # Windows: no-op so tests run
    return handle


def _log(msg):
    print(msg, flush=True)


# ------------------------------------------------------------------- the life
class Life:
    def __init__(self, ablate=None):
        self.ablate = ablate or []
        # DW-01: refuse to boot a genome in which the bird can never be sated.
        # That is the failure that ran silently for 1.68 M beats; a gate that can
        # actually refuse is the only proof it will not run silently again.
        ceiling = assert_satiety_reachable()
        _log(f"[life] satiety gate: a meal lifts E by <= {genome.EAT_GAIN_MAX} "
             f"(ceiling {ceiling:.2f} without hysteresis), satiety line "
             f"{genome.SATIETY_LINE}, hysteresis={genome.EAT_HYSTERESIS}")
        if not os.path.exists(SPLIT_PATH):
            raise SystemExit(
                f"[life] no {SPLIT_PATH} — run prep/adopt_archive.sh on eran4 first "
                f"(adopts food/*.json + split.json read-only out of ~/darwish-ai)")
        self.ears = Ears(FOOD_DIR, SPLIT_PATH)
        self.brain = self._wake_brain()
        (self.chem, self.drives, self.beat, self.tokens_eaten,
         self._song_gate) = self._wake_organs()
        self.critic = self._wake_critic()
        self.tokens_since_save = 0
        self._seq_idx = 0
        self.stop = False
        self._rng = random.Random(genome.SEED)                      # DW-02
        self._recent = collections.deque(maxlen=genome.MEAL_RECENT_EXCLUDE)
        self._diet = collections.deque(maxlen=genome.DIET_WINDOW)
        self._songs = 0
        self._song_warn_beat = self.beat                            # DW-01
        self._sht_ring = collections.deque(maxlen=10)               # DW-04
        self._last_metrics_ts = 0.0                                 # DW-07
        self._metrics_day = datetime.date.today().isoformat()
        if "da" in self.ablate:
            # DA never updates: plasticity_gain() == ach*(1+0), i.e. flat
            # Hebbian counts — the ablated lattice baseline (§6, engine 2).
            self.chem.observe_surprise = lambda bits: None

    # ---------------------------------------------------------------- wake
    def _wake_brain(self):
        if os.path.exists(BRAIN_FILE):
            return Brain.load(BRAIN_FILE)
        return Brain()

    def _wake_organs(self):
        chem_state = drives_state = None
        beat = tokens_eaten = 0
        song_gate = {}
        if os.path.exists(ORGANS_FILE):
            try:
                with open(ORGANS_FILE, "r", encoding="utf-8") as f:
                    s = json.load(f)
                chem_state = s.get("chemistry")
                drives_state = s.get("drives")
                beat = int(s.get("beat", 0))
                tokens_eaten = int(s.get("tokens_eaten", 0))
                song_gate = dict(s.get("song_gate") or {})    # DW-01 cadence cap
            except (OSError, ValueError):
                pass
        return (Chemistry(chem_state), Drives(drives_state), beat, tokens_eaten,
                song_gate)

    def _wake_critic(self):
        if os.path.exists(SETPOINTS_PATH):
            try:
                return Critic(SETPOINTS_PATH)
            except (OSError, ValueError) as e:
                _log(f"[life] setpoints.json unreadable ({e}); critic silent")
        else:
            _log("[life] no setpoints.json yet; the closed feedback loop is silent "
                 "until --feed-all measures it")
        return None

    # ---------------------------------------------------------------- persist
    def _atomic_write_json(self, path, obj):
        assert_not_archive(path)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False)
        os.replace(tmp, path)

    def _save_brain(self):
        assert_not_archive(BRAIN_FILE)
        os.makedirs(STATE_DIR, exist_ok=True)
        tmp = BRAIN_FILE + ".tmp"
        self.brain.save(tmp)
        os.replace(tmp, BRAIN_FILE)

    def _save_organs(self):
        self._atomic_write_json(ORGANS_FILE, {
            "chemistry": self.chem.to_state(),
            "drives": self.drives.to_state(),
            "beat": self.beat,
            "tokens_eaten": self.tokens_eaten,
            "song_gate": self._song_gate,
        })

    def checkpoint(self):
        os.makedirs(STATE_DIR, exist_ok=True)
        self._save_brain()
        self._save_organs()
        self.tokens_since_save = 0

    def _metrics_line(self, extra=None, force=False):
        """DW-07: journal EVENTS plus a heartbeat — not every beat.

        The old code wrote one line per beat: 1,678,809 lines / 237 MB, of which
        1,666,716 (99.3%) were idle beats that said nothing new, never rotated
        and never pruned. Same file, same schema; only the silence is dropped.
        """
        now = time.time()
        eventful = bool(extra)
        if not (eventful or force
                or now - self._last_metrics_ts >= genome.METRICS_HEARTBEAT_S):
            return
        line = {"ts": datetime.datetime.now().isoformat(timespec="seconds"),
                "beat": self.beat, "mass": self.brain.mass,
                "E": round(self.drives.E, 4), "da": round(self.chem.da, 4),
                "sht": round(self.chem.sht, 4), "ach": round(self.chem.ach, 4),
                "tokens_eaten": self.tokens_eaten}
        if not eventful:
            line["heartbeat"] = True
        if self.ablate:
            line["ablate"] = list(self.ablate)
        if extra:
            line.update(extra)
        assert_not_archive(METRICS_FILE)
        os.makedirs(STATE_DIR, exist_ok=True)
        self._roll_metrics_day()
        with open(METRICS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
        self._last_metrics_ts = now

    def _roll_metrics_day(self):
        """Daily rotation (DW-07). The closed day is MOVED to
        state/metrics-<date>.jsonl — never deleted, never overwritten."""
        today = datetime.date.today().isoformat()
        if today == self._metrics_day:
            return
        closed, self._metrics_day = self._metrics_day, today
        if not os.path.exists(METRICS_FILE):
            return
        dest = os.path.join(STATE_DIR, "metrics-%s.jsonl" % closed)
        if os.path.exists(dest):
            return
        try:
            os.replace(METRICS_FILE, dest)
            _log(f"[life] metrics rotated -> {os.path.basename(dest)}")
        except OSError as e:
            _log(f"[life] metrics rotate failed: {e}")

    # ------------------------------------------------------------- appetite
    def _pick_meal(self):
        names = self.ears.train
        if not names:
            return None
        if "hunger" in self.ablate:                # flat sequential diet, no ranking
            name = names[self._seq_idx % len(names)]
            self._seq_idx += 1
            return name
        ranked = self.drives.probe_appetite(self.brain, self.ears, names)
        if not ranked:
            return names[0]
        # DW-02: DRAW the meal. `ranked[0][1]` ate one shard 11,724 times in 15
        # days because that shard's nutrition never fell — an argmax over a
        # fixed point is not a curriculum.
        name = self.drives.choose_meal(
            ranked, recent=self._recent, counts=collections.Counter(self._diet),
            temperature=self.chem.temperature(), rng=self._rng)
        return name or ranked[0][1]

    def _note_meal(self, name):
        self._recent.append(name)
        self._diet.append(name)

    def _log_diet(self):
        """DW-02: say what the bird is actually eating, and warn on collapse."""
        if not self._diet:
            return
        counts = collections.Counter(self._diet)
        total = sum(counts.values())
        top = counts.most_common(5)
        _log("[life] diet (last %d meals, %d distinct): %s" % (
            total, len(counts),
            ", ".join("%.0f%% %s" % (100.0 * n / total, os.path.basename(nm)[:38])
                      for nm, n in top)))
        nm, n = top[0]
        if total >= genome.DIET_WINDOW_MIN and n / total > genome.DIET_DOMINANCE_CAP:
            _log("[life] WARNING: %.0f%% of the last %d meals were one shard "
                 "(%s) — curriculum collapse"
                 % (100.0 * n / total, total, os.path.basename(nm)[:60]))

    def _eat_shard(self, name):
        bits = []
        for tok, phase in self.ears.feed(name):
            b = self.brain.digest(tok, phase, self.chem, learn=True)
            bits.append(b)
        nutrition = self.drives.nutrition_of_bits(bits)
        self.drives.eat(nutrition)
        self.tokens_since_save += len(bits)
        self.tokens_eaten += len(bits)
        return bits, nutrition

    # ---------------------------------------------------------------- voice
    def _sing_and_audition(self):
        song_id = f"chai-{datetime.datetime.now():%Y%m%d-%H%M%S}"
        tokens, trace = voice.sing(self.brain, self.chem, bars=genome.SONG_BARS)
        os.makedirs(OUTBOX_DIR, exist_ok=True)
        assert_not_archive(OUTBOX_DIR)
        voice.save_song(song_id, tokens, trace, OUTBOX_DIR)
        midi_path = os.path.join(OUTBOX_DIR, song_id + ".mid")
        wav_path = os.path.join(OUTBOX_DIR, song_id + ".wav")
        basic_wav_path = os.path.join(OUTBOX_DIR, song_id + "-basic.wav")
        midi_out.write(midi_path, tokens)
        if psy_synth is not None:
            bpm = psy_synth.corpus_bpm()
            synth.render(basic_wav_path, tokens, bpm=bpm)   # old renderer: kept as fallback
            dur = psy_synth.render(wav_path, tokens, bpm=bpm)  # the real psytrance voice
        else:
            dur = synth.render(wav_path, tokens)             # numpy/scipy missing: old only
        self.drives.sing_cost()
        extra = {"sang": song_id, "duration_s": round(dur, 1), "bars": genome.SONG_BARS}
        if "critic" not in self.ablate and self.critic is not None:
            old_ach = self.chem.ach
            self.chem.mode(genome.ACH_AUDIT)        # hearing itself: mild attention
            for tok, phase in self.ears.audition(tokens):
                self.brain.digest(tok, phase, self.chem, learn=True)
            valence, detail = self.critic.judge(tokens)
            paid, missing = self.brain.pay_trace(trace, valence, genome.ETA0, self.chem)
            # DW-04: serotonin used to move ONLY on a human tap, and no tap was
            # ever written, so mood was a constant 0.5 and the sampling
            # temperature a constant 1.0 for the entire life. The bird's own
            # verdict now moves it too, at CRITIC_VALENCE_GAIN of a father's.
            self.chem.critic_valence(valence)
            self.chem.mode(old_ach)
            extra["critic_valence"] = round(valence, 3)
            extra["critic_detail"] = detail
            extra["audition_paid"] = paid
            extra["sht"] = round(self.chem.sht, 4)
        self._rotate_outbox()
        return extra

    # ------------------------------------------------------ DW-01 cadence cap
    def _song_allowed(self, now=None):
        """Rate-limit the voice. With DW-01 fixed the bird reaches satiety every
        ~3 meals — ~1,300 songs/day, each a full psy_synth render, on a box
        with no free memory. Sing rarely and mean it."""
        now = time.time() if now is None else now
        day = datetime.date.fromtimestamp(now).isoformat()
        gate = self._song_gate
        if gate.get("day") != day:
            gate["day"], gate["count"] = day, 0
        if int(gate.get("count", 0)) >= genome.SONG_MAX_PER_DAY:
            return False
        return now - float(gate.get("last_ts") or 0.0) >= genome.SONG_MIN_INTERVAL_S

    def _note_song(self, now=None):
        now = time.time() if now is None else now
        self._song_gate["count"] = int(self._song_gate.get("count", 0)) + 1
        self._song_gate["last_ts"] = now
        self._songs += 1

    def _rotate_outbox(self):
        """Keep songs/outbox bounded — and with it the tap page (DW-01/DW-05).
        Older songs are MOVED to songs/older/, never deleted."""
        try:
            names = os.listdir(OUTBOX_DIR)
        except OSError:
            return
        ids = sorted({n.split(".")[0].replace("-basic", "")
                      for n in names if n.startswith("chai-")})
        if len(ids) <= genome.OUTBOX_KEEP:
            return
        older = os.path.join(ROOT, "songs", "older")
        assert_not_archive(older)
        os.makedirs(older, exist_ok=True)
        moved = 0
        for sid in ids[:-genome.OUTBOX_KEEP]:
            for n in [x for x in names if x.startswith(sid)]:
                try:
                    os.replace(os.path.join(OUTBOX_DIR, n),
                               os.path.join(older, n))
                    moved += 1
                except OSError as e:
                    _log(f"[life] outbox rotate: cannot move {n}: {e}")
        if moved:
            _log(f"[life] outbox rotated: {moved} files from "
                 f"{len(ids) - genome.OUTBOX_KEEP} old songs -> songs/older/ "
                 f"(keeping the newest {genome.OUTBOX_KEEP})")

    # ------------------------------------------------------- liveness checks
    def _liveness_checks(self, extra):
        """A dead signal must SAY it is dead — the whole lesson of this pass.
        The bird sang once in 1,678,809 beats and serotonin never left 0.5, and
        not one line in 237 MB of metrics said so."""
        if "sang" in extra:
            self._song_warn_beat = self.beat
        elif self.beat - self._song_warn_beat >= genome.SONG_SILENCE_WARN_BEATS:
            self._song_warn_beat = self.beat
            _log(f"[life] WARNING: no song in {genome.SONG_SILENCE_WARN_BEATS} "
                 f"beats (E={self.drives.E:.3f}, satiety {genome.SATIETY_LINE}, "
                 f"feeding={self.drives.feeding}) — critic, trace payout, taps "
                 f"and serotonin are all dark behind it")
            extra["warn_no_song"] = genome.SONG_SILENCE_WARN_BEATS
        if self.beat % 1000 == 0:
            self._sht_ring.append(round(self.chem.sht, 6))
            if (len(self._sht_ring) == self._sht_ring.maxlen
                    and len(set(self._sht_ring)) == 1 and self._songs > 0):
                _log(f"[life] WARNING: serotonin has not moved in "
                     f"{1000 * self._sht_ring.maxlen} beats "
                     f"(sht={self.chem.sht}) across {self._songs} songs — "
                     f"mood is a dead signal")
                extra["warn_flat_mood"] = round(self.chem.sht, 4)
                self._sht_ring.clear()

    # ------------------------------------------------------------ one beat
    def one_beat(self):
        self.beat += 1
        extra = {}
        self.chem.decay_toward_baseline()

        if "parent" not in self.ablate:
            paid = parent.pay_taps(self.brain, self.chem, INBOX_DIR, OUTBOX_DIR, log=_log)
            if paid:
                extra["taps_paid"] = paid

        did_work = False
        # DW-01: should_eat() carries the feeding bout. `self.drives.hungry`
        # alone capped E at 0.55, which made the `sated` branch below dead code
        # for 1,678,853 live beats — no exception, no log line.
        if self.drives.should_eat():
            name = self._pick_meal()
            if name:
                bits, nutrition = self._eat_shard(name)
                self._note_meal(name)
                extra.update({"ate": name, "tokens": len(bits),
                             "nutrition": round(nutrition, 3)})
                did_work = True
            else:
                extra["warn_empty_menu"] = len(self.ears.train)
                _log("[life] WARNING: hungry and the menu is EMPTY "
                     f"({len(self.ears.train)} train shards visible) — "
                     f"that is starvation, not idleness")
        elif self.drives.should_sing() and self._song_allowed():
            extra.update(self._sing_and_audition())
            self._note_song()
            did_work = True

        self.drives.tick()
        self._liveness_checks(extra)
        self._metrics_line(extra)

        if self.beat % genome.SLEEP_EVERY == 0:
            _log(f"[life] beat {self.beat}: sleep skipped — sleep.py not built yet "
                 f"(v0.2 by design: attrition/scar-decay/chunking)")
            self._log_diet()

        if self.tokens_since_save >= genome.SAVE_EVERY or "sang" in extra:
            self.checkpoint()

        if not did_work:
            time.sleep(IDLE_SLEEP_S)                # pacing: don't spin an idle core

    # ------------------------------------------------------------ feed-all boot
    def feed_all(self):
        """Bootstrap: one nutrition-ranked pass over every train shard, once each.
        Then measure the critic's corpus set-points from the same train split."""
        names = list(self.ears.train)
        self._log_feed_all_start(len(names))
        ranked = self.drives.probe_appetite(self.brain, self.ears, names)
        order = [name for _, name in ranked] if ranked else names
        t0 = time.time()
        for name in order:
            if self.stop:
                break
            self.beat += 1
            self.chem.decay_toward_baseline()
            bits, nutrition = self._eat_shard(name)
            self._metrics_line({"ate": name, "tokens": len(bits),
                                "nutrition": round(nutrition, 3), "feed_all": True})
            if self.tokens_since_save >= genome.SAVE_EVERY:
                self.checkpoint()
        wall = time.time() - t0
        self.checkpoint()
        os.makedirs(STATE_DIR, exist_ok=True)
        assert_not_archive(SETPOINTS_PATH)
        sp = measure_setpoints(self.ears, self.ears.train, SETPOINTS_PATH)
        self.critic = Critic(SETPOINTS_PATH)
        _log(f"[feed-all] done: {len(order)} shards, {self.tokens_eaten} tokens, "
             f"{self.brain.mass} synapses, {wall:.1f}s wall-clock; "
             f"setpoints measured from {sp['n_tracks']} train tracks -> "
             f"{SETPOINTS_PATH}")

    def _log_feed_all_start(self, n):
        _log(f"[feed-all] ranking + eating {n} train shards "
             f"(heldout + excluded skipped by split.json)")

    # -------------------------------------------------------------------- run
    def run(self, beats=None):
        n = 0
        while not self.stop and (beats is None or n < beats):
            self.one_beat()
            n += 1
        self.checkpoint()


def main(argv=None):
    ap = argparse.ArgumentParser(description="Chai the Songbird — the heartbeat")
    ap.add_argument("--feed-all", action="store_true")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--beats", type=int, default=None)
    ap.add_argument("--ablate", action="append", default=[],
                    choices=["da", "hunger", "critic", "parent"])
    args = ap.parse_args(argv)

    lock = acquire_lock()                           # held for the process's life
    try:
        life = Life(ablate=args.ablate)

        def _term(signum, frame):
            life.stop = True
        signal.signal(signal.SIGTERM, _term)
        signal.signal(signal.SIGINT, _term)

        try:
            if args.feed_all:
                life.feed_all()
            if args.live:
                life.run(None)
            elif args.beats:
                life.run(args.beats)
        finally:
            life.checkpoint()
        _log(f"[life] rest at beat {life.beat}; {life.brain.mass} synapses, "
             f"{life.tokens_eaten} tokens eaten. good night.")
    finally:
        lock.close()


if __name__ == "__main__":
    main()
