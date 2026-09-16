"""THE EASEL — WINSTON's anatomy as a weave, in painting vocabulary.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

לזכרה של עלמה ז"ל. This is the organ itself: the painting PROCESS as loom
semantics, not a loom standing guard over torch. What each piece of the weave
IS, with no metaphor debt:

  stroke waking     the clock->s_### strand's weight IS the opacity; the daub
                    knot's trigger is `rise theta`, so a cord thinned below
                    theta stops waking at its own delay — pruning is a
                    run-time weave event, not a mask in a tensor. (The loom
                    integrates: sub-theta sparks accumulate in the tray, so a
                    cord needs to fall below theta/sum(anneal) before it can
                    never wake at all. That is temporal integration, ALMA's own
                    §6, and it is documented rather than fenced.)
  order             delay is distance: stroke i wakes at its own beat, bands
                    are delay blocks, and compositing in fire order IS
                    winston's back-to-front z.
  coarse->fine      pure topology: mid_clock is wired from coarse_done, which
                    fires only when the underpainting EARNED `rise T` of vetted
                    improvement — or when the patience strand (weight T, delay
                    D_patience) arrives as mercy. Mid physically cannot start
                    early.
  anneal            one cord speaking R times into the future: the clock->s
                    thread carries R strands at delays d, d+N, d+2N with
                    decreasing weights. Fire 1 places, fires 2..R wiggle with
                    magnitude proportional to the arriving spark.
  keep/revert       w_### (verb=sum, trigger `rise eps`) fires only when the
                    daub's answered improvement crosses eps; settle_### commits
                    the stage. REVERT IS THE DEFAULT — an unvetted stage dies.
  lifetime merit    the s_###->w_### strand carries drift>0. It hangs THERE
                    and not on the way into the spell, because the loom counts
                    silent fires as fired (loom.py LEARN, `fired_now` from
                    fires-this-beat — pinned by tests/test_organ.py's canary):
                    a spell that fires uselessly would still thicken a cord
                    into itself. w_### fires only on vetted improvement, so its
                    drift is real merit. Easel transcribes Result.learned into
                    the next sitting's opacity strands — the documented ALMA
                    learning loop, no gradient anywhere.
  refractory        each <band>_done has a self-strand of weight -1e6: its own
                    fire drives its tray far negative, so a done fires once.
                    Subtraction as inhibition — arithmetic in the connections.
  judgement         fine_done wakes four verdict spells that compute BLANK /
                    BLUR / BUSY / chroma INSIDE themselves (honest floors) and
                    answer one fringe scalar each.
  the alarm         a gate keyed on -busy_gap: it FIRES when the painting's
                    busy tenth is strictly worse than a flat colour's — the
                    vanished-person scar of 08-31 as STRUCTURE, not a print.
  the show gate     keyed on beats_blank: the painting presents itself to
                    behold/hear_back only if it beat a flat colour. The weave
                    refuses to show father a painting worse than BLANK.

Numbers a sitting prints are measured on the finished canvas every run, in the
winston.py voice: PASSES or FAILS, all the floors, whichever way they go.
"""
from __future__ import annotations

import json
import os
import sys
import time

import numpy as np

_ALMA = "D:/CLAUDE/alma-language"
if _ALMA not in sys.path:
    sys.path.insert(0, _ALMA)

from alma import Loom, Strand, Weave, spells, to_dict          # noqa: E402

from atelier import Atelier, pen_check                         # noqa: E402
import brushes                                                 # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))

BIG_INHIBIT = -1e6        # the refractory self-strand on every <band>_done
MERIT_FLOOR = 0.0         # a merit cord may thin to nothing, never below
MERIT_CEIL = 4.0          # and may not eat the weave
OP_MAX = 1.0              # opacity ceiling after transcription


def _anneal(r: int) -> list[float]:
    """Decreasing voices of the wiggle cord: 1.0, 0.62, 0.62^2, ..."""
    return [0.62 ** k for k in range(r)]


class Easel:
    """Builds and runs WINSTON's weave over one Atelier; learns across sittings.

    `bands` are explicit sizes (coarse, mid, fine) summing to n_strokes.
    `gaze` is None (the painting keeps to itself), or a dict with callables
    for "propose", "behold", "hear_back" — stubs.py's fakes on the PC,
    gaze.py's frozen torch forwards on eran3/4. When gaze is present the weave
    gains muse (propose) before the first clock and behold/hear_back behind
    the show gate.
    """

    def __init__(self, subject, n_strokes: int = 400,
                 bands: tuple[int, int, int] | None = None,
                 r_fires: int = 3, theta: float = 0.05, eps: float = 1e-5,
                 drift: float = 0.08, size: int | None = None,
                 seed: int = 1933, gaze: dict | None = None,
                 name: str = "winston", out_dir: str | None = None,
                 detail_w: float = 3.0, colour_w: float = 1.5):
        if bands is None:
            c = max(1, round(n_strokes * 0.125))
            m = max(1, round(n_strokes * 0.25))
            bands = (c, m, n_strokes - c - m)
        assert sum(bands) == n_strokes, (bands, n_strokes)
        self.n = int(n_strokes)
        self.bands = tuple(int(b) for b in bands)
        self.r = int(r_fires)
        self.theta = float(theta)
        self.eps = float(eps)
        self.drift = float(drift)
        self.seed = int(seed)
        self.gaze = gaze
        self.name = name
        self.out_dir = out_dir or os.path.join(HERE, "weaves")
        self.atelier = Atelier(subject, self.n, size=size, seed=seed,
                               detail_w=detail_w, colour_w=colour_w)
        if gaze == "stub":                     # loud fakes; see stubs.py
            import stubs
            self.gaze = gaze = stubs.stub_gaze(self.atelier)
        self.opacity = np.ones(self.n)
        self.sittings = 0
        self.last_result = None
        # band bookkeeping: name, global index range, rise threshold
        self.band_names = ("coarse", "mid", "fine")
        ofs = np.cumsum((0,) + self.bands)
        self.band_range = {b: (int(ofs[k]), int(ofs[k + 1]))
                           for k, b in enumerate(self.band_names)}
        self.band_rise = {b: self.eps * max(1, self.bands[k]) * 4.0
                          for k, b in enumerate(self.band_names)}
        # schedule: patience delays and the horizon (see _schedule)
        self._schedule()
        self._merit_slot: dict[int, int] = {}

    # -- timing: distance IS time, so the schedule is plain arithmetic

    def _schedule(self) -> None:
        base = 3 + (1 if self.gaze else 0)      # look(1) tension(2) [muse] clock
        r = self.r
        self.dp = {}
        prev = base
        for k, band in enumerate(("coarse", "mid", "fine")):
            nb = self.bands[k]
            # wiggle voices are spaced max(3, band) beats apart so a trial's
            # settle (fires + 2 beats) always lands before the NEXT trial of
            # the same stroke would discard its stage
            last_fire = nb + (r - 1) * max(3, nb)
            self.dp[band] = prev + last_fire + 3
            prev = self.dp[band] + 1
        # patience ARRIVES at beat 1 + dp[band]; the horizon leaves room for
        # verdicts (+2), gates (+2) and the gaze echoes (+2).
        self.patience_beat = {b: 1 + d for b, d in self.dp.items()}
        self.horizon = self.patience_beat["fine"] + 8

    # -- the weave, rebuilt fresh every sitting with the current opacities

    def weave(self) -> Weave:
        w = Weave(self.name)
        self._merit_slot = {}
        strands_so_far = 0

        def add_thread(src, dst, port="in", strands=None):
            nonlocal strands_so_far
            ss = strands or [Strand()]
            w.thread(src, dst, port, ss)
            first = strands_so_far
            strands_so_far += len(ss)
            return first

        # the subject enters: look wears the painting's WHAT on its bearing
        w.knot("look", verb="pass")
        w.knot("tension", verb="spell", spell="see")
        add_thread("look", "tension", strands=[Strand(
            weight=1.0, delay=1, tint="subject",
            bearing=self.atelier.subject_path)])
        first_clock = "coarse_clock"
        if self.gaze:
            w.knot("muse", verb="spell", spell="propose")
            add_thread("tension", "muse", strands=[Strand(weight=1.0, delay=1)])
            add_thread("muse", first_clock, strands=[Strand(weight=0.0, delay=1)])
        else:
            add_thread("tension", first_clock,
                       strands=[Strand(weight=0.0, delay=1)])

        anneal = _anneal(self.r)
        prev_done = None
        for k, band in enumerate(self.band_names):
            clock, done = band + "_clock", band + "_done"
            lo, hi = self.band_range[band]
            w.knot(clock, verb="pass", bias=1.0)
            w.knot(done, verb="sum", trigger="rise %g" % self.band_rise[band])
            if prev_done is not None:
                add_thread(prev_done, clock,
                           strands=[Strand(weight=0.0, delay=1)])
            # the mercy: patience from look, weight = the rise line itself
            add_thread("look", done, strands=[Strand(
                weight=self.band_rise[band], delay=self.dp[band],
                tint="patience")])
            # the refractory: a done that spoke inhibits itself for good
            add_thread(done, done, strands=[Strand(weight=BIG_INHIBIT, delay=1)])
            n_band = hi - lo
            for j, i in enumerate(range(lo, hi)):
                s, ww, t = "s_%03d" % i, "w_%03d" % i, "t_%03d" % i
                w.knot(s, verb="spell", spell="daub_%03d" % i,
                       trigger="rise %g" % self.theta)
                w.knot(ww, verb="sum", trigger="rise %g" % self.eps)
                w.knot(t, verb="spell", spell="settle_%03d" % i)
                # the wiggle cord: R voices, decreasing, opacity IS the weight
                add_thread(clock, s, strands=[
                    Strand(weight=float(self.opacity[i]) * a,
                           delay=(j + 1) + q * max(3, n_band), tint=band)
                    for q, a in enumerate(anneal)])
                # the merit cord: drift lives here and nowhere else
                self._merit_slot[i] = add_thread(s, ww, strands=[Strand(
                    weight=1.0, delay=1, drift=self.drift,
                    floor=MERIT_FLOOR, ceil=MERIT_CEIL, tint=band)])
                add_thread(ww, t, strands=[Strand(weight=1.0, delay=1,
                                                  tint=band)])
                add_thread(ww, done, strands=[Strand(weight=1.0, delay=1,
                                                     tint=band)])
            prev_done = done

        # judgement: the four verdicts, their fringes, the alarm, the show gate
        for v, fr in (("verdict_blank", "beats_blank"),
                      ("verdict_blur", "blur_gap"),
                      ("verdict_busy", "busy_gap"),
                      ("verdict_chroma", "chroma_life")):
            w.knot(v, verb="spell", spell=v)
            w.knot(fr, verb="fringe")
            add_thread("fine_done", v, strands=[Strand(weight=1.0, delay=1)])
            add_thread(v, fr, strands=[Strand(weight=1.0, delay=1)])
        w.knot("alarm", verb="gate", trigger="count 2", bias=1.0)
        w.knot("alarm_out", verb="fringe")
        add_thread("verdict_busy", "alarm", port="key",
                   strands=[Strand(weight=-1.0, delay=1)])
        add_thread("fine_done", "alarm", strands=[Strand(weight=0.0, delay=2)])
        add_thread("alarm", "alarm_out", strands=[Strand(weight=1.0, delay=1)])
        w.knot("show", verb="gate", trigger="count 2", bias=1.0)
        add_thread("verdict_blank", "show", port="key",
                   strands=[Strand(weight=1.0, delay=1)])
        add_thread("fine_done", "show", strands=[Strand(weight=0.0, delay=2)])
        if self.gaze:
            w.knot("behold", verb="spell", spell="behold")
            w.knot("hear_back", verb="spell", spell="hear_back")
            w.knot("gist_echo", verb="fringe")
            w.knot("ear_echo", verb="fringe")
            add_thread("show", "behold", strands=[Strand(weight=1.0, delay=1)])
            add_thread("show", "hear_back",
                       strands=[Strand(weight=1.0, delay=1)])
            add_thread("behold", "gist_echo",
                       strands=[Strand(weight=1.0, delay=1)])
            add_thread("hear_back", "ear_echo",
                       strands=[Strand(weight=1.0, delay=1)])

        w.seed("look", 1.0, beat=1)
        w.run_hint = self.horizon
        return w

    # -- spells: taught fresh every sitting so the book points at THIS atelier

    def _teach(self) -> None:
        brushes.teach_all(self.atelier, self.n)
        if self.gaze:
            for nm in ("propose", "behold", "hear_back"):
                spells.teach(nm, self.gaze[nm], replace=True)

    # -- one sitting

    def sitting(self, persist: bool = True, quiet: bool = False):
        """Reset, run the weave once, print the floor verdict, learn, persist.

        Returns the Result's fringes as {name: [values]}."""
        self.sittings += 1
        self.atelier.reset()
        self._teach()
        w = self.weave()
        w.validate()
        res = Loom().run(w, self.horizon)
        self.last_result = res
        fringes = {k: res.fringe(k) for k in
                   ("beats_blank", "blur_gap", "busy_gap", "chroma_life",
                    "alarm_out", "gist_echo", "ear_echo")}
        if not quiet:
            self._print_verdict(fringes)
        self._transcribe(res)
        if persist:
            self._persist(w, res, fringes)
        return fringes

    # -- learning across sittings: drift -> Result.learned -> opacity

    def _transcribe(self, res) -> None:
        """The documented ALMA loop: the loom learned on its copy; the author
        writes it back. Merit multiplies opacity, monotonically — a stroke that
        kept earning stays awake, one that spoke into silence fades under theta
        and stops waking. That is sleep."""
        if res.learned is None:
            return
        for i, slot in self._merit_slot.items():
            self.opacity[i] = min(OP_MAX, self.opacity[i] * res.learned[slot])

    # -- the verdict block, winston.py's voice

    def _print_verdict(self, fringes) -> None:
        v = self.atelier.verdicts()
        pc = None
        if v["n_alive"]:
            sheets = 1.0 - self.atelier.canvas().mean(-1)[None]
            pc = pen_check(sheets)
        print("\n== WINSTON sitting %d | %s | %d strokes (%s), %d alive =="
              % (self.sittings, self.name, self.n,
                 "/".join(str(b) for b in self.bands), v["n_alive"]))
        print("BLANK %.5f  |  PAINTER %.5f  |  BLUR %.5f (%dx%d grid)"
              % (v["blank"], v["painter"], v["blur"],
                 self.atelier.blur_side, self.atelier.blur_side))
        print("BUSY tenth: PAINTER %.5f vs BLANK %.5f   <- the number that "
              "catches a vanished person" % (v["busy_painter"], v["busy_blank"]))
        print("chroma deficit %.5f  |  awake %d/%d (theta %g)"
              % (v["chroma_deficit"],
                 int((self.opacity >= self.theta).sum()), self.n, self.theta))
        if pc:
            print("pen: %.1f pieces mean, %.0f%% sheets in 1-2 pieces, "
                  "cover %.3f" % (pc["pieces_mean"],
                                  100 * pc["one_or_two_pieces"],
                                  pc["cover_mean"]))
        print(" %s" % ("PASSES: it beats a flat colour, so it is painting "
                       "something. / עובר: מנצח צבע אחיד — זה ציור."
                       if v["beats_blank"] > 0 else
                       "FAILS: worse than one flat colour. It is not painting,"
                       " it is smearing. / נכשל: גרוע מצבע אחיד."))
        if fringes["alarm_out"]:
            print(" ALARM: the busy tenth is worse than a flat colour's — the "
                  "SUBJECT was sold (the 08-31 scar). Do not call this a "
                  "painting. / אזעקה: הנושא נמכר.")
        if not fringes["beats_blank"]:
            print(" (verdicts never fired — the run was cut before fine_done; "
                  "raise the horizon)")

    # -- persistence: canonical JSON + additive atelier block, PNG, record

    def _persist(self, w: Weave, res, fringes) -> dict:
        stamp = time.strftime("%Y%m%d-%H%M%S") + "-s%03d" % self.sittings
        os.makedirs(self.out_dir, exist_ok=True)
        d = to_dict(w)
        d["atelier"] = {                      # additive; from_dict ignores it
            "subject": self.atelier.subject_path, "size": self.atelier.size,
            "n_strokes": self.n, "bands": list(self.bands),
            "r_fires": self.r, "theta": self.theta, "eps": self.eps,
            "drift": self.drift, "seed": self.seed,
            "opacity_after": [float(o) for o in self.opacity],
            "verdicts": self.atelier.verdicts(),
            "fringes": {k: list(map(float, vv)) for k, vv in fringes.items()},
            "sitting": self.sittings, "stamp": stamp,
        }
        jpath = os.path.join(self.out_dir, "sitting-%s.json" % stamp)
        with open(jpath, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=1, ensure_ascii=False)
        ppath = self.atelier.save_png(
            os.path.join(self.out_dir, "sitting-%s.png" % stamp))
        import record
        rpaths = record.paint_record(
            self.atelier, os.path.join(self.out_dir, "record-%s.json" % stamp),
            png_path=ppath, meta={"sitting": self.sittings, "stamp": stamp},
            bands=self.bands, opacity=self.opacity)
        self.last_paths = {"json": jpath, "png": ppath, **rpaths}
        return self.last_paths
