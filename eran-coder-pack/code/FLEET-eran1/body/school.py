"""school.py — the environment. It plays audio; it NEVER passes labels.

The curriculum is environmental: units advance in genome order, and all the
school does is decide WHICH wav files are on the menu (70% current unit, 30%
replay of mastered units, occasional free listening). The menu records are
opaque {'path': ...} — no label field ever crosses to the organism.

The mastery gate is the yigal2 lesson.json contract, fail-closed: one unit at
a time, sens/spec >= 0.95 on a DEV split carved from train (never the 132-item
heldout), a 12-hour delayed retention re-exam, 30% replay of mastered units
with a <=2-point regression tolerance. The examiner (proof/measure.py) holds
the labels; the school only receives numbers back.

Embodies: the parent sets the fence, the child plays inside it; fail-closed
gates (the yigal scar: gates that hold are worthless only if nobody feeds the
child — so the school itself is the feeder).
"""
import json
import os
import random
import sys
import time

import genome

sys.path.insert(0, os.path.join(genome.ROOT, "proof"))
import measure                                          # the examiner


class School:
    def __init__(self, seed=genome.SEED, now_fn=time.time):
        self.rng = random.Random(seed)
        self.now = now_fn
        self.unit = genome.CURRICULUM[0]
        self.mastered = []
        self.pending_retention = {}      # unit -> retention due (epoch seconds)
        self.revisit = []                # units the child moved past, to come back to
        self.fails = {}                  # unit -> consecutive failed gates
        self.last_gate = {}
        self._no_dev_logged = None       # ERAN-03: unit whose blindness was said
        self._load()

    # ----------------------------------------------------------- persistence
    def _load(self):
        if os.path.exists(genome.CURRICULUM_FILE):
            try:
                with open(genome.CURRICULUM_FILE, "r", encoding="utf-8") as f:
                    s = json.load(f)
                self.unit = s.get("unit", self.unit)
                self.mastered = list(s.get("mastered", []))
                self.pending_retention = dict(s.get("pending_retention", {}))
                self.revisit = list(s.get("revisit", []))
                self.fails = dict(s.get("fails", {}))
            except (ValueError, OSError):
                pass

    def save(self):
        os.makedirs(os.path.dirname(genome.CURRICULUM_FILE), exist_ok=True)
        tmp = genome.CURRICULUM_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"unit": self.unit, "mastered": self.mastered,
                       "pending_retention": self.pending_retention,
                       "revisit": self.revisit, "fails": self.fails,
                       "last_gate": self.last_gate}, f, indent=1)
        os.replace(tmp, genome.CURRICULUM_FILE)

    # ------------------------------------------------------------- the menu
    def _unit_wavs(self, unit):
        """Train wavs of one unit, dev files excluded (the gate must stay
        honest: the organism never eats its own exam)."""
        d = genome.FOOD_TRAIN
        if not os.path.isdir(d):
            return []
        return [os.path.join(d, n) for n in sorted(os.listdir(d))
                if n.startswith(unit + "_") and n.endswith(".wav")
                and not measure.is_dev(n)]

    def _world_wavs(self):
        """Everything audible in the house. A baby in a home OVERHEARS the
        whole language long before anyone teaches it a syllable — measured
        2026-08-21: with free listening restricted to taught units the child
        had heard 3 sounds of 22 after 733,000 beats, and 3/22 was a hard
        ceiling on every exam. The curriculum sets ATTENTION, never a wall."""
        d = genome.FOOD_TRAIN
        if not os.path.isdir(d):
            return []
        return [os.path.join(d, n) for n in sorted(os.listdir(d))
                if n.endswith(".wav") and not measure.is_dev(n)]

    def serve_menu(self, chem=None):
        """Opaque menu: [{'path': ...}]. No labels. Ever."""
        current = self._unit_wavs(self.unit) if self.unit else []
        replay_pool = ([p for u in self.mastered for p in self._unit_wavs(u)]
                       or self._world_wavs())
        patience = chem.patience() if chem else genome.SHT0
        free_p = genome.FREE_LISTEN_P * (1.0 - 0.5 * patience)
        if (not current) or (replay_pool and self.rng.random() < free_p):
            pool = self._world_wavs() + current   # free listening: the house
            picks = self.rng.sample(pool, min(genome.MENU_SIZE, len(pool)))
        else:
            n_cur = max(1, round(genome.MENU_SIZE * genome.CURRENT_FRAC))
            n_rep = genome.MENU_SIZE - n_cur
            picks = self.rng.sample(current, min(n_cur, len(current)))
            if replay_pool and n_rep:
                picks += self.rng.sample(replay_pool,
                                         min(n_rep, len(replay_pool)))
        self.rng.shuffle(picks)
        return [{"path": p} for p in picks]       # opaque — path only

    # ------------------------------------------------------------- the gate
    def _advance(self):
        # Pipelined ladder: a unit that passed its technical gate waits for
        # its 12h retention in pending_retention while the NEXT unit becomes
        # current. "Mastered" still requires the retention pass — the 12h law
        # is untouched; only the waiting no longer blocks the next lesson.
        for u in genome.CURRICULUM:
            if (u not in self.mastered and u not in self.pending_retention
                    and u not in self.revisit):
                self.unit = u
                return
        for u in self.revisit:                    # nothing new left: go back
            if u not in self.mastered and u not in self.pending_retention:
                self.unit = u
                self.revisit.remove(u)
                return
        self.unit = None                          # the whole ladder is climbed

    def gate(self, brain, ears_exam):
        """Run the examiner on the DEV split; apply the fail-closed contract.

        Returns a summary dict (numbers only) for the metrics line.

        The exam universe is the EXPOSURE — mastered units + the current one:
        a child is examined against everything the curriculum has let it
        hear, and each new unit must be discriminated from all of it. The
        global 22-class number is the examiner's reported exam, not the gate.
        """
        universe = list(self.mastered)
        for u in self.pending_retention:          # exposure includes waiters
            if u not in universe:
                universe.append(u)
        if self.unit and self.unit not in universe:
            universe.append(self.unit)
        scores = measure.dev_scores(brain, ears_exam, units=universe)
        now = self.now()
        if scores["dev_items"] == 0:
            # ERAN-03: AN EMPTY DEV SPLIT IS BLINDNESS, NOT A VERDICT.
            # measure.dev_scores returns sens 0.0 when a unit has no positives
            # and top1 0.0 when there are no truths at all -- indistinguishable
            # from a child who got everything wrong. Left alone, that pushes
            # fails to GATE_PATIENCE on every unit in turn, moves each to
            # revisit, marks all 13 mastered units 'regressed', and rewrites
            # curriculum.json with those zeros every 200 beats. The 2026-09-06
            # famine fix (DEV_SESSION_PICK 0 -> 1) cures the starvation by
            # making the EXAMINER blind, and nothing here said so. Skip the
            # exam, touch nothing, and say it once per unit.
            if self._no_dev_logged != self.unit:
                self._no_dev_logged = self.unit
                print(f"[gate] NO DEV SPLIT: 0 dev items over the exam "
                      f"universe {universe} -- exam SKIPPED, ladder untouched "
                      f"(unit '{self.unit}', fit_items "
                      f"{scores['fit_items']})", flush=True)
            self.last_gate = {"ts": now, "unit": self.unit,
                              "examined": self.unit, "current": None,
                              "dev_top1": 0.0, "regressed": [],
                              "events": [{"no_dev": True}],
                              "dev_items": 0, "no_dev": True}
            return self.last_gate     # NOT saved: keep the last REAL gate on disk
        per_unit = scores["per_unit"]
        events = []

        # 1. retention re-exams that have come due
        for unit, due in sorted(self.pending_retention.items()):
            if now < due:
                continue
            s = per_unit.get(unit, {"sens": 0.0, "spec": 0.0})
            del self.pending_retention[unit]
            if s["sens"] >= genome.SENS and s["spec"] >= genome.SPEC:
                if unit not in self.mastered:
                    self.mastered.append(unit)
                events.append({"retention_pass": unit})
                if self.unit is None:
                    self._advance()
            else:
                events.append({"retention_fail": unit,
                               "sens": s["sens"], "spec": s["spec"]})
                # fail-closed PULLBACK: the failed unit becomes current
                # again and must re-earn the whole gate
                self.unit = unit

        # 2. regression watch on mastered units (<=2-point tolerance)
        regressed = [u for u in self.mastered
                     if per_unit.get(u, {}).get("sens", 0.0)
                     < genome.SENS - genome.REGRESSION_TOL]

        # 2b. a current unit already waiting on retention has nothing left to
        # prove today — pipeline to the next lesson (covers state saved by
        # the pre-pipeline code too)
        if self.unit and self.unit in self.pending_retention:
            self._advance()
            events.append({"advanced_to": self.unit})

        # 3. technical gate on the current unit
        examined = self.unit                      # the unit this exam judged
        if self.unit and self.unit not in self.pending_retention:
            s = per_unit.get(self.unit, {"sens": 0.0, "spec": 0.0})
            if (s["sens"] >= genome.SENS and s["spec"] >= genome.SPEC
                    and not regressed):
                due = now + genome.RETENTION_HOURS * 3600
                self.pending_retention[self.unit] = due
                events.append({"technical_pass": self.unit,
                               "retention_due": due})
                self.fails.pop(self.unit, None)
                self._advance()                   # pipelined: next lesson now
                events.append({"advanced_to": self.unit})
            else:
                # A child who cannot get a sound today does not stop learning
                # language. After GATE_PATIENCE honest failures the lesson
                # moves on and the sound goes on the revisit list — it is
                # never marked mastered, and attention comes back to it once
                # the rest of the ladder has been walked. Without this the
                # child sat on one syllable forever (measured 2026-08-21:
                # stuck on 'ga' at sens 0.40 while 15 sounds waited).
                n = self.fails.get(self.unit, 0) + 1
                self.fails[self.unit] = n
                if n >= genome.GATE_PATIENCE:
                    events.append({"moved_on_from": self.unit,
                                   "after_failed_gates": n,
                                   "sens": s["sens"], "spec": s["spec"]})
                    self.revisit.append(self.unit)
                    self.fails.pop(self.unit, None)
                    self._advance()
                    events.append({"advanced_to": self.unit})

        self.last_gate = {
            "ts": now, "unit": self.unit, "examined": examined,
            "current": per_unit.get(examined) if examined else None,
            "dev_top1": scores["dev_top1"], "regressed": regressed,
            "dev_items": scores["dev_items"], "no_dev": False,
            "events": events,
        }
        self.save()
        return self.last_gate
