"""eran_life.py — the heartbeat of Perceptron Mark II. Living IS learning.

    wake -> school serves a menu -> hunger chooses -> ears hear -> the CORTEX
    learns (every layer from the one below) -> chemistry updates -> (every K
    beats) quick dev-exam -> metrics line -> parent inbox -> sleep pressure ->
    sleep (every layer prunes; a new layer may be BORN) -> beat.

DEPTH (2026-08-21, body/cortex.py): the brain is a Cortex now, not a bare
Brain. ``self.brain`` is still layer 0 — the same object — so the school's
gate, the examiner, the babble and the observation window are untouched. A
single-layer state/brain.json.gz written before depth existed loads and becomes
layer 0 with no rebirth (proof/test_organism.py tests exactly that: ERAN is
alive on eran1 with a real history, and the worst scar in this project is
11.9M steps destroyed).

CRASH-PROOFING (law):
  * single-writer lock on state/.lock — fcntl.flock on Linux (REAL on the
    box); msvcrt fallback on Windows so the tests run on the PC mirror.
  * boot assert — if brain.json.gz's beat is behind metrics.jsonl's last
    beat, REFUSE to start (the 11.9M-step-loss class of death). Recovery is
    explicit and loud: --accept-loss truncates metrics to the brain's beat.
  * every write is atomic (tmp + os.replace); SIGTERM checkpoints and exits.

Flags: --feed-all (bootstrap pass over unit 1) | --live (forever)
       --beats N (bounded) | --ablate ENGINE (chemistry|hunger|sleep|parent)
       --accept-loss (explicit crash recovery)
"""
import argparse
import datetime
import gzip
import json
import os
import shutil
import signal
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "body"))
sys.path.insert(0, os.path.join(ROOT, "voice"))

import genome                                     # noqa: E402
from brain import Brain                           # noqa: E402
from cortex import Cortex                         # noqa: E402
from chemistry import Chemistry                   # noqa: E402
from drives import Drives                         # noqa: E402
from ears import Ears                             # noqa: E402
import parent                                     # noqa: E402
import school as school_mod                       # noqa: E402
import sleep as sleep_mod                         # noqa: E402

# REVISION 2026-09-06 (ERAN-03): a gate that examined fewer than this many
# dev items is not evidence and must never crown best.json.gz. With an empty
# dev split every gate returns dev_top1 0.0, and best_dev started at -1.0 on
# every wake -- so the first blind gate after a restart would overwrite the
# only record of the best-dev brain (2026-08-22, beat 24,476,400) with a
# score that means 'the examiner saw nothing'.
MIN_DEV_ITEMS_FOR_BEST = 20


class StaleBrainError(RuntimeError):
    pass


class SecondWriterError(RuntimeError):
    pass


class FoodEmptyError(RuntimeError):
    pass


# ------------------------------------------------------------------ the lock
def acquire_lock(path=None):
    """Single-writer exclusion. Returns the open handle (hold it for life)."""
    path = path or genome.LOCK_FILE
    os.makedirs(os.path.dirname(path), exist_ok=True)
    handle = open(path, "a+")
    try:
        try:
            import fcntl                          # Linux: the REAL flock
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except ImportError:
            import msvcrt                         # Windows test fallback
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        handle.close()
        raise SecondWriterError(
            f"another writer holds {path} — one organism, one body")
    return handle


# ----------------------------------------------------------------- boot assert
def _last_metrics_beat(metrics_path, block=1 << 20):
    """Highest beat in metrics.jsonl -- read from the END of the file.

    SCAR 2026-09-06 (ERAN-01): this walked and json-parsed EVERY line at wake.
    metrics.jsonl is one line per beat and had reached 54.97 GB (~296M lines,
    186 B/line), growing 3.47 GB/day; measured at 590,898 lines/s that is 8.3
    minutes of parsing (IO excluded) before the first heartbeat. deploy/nanny.sh
    restarted eranb-life whenever the metrics file was older than 900 s, so a
    boot scan that outgrew 15 minutes -- around 99 GB, i.e. mid-September --
    would have made every restart a kill-loop: boot, scan, killed, boot again,
    with no metrics line ever written. serve.py fixed the identical shape for
    page loads on 2026-08-24 (_metrics_tail); the boot path never got it.

    Beats only increase, so the last whole lines hold the maximum. Constant
    time and constant memory however long he lives; the block grows only if the
    tail somehow holds no parseable line, and the answer is then identical to
    the old full scan.
    """
    if not os.path.exists(metrics_path):
        return -1
    size = os.path.getsize(metrics_path)
    while True:
        start = max(0, size - block)
        with open(metrics_path, "rb") as fb:
            fb.seek(start)
            raw = fb.read()
        if start:                                 # first line is probably cut
            nl = raw.find(b"\n")
            raw = raw[nl + 1:] if nl >= 0 else b""
        last = -1
        for line in raw.decode("utf-8", "replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                last = max(last, int(json.loads(line).get("beat", -1)))
            except (ValueError, TypeError):
                continue                          # a torn last line is fine
        if last >= 0 or start == 0:
            return last
        block *= 8


def _drop_metrics_above(metrics_path, brain_beat):
    """Delete every metrics row above `brain_beat` WITHOUT reading the file
    into memory. Returns (bytes_dropped, how).

    2026-09-07: this used to be `kept = []` + `kept.append(line)` over the
    whole file. On the live body state/metrics.jsonl is 58 GB, so the one
    documented recovery from an out-of-memory crash would have caused the
    next one. The guard has to survive the crash it exists to catch.

    Rows are appended in beat order, so the rows to drop are a contiguous
    tail: find where it starts and truncate there. That reads kilobytes,
    not gigabytes. If the tail is NOT clean -- a row at or below the brain's
    beat sitting after one above it -- fall back to a streaming rewrite,
    which is slow and needs room for a second copy, but still never holds
    more than one line at a time."""
    size = os.path.getsize(metrics_path)
    block = 1 << 20
    while True:
        start = max(0, size - block)
        with open(metrics_path, "rb") as fb:
            fb.seek(start)
            raw = fb.read()
        if start:                                  # the first line is cut
            nl = raw.find(b"\n")
            if nl < 0:                             # one enormous line
                block *= 8
                continue
            raw = raw[nl + 1:]
            base = start + nl + 1
        else:
            base = 0
        cut = None
        ordered = True
        pos = base
        for line in raw.split(b"\n"):
            step = len(line) + 1
            text = line.strip()
            if text:
                try:
                    beat = int(json.loads(text).get("beat", -1))
                except (ValueError, TypeError):
                    beat = None                    # a torn line; it stays
                if beat is not None:
                    if beat > brain_beat:
                        if cut is None:
                            cut = pos
                    elif cut is not None:
                        ordered = False
                        break
            pos += step
        if not ordered:
            break                                  # streaming rewrite below
        if cut is not None and cut > base:
            os.truncate(metrics_path, cut)         # the tail, in one call
            return size - cut, "truncate"
        if start == 0:
            if cut == 0:                           # every row is above it
                os.truncate(metrics_path, 0)
                return size, "truncate"
            return 0, "truncate"                   # nothing above the brain
        block *= 8                                 # the tail reaches back

    tmp = metrics_path + ".tmp"
    dropped = 0
    with open(metrics_path, "r", encoding="utf-8") as src, \
            open(tmp, "w", encoding="utf-8") as dst:
        for line in src:                           # one line, never a list
            try:
                keep = int(json.loads(line).get("beat", -1)) <= brain_beat
            except ValueError:
                continue                           # unparseable rows go
            if keep:
                dst.write(line)
            else:
                dropped += len(line.encode("utf-8"))
    os.replace(tmp, metrics_path)
    return dropped, "rewrite"


def boot_assert(brain_path=None, metrics_path=None, accept_loss=False,
                log=print):
    """Refuse to start on a stale brain; --accept-loss reconciles, loudly."""
    brain_path = brain_path or genome.BRAIN_FILE
    metrics_path = metrics_path or genome.METRICS_FILE
    brain_beat = -1
    if os.path.exists(brain_path):
        with gzip.open(brain_path, "rb") as f:
            brain_beat = int(json.loads(f.read().decode("utf-8")).get("beat", 0))
    metrics_beat = _last_metrics_beat(metrics_path)
    if metrics_beat > brain_beat and brain_beat >= 0:
        if not accept_loss:
            raise StaleBrainError(
                f"brain is at beat {brain_beat} but metrics reach beat "
                f"{metrics_beat}: a crash lost work. REFUSING to start. "
                f"Recover explicitly with --accept-loss.")
        dropped, how = _drop_metrics_above(metrics_path, brain_beat)
        log(f"[boot] ACCEPTED LOSS: metrics truncated to beat {brain_beat} "
            f"(was {metrics_beat}), {dropped} bytes dropped by {how}. "
            f"This is recorded, not hidden.")
    if brain_beat < 0 and metrics_beat >= 0:
        if not accept_loss:
            raise StaleBrainError(
                "metrics exist but no brain file: refusing a false rebirth. "
                "Recover explicitly with --accept-loss "
                "(or remove state/ to truly start over).")
        os.replace(metrics_path, metrics_path + ".orphaned")
        log("[boot] ACCEPTED LOSS: no brain file; metrics archived to "
            "*.orphaned and the organism starts over. Recorded, not hidden.")
    return True


# ------------------------------------------------------------------- the life
class Life:
    def __init__(self, ablate=None):
        self.ablate = ablate or []
        self.ears = Ears()                        # crown-aware (life mode)
        self.ears_exam = Ears(exam=True)
        self.chem = Chemistry()
        self.drives = Drives()
        self.school = school_mod.School()
        self._load_organs()
        self.reborn = False
        self.cortex = self._wake_brain()
        if self.reborn:
            # _wake_brain archived curriculum.json, but School() above had
            # ALREADY read it, and the next checkpoint would write the old
            # ladder straight back — a brand-new empty brain believing it had
            # mastered a dozen syllables. Found in review 2026-08-21; it
            # predates depth (School has always been built first) and is fixed
            # here rather than left as a broken window.
            self.school = school_mod.School()
            self._log(f"[wake] curriculum restarted with the new brain: "
                      f"unit {self.school.unit}, mastered "
                      f"{self.school.mastered}")
        # `self.brain` IS layer 0 — the same object, not a copy. Everything
        # written before depth existed (the school's gate, the examiner, the
        # babble, the observation window) keeps working untouched.
        self.brain = self.cortex.layers[0]
        self.beat = self.brain.beat
        self.best_dev = self._load_best_dev()     # ERAN-03: not -1.0 every wake
        self.eaten_since_sleep = 0
        self.famine_beats = 0                     # ERAN-05: beats that ate nothing
        self.stop = False
        if "chemistry" in self.ablate:
            self.chem.frozen = True
        if "hunger" in self.ablate:
            self.drives.ablated = True
        self._assert_food()                       # ERAN-05: refuse a famine

    # ------------------------------------------------------------- the diet
    def _assert_food(self):
        """Refuse to wake with nothing to eat, and say the split out loud.

        SCAR 2026-09-06 (ERAN-05): a session-based dev split classified ALL 657
        food files as exam-only, school.serve_menu() returned an empty list
        every beat, and NOTHING raised -- an empty menu is not an exception, so
        `if item:` fell straight through and the beat wrote a metrics line with
        no 'surprise'. Beats kept flowing at 215/s; he was starving in silence,
        one restart away. A filter that can exclude everything must be named at
        the door, and the counts must be one journal line away next time.
        """
        d = genome.FOOD_TRAIN
        names = ([n for n in os.listdir(d) if n.endswith(".wav")]
                 if os.path.isdir(d) else [])
        dev = [n for n in names if school_mod.measure.is_dev(n)]
        world = len(names) - len(dev)
        unit_n = (len(self.school._unit_wavs(self.school.unit))
                  if self.school.unit else 0)
        self._log(f"[wake] split: {len(names)} wav in {d} -> world/edible "
                  f"{world}, dev/exam {len(dev)} "
                  f"(DEV_SESSION_PICK={genome.DEV_SESSION_PICK} of "
                  f"{genome.DEV_SESSION_MOD}); unit '{self.school.unit}' "
                  f"has {unit_n} edible files")
        if world == 0:
            raise FoodEmptyError(
                f"{len(names)} wav in {d}, and the dev split marks ALL of them "
                f"exam-only (DEV_SESSION_PICK={genome.DEV_SESSION_PICK}, "
                f"DEV_SESSION_MOD={genome.DEV_SESSION_MOD}). The menu would be "
                f"empty every beat and he would starve in silence. REFUSING to "
                f"wake -- this is the 2026-09-06 famine, named at the door.")

    # --------------------------------------------------------- the high-water
    def _best_dev_path(self):
        return os.path.join(genome.STATE_DIR, "best-dev.json")

    def _load_best_dev(self):
        """The best-dev high-water mark, remembered across a restart."""
        try:
            with open(self._best_dev_path(), "r", encoding="utf-8") as f:
                return float(json.load(f).get("best_dev", -1.0))
        except (OSError, ValueError, TypeError):
            return -1.0

    def _save_best(self, gate):
        """Crown a new best -- but never lose the old one silently."""
        if (not os.path.exists(self._best_dev_path())
                and os.path.exists(genome.BEST_FILE)):
            # No recorded high-water mark: the dev score behind the existing
            # best.json.gz was never written down (it dates from 2026-08-22,
            # beat 24,476,400) and this process used to start every wake at
            # best_dev = -1.0, so the first gate of a wake silently replaced
            # it. Keep a copy before crowning anything.
            stamp = datetime.datetime.fromtimestamp(
                os.path.getmtime(genome.BEST_FILE)).strftime("%Y%m%d-%H%M%S")
            arch = os.path.join(genome.STATE_DIR, f"best-{stamp}.json.gz")
            if not os.path.exists(arch):
                shutil.copy2(genome.BEST_FILE, arch)
                self._log(f"[gate] previous best.json.gz kept as "
                          f"{os.path.basename(arch)} -- its dev score was "
                          f"never recorded, so it is not overwritten blind")
        self.brain.beat = self.beat
        self.brain.save(genome.BEST_FILE)
        p = self._best_dev_path()
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"best_dev": self.best_dev, "beat": self.beat,
                       "dev_items": gate.get("dev_items", 0),
                       "ts": datetime.datetime.now().isoformat(
                           timespec="seconds")}, f)
        os.replace(tmp, p)

    # ------------------------------------------------------------- snapshots
    SNAP_KEEP = 24            # newest snap-<beat>.json.gz kept in state/
    SNAP_PRUNE_MAX = 500      # deletions per snap event (never stall a beat)

    def _rotate_snaps(self):
        """Bound state/ -- snapshots nobody loads used to accumulate forever.

        SCAR 2026-09-06 (ERAN-10): snap-<beat>.json.gz is written every
        SNAP_EVERY beats (23 s of wall clock) and NO script in this tree reads
        one; eran-save.sh already keeps 200 verified snapshots elsewhere. They
        had reached 59,470 files (~2.4 GB), and the real cost was not the disk
        but the directory: state/'s inode had grown to 2.8 MB, so every
        listdir/glob of state/ -- the window's journal lookup on each GET,
        every backup, every ls -- walked 59k entries.
        """
        d = genome.STATE_DIR
        try:
            names = [n for n in os.listdir(d)
                     if n.startswith("snap-") and n.endswith(".json.gz")]
        except OSError:
            return
        if len(names) <= self.SNAP_KEEP:
            return

        def _beat_of(n):
            try:
                return int(n[len("snap-"):-len(".json.gz")])
            except ValueError:
                return -1
        names.sort(key=_beat_of)
        for n in names[:-self.SNAP_KEEP][:self.SNAP_PRUNE_MAX]:
            try:
                os.remove(os.path.join(d, n))
            except OSError:
                pass

    def _ear_signature(self):
        return {"repr": self.ears.repr, "n_bands": self.ears.n_bands,
                "pooling": self.ears.pooling, "dim": self.ears.dim}

    def _ear_changed(self):
        """A crowned ear can keep the SAME width and still mean something
        completely different (onset cepstra vs steady cepstra both give 12
        numbers). Prototypes learned through the old ear are nonsense to the
        new one, so the signature — not just the dim — decides rebirth."""
        path = os.path.join(genome.STATE_DIR, "ear-signature.json")
        now = self._ear_signature()
        old = None
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    old = json.load(f)
            except (ValueError, OSError):
                old = None
        os.makedirs(genome.STATE_DIR, exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(now, f, indent=1)
        os.replace(tmp, path)
        return old is not None and old != now, old

    def _wake_brain(self):
        """Wake the whole cortex.

        A single-layer state/brain.json.gz written before depth existed loads
        and BECOMES layer 0 — no rebirth, no archive, no loss. ERAN is alive on
        eran1 right now with a real history; losing it would repeat the worst
        scar in this project (11.9M steps destroyed). Only the ear changing
        still forces a rebirth, exactly as before, and then the whole stack is
        reborn together — layers above 0 are built out of layer 0's
        prototypes, so they are just as blind through a new ear.
        """
        ear_changed, old_sig = self._ear_changed()
        if os.path.exists(genome.BRAIN_FILE):
            b = Brain.load()
            if b.dim != self.ears.dim or ear_changed:
                # the tournament crowned new ears — the old brain cannot see
                # through them. Archive it honestly and be born again.
                stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
                arch = os.path.join(genome.STATE_DIR,
                                    f"brain-dim{b.dim}-{stamp}.json.gz")
                os.replace(genome.BRAIN_FILE, arch)
                # A new brain gets a new life log. Without this the boot
                # assert (which guards the 11.9M-step scar) would read the
                # old brain's beats as work this brain lost, and refuse to
                # wake it forever. Rebirth is not a crash — but nothing is
                # deleted: the old log is archived beside the old brain.
                if os.path.exists(genome.METRICS_FILE):
                    os.replace(genome.METRICS_FILE,
                               os.path.join(genome.STATE_DIR,
                                            f"metrics-dim{b.dim}-{stamp}.jsonl"))
                for stale in (genome.BEST_FILE, genome.CURRICULUM_FILE,
                              genome.CORTEX_FILE):
                    if os.path.exists(stale):
                        os.replace(stale, stale + f".dim{b.dim}-{stamp}")
                self._log(f"[wake] ear changed {old_sig}->"
                          f"{self._ear_signature()}; old brain + life log "
                          f"archived ({os.path.basename(arch)}); REBORN")
                self.reborn = True
                return Cortex(self.ears.dim, log=self._log)
            return Cortex.load(self.ears.dim, log=self._log)
        return Cortex(self.ears.dim, log=self._log)

    def _load_organs(self):
        p = os.path.join(genome.STATE_DIR, "organs.json")
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    s = json.load(f)
                self.chem = Chemistry(s.get("chemistry"))
                self.drives = Drives(s.get("drives"))
            except (ValueError, OSError):
                pass

    def _save_organs(self):
        p = os.path.join(genome.STATE_DIR, "organs.json")
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"chemistry": self.chem.to_state(),
                       "drives": self.drives.to_state()}, f)
        os.replace(tmp, p)

    def _log(self, msg):
        print(msg, flush=True)

    # ---------------------------------------------------------------- metrics
    def _metrics_line(self, extra=None):
        line = {"ts": datetime.datetime.now().isoformat(timespec="seconds"),
                "beat": self.beat, "protos": len(self.brain.protos),
                "mass": round(self.brain.total_mass(), 1),
                "layers": self.cortex.n_layers(),
                "layer_protos": self.cortex.counts(),
                "E": round(self.drives.E, 4), "unit": self.school.unit}
        line.update(self.chem.snapshot())
        if extra:
            line.update(extra)
        os.makedirs(genome.STATE_DIR, exist_ok=True)
        with open(genome.METRICS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")

    # -------------------------------------------------------------- checkpoint
    def checkpoint(self):
        self.brain.beat = self.beat
        self.cortex.beat = self.beat
        self.cortex.save()               # layer 0 to BRAIN_FILE, rest to CORTEX_FILE
        self._save_organs()
        self.school.save()

    # ------------------------------------------------------------ one heartbeat
    def one_beat(self):
        self.beat += 1
        extra = {}
        self.chem.decay()
        if "parent" not in self.ablate:
            taps = parent.check_inbox(self.brain, self.chem, log=self._log)
            if taps:
                extra["taps"] = taps
        menu = self.school.serve_menu(self.chem)
        item = self.drives.choose(menu, self.brain, self.ears)
        if not menu or item is None:
            # ERAN-05: NAME THE FAMINE. This used to fall straight through
            # `if item:` -- no exception, no log line, and a metrics line with
            # no 'surprise'. That silence is exactly how 2026-09-06 nearly
            # ended: an empty menu is not an error to Python, so nothing said
            # he had eaten nothing. Now every such beat is marked, and the
            # first one (and every thousandth) says so out loud.
            extra["ate_nothing"] = ("empty menu" if not menu
                                    else "chooser took nothing from the menu")
            self.famine_beats += 1
            if self.famine_beats == 1 or self.famine_beats % 1000 == 0:
                self._log(f"[life] beat {self.beat} ATE NOTHING "
                          f"({extra['ate_nothing']}); {self.famine_beats} "
                          f"such beats since wake")
        if item:
            try:
                rec = self.cortex.hear_path(self.ears, item["path"],
                                            self.chem, self.beat)
            except (OSError, ValueError) as e:
                # NEVER silent. The old code wrapped only ears.utterance, where
                # a bad wav was the only thing that could fail. This wraps the
                # whole stack, and a structural fault (a layer whose width no
                # longer matches the one below) would otherwise starve the
                # organism forever with no line anywhere saying so — the beat
                # would just quietly stop containing "surprise".
                self._log(f"[life] beat {self.beat} ate nothing: "
                          f"{type(e).__name__}: {e}")
                extra["ate_nothing"] = f"{type(e).__name__}: {e}"
                rec = None
            if rec is not None:
                self.chem.observe(rec["surprise"])
                self.drives.eat_cost()
                self.drives.feed_progress(self.chem.progress(), self.beat)
                self.eaten_since_sleep += 1
                extra["surprise"] = round(rec["surprise"], 4)
                if rec["spawned"]:
                    extra["spawned"] = True
                up = [r for r in rec["layers"][1:] if r.get("spawned")]
                if up:
                    extra["spawned_above"] = [r["layer"] for r in up]
        for layer in self.cortex.layers:
            layer.decay_traces()
        self.drives.tick()

        if self.beat % genome.GATE_EVERY == 0:
            gate = self.school.gate(self.brain, self.ears_exam)
            extra["dev_top1"] = round(gate["dev_top1"], 4)
            if gate["current"]:
                extra["unit_sens"] = round(gate["current"]["sens"], 4)
                extra["unit_spec"] = round(gate["current"]["spec"], 4)
            extra["dev_items"] = gate.get("dev_items", 0)
            # ERAN-03: a blind exam (0 dev items) scores 0.0, which is not a
            # result -- and best_dev used to start at -1.0 every wake, so that
            # 0.0 would have been crowned as the new best on the first gate
            # after a restart, destroying the 2026-08-22 best brain.
            if (gate.get("dev_items", 0) >= MIN_DEV_ITEMS_FOR_BEST
                    and gate["dev_top1"] > self.best_dev):
                self.best_dev = gate["dev_top1"]
                self._save_best(gate)

        slept = False
        if "sleep" not in self.ablate and (
                self.drives.sleep_pressure(self.beat)
                or self.beat % genome.SLEEP_EVERY == 0):
            s = sleep_mod.cycle(self.cortex, self.chem, self.drives, self.ears,
                                self.beat, self.school.unit,
                                self.eaten_since_sleep, log=self._log)
            self.eaten_since_sleep = 0
            extra["sleep_pruned"] = s["pruned"]
            extra["sleep_pruned_per_layer"] = s["pruned_per_layer"]
            if s.get("layer_born"):
                extra["layer_born"] = s["layer_born"]
            slept = True

        if self.beat % genome.BABBLE_EVERY == 0:
            try:
                import voice
                out = voice.babble(self.brain, self.ears)
                if out:
                    extra["babble"] = os.path.basename(out)
            except Exception as e:                # babble must never kill life
                self._log(f"[voice] babble failed honestly: {e}")

        self._metrics_line(extra)
        if self.beat % genome.SAVE_EVERY == 0 or slept:
            self.checkpoint()
        if self.beat % genome.SNAP_EVERY == 0:
            self.brain.beat = self.beat
            self.brain.save(os.path.join(genome.STATE_DIR,
                                         f"snap-{self.beat}.json.gz"))
            self._rotate_snaps()                  # ERAN-10: bound state/

    # ------------------------------------------------------------ feed-all boot
    def feed_all(self):
        """Bootstrap: one pass over unit 1's train wavs (dev excluded)."""
        unit = genome.CURRICULUM[0]
        wavs = self.school._unit_wavs(unit)
        self._log(f"[feed-all] unit '{unit}': {len(wavs)} wavs")
        for p in wavs:
            if self.stop:
                break
            self.beat += 1
            self.chem.decay()
            rec = self.cortex.hear_path(self.ears, p, self.chem, self.beat)
            self.chem.observe(rec["surprise"])
            for layer in self.cortex.layers:
                layer.decay_traces()
            self.drives.eat_cost()
            self.drives.feed_progress(self.chem.progress(), self.beat)
            self._metrics_line({"surprise": round(rec["surprise"], 4),
                                "feed_all": True})
        self.checkpoint()
        self._log(f"[feed-all] done: {self.cortex.counts()} prototypes "
                  f"per layer, beat {self.beat}")

    # -------------------------------------------------------------------- run
    def run(self, beats=None):
        n = 0
        while not self.stop and (beats is None or n < beats):
            self.one_beat()
            n += 1
        self.checkpoint()


def main(argv=None):
    ap = argparse.ArgumentParser(description="the heartbeat")
    ap.add_argument("--feed-all", action="store_true")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--beats", type=int, default=None)
    ap.add_argument("--ablate", action="append", default=[],
                    choices=["chemistry", "hunger", "sleep", "parent"])
    ap.add_argument("--accept-loss", action="store_true")
    ap.add_argument("--state", default=None,
                    help="grow in another state dir (an experiment; the live "
                         "body's state/ is left alone)")
    args = ap.parse_args(argv)

    if args.state:
        genome.use_state_dir(args.state)
        print(f"[life] state dir: {genome.STATE_DIR} (experiment)")

    lock = acquire_lock()                          # held for the process's life
    boot_assert(accept_loss=args.accept_loss)
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
        lock.close()
    print(f"[life] rest at beat {life.beat}; "
          f"{life.cortex.n_layers()} layer(s), {life.cortex.counts()} "
          f"prototypes. good night.")


if __name__ == "__main__":
    main()
