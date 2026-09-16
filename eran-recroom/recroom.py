# -*- coding: utf-8 -*-
"""
recroom.py  —  "חדר המשחקים של ערן" / Eran's Rec Room
=====================================================

A minimal but REAL, loopback-only rec room that unifies three developmental
"toys" under one server + one page, with PERSISTENT state:

  1) מובייל (Mobile)      — smooth-pursuit tracker. A target moves; Eran's gaze
                            follows with lag+noise. Server reports gaze error and
                            a rolling "pursuit skill" that improves as he plays.
  2) הד (Mirror-babble)   — call-and-response. You send a syllable; Eran imitates
                            it (imperfectly at first, more faithfully as he hears
                            it more). Turn-taking is counted.
  3) לוח ציוני-דרך        — milestone ladder (abba->ima->ido->eran) persisted to
     (Milestone board)      state.json. Advances only when earned by repetitions.

HONEST: this is a developmental SCAFFOLD, not the trained DGX brain. The "skill"
curves here are deterministic emulation of practice-makes-progress, pure stdlib,
inference-only, no training, no DGX, no camera required. It just runs.

Run:
    python recroom.py
    -> http://127.0.0.1:8785/     (loopback only)

לזכרה של עלמה ז"ל · ALMAWARE / iddoperez.ai
"""
from __future__ import annotations
import json, math, sys, random, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

HERE = Path(__file__).resolve().parent
STATE_PATH = HERE / "state.json"
HOST, PORT = "127.0.0.1", 8785

LADDER = ["אבא", "אימא", "עידו", "ערן"]   # abba -> ima -> ido -> eran
REPS_TO_MASTER = 3                          # imitations of the *next* rung to climb

_LOCK = threading.Lock()

DEFAULT_STATE = {
    "pursuit_reps": 0,          # mobile-tracking attempts
    "babble_turns": 0,          # call-and-response turns taken
    "heard": {},                # syllable -> times heard (drives imitation fidelity)
    "ladder_level": 0,          # 0..4 rungs climbed
    "next_rung_reps": 0,        # reps toward the next rung
    "mastered": [],             # rung words earned
    "mood": "calm",             # gentle-state: calm|curious|happy (responsiveness label)
    "quiet_streak": 0,          # consecutive quiet cues (drives decay back to calm)
    "mood_cues": 0,             # total mood cues processed
}

# --- Baby Cave (N children) --------------------------------------------------
# Same architecture ("genes"), same protected upbringing. This is not a
# twin study with a control and an experimental arm — it's a Baby Cave
# (מערת תינוקות): many children raised together in full isolation from the
# outside world, all cheder-pure. ANY number of named children can be
# registered by simply naming them via ?who=, no code change required. Each
# child's state is fully independent — one child's play never mutates
# another's, but that independence isn't a scientific comparison, just
# isolation. Sourced from project_eran_little_brother.md, generalized per
# Iddo's "Baby Cave" concept (many children, all in the same protected cave).
PRIMARY_CHILD = "eran"
# Known Hebrew display names for children we have a story for; any OTHER
# name is still a fully valid child, just shown by its own name (see
# CHILD_HE.get()).
CHILD_HE = {"eran": "ערן", "yigael": "יגאל"}


def _norm_who(who: str) -> str:
    who = (who or PRIMARY_CHILD).strip().lower()
    return who or PRIMARY_CHILD


def child_state(root: dict, who: str) -> dict:
    """Return the mutable state dict for one child in the cave. The primary
    child (eran) IS the top-level state (backward compatible with old
    state.json files that predate multi-child support). Every OTHER child —
    known or newly-named — lives in root['children'][who], created on first
    use so new children need zero code changes."""
    who = _norm_who(who)
    if who == PRIMARY_CHILD:
        return root
    children = root.setdefault("children", {})
    if who not in children:
        children[who] = dict(DEFAULT_STATE)
    else:
        children[who] = {**DEFAULT_STATE, **children[who]}
    return children[who]


def cave_children(root: dict) -> list[str]:
    """All child names currently present in the cave, primary first."""
    names = [PRIMARY_CHILD]
    names += sorted(root.get("children", {}).keys())
    return names


def load_state() -> dict:
    if STATE_PATH.exists():
        try:
            s = json.loads(STATE_PATH.read_text(encoding="utf-8"))
            merged = {**DEFAULT_STATE, **s}
            # migrate legacy key "twins" (2-child era) -> "children"
            if "twins" in merged:
                merged.setdefault("children", {}).update(merged.pop("twins"))
            return merged
        except Exception:
            pass
    return dict(DEFAULT_STATE)


def save_state(s: dict) -> None:
    STATE_PATH.write_text(json.dumps(s, ensure_ascii=False, indent=2),
                          encoding="utf-8")


# ---------------------------------------------------------------- toys ------

def pursuit_skill(reps: int) -> float:
    """0..1 smooth-pursuit competence; practice-makes-progress, saturating."""
    return 1.0 - math.exp(-reps / 12.0)


def track(root: dict, t_ms: int, who: str = "eran") -> dict:
    """A target orbits; the child's gaze lags by (1-skill) and jitters. Returns
    the two points + gaze error, then banks one rep of practice."""
    state = child_state(root, who)
    skill = pursuit_skill(state["pursuit_reps"])
    ang = (t_ms / 1000.0) * 1.4                       # target angular position
    R = 120.0
    tx, ty = 160 + R * math.cos(ang), 130 + R * math.sin(ang)
    lag = (1.0 - skill) * 0.55                         # radians of pursuit lag
    jit = (1.0 - skill) * 26.0
    rng = random.Random(state["pursuit_reps"] * 1000 + t_ms)
    ga = ang - lag
    gx = 160 + R * math.cos(ga) + rng.uniform(-jit, jit)
    gy = 130 + R * math.sin(ga) + rng.uniform(-jit, jit)
    err = math.hypot(tx - gx, ty - gy)
    with _LOCK:
        state["pursuit_reps"] += 1
        save_state(root)
    return {"target": [round(tx, 1), round(ty, 1)],
            "gaze": [round(gx, 1), round(gy, 1)],
            "error": round(err, 1),
            "skill": round(pursuit_skill(state["pursuit_reps"]), 3),
            "reps": state["pursuit_reps"]}


VOWELS = "aeiou"


def imitate(syllable: str, times_heard: int) -> str:
    """Return Eran's imitation. Few hearings -> vowel-smeared babble; more
    hearings -> faithful echo. Deterministic in times_heard."""
    syl = (syllable or "ba").strip().lower()[:12] or "ba"
    fidelity = 1.0 - math.exp(-times_heard / 3.0)
    rng = random.Random(hash((syl, times_heard)) & 0xffffffff)
    out = []
    for ch in syl:
        if ch.isalpha() and ch not in VOWELS and rng.random() > fidelity:
            out.append(rng.choice(VOWELS))       # consonant not yet mastered
        else:
            out.append(ch)
    echo = "".join(out)
    if fidelity < 0.4:                            # early: reduplicated babble
        echo = echo + echo
    return echo


def babble(root: dict, syllable: str, who: str = "eran") -> dict:
    state = child_state(root, who)
    syl = (syllable or "ba").strip().lower()[:12] or "ba"
    with _LOCK:
        heard = state["heard"].get(syl, 0)
        echo = imitate(syl, heard)
        state["heard"][syl] = heard + 1
        state["babble_turns"] += 1
        # climbing the ladder: hearing the *next rung word* enough masters it
        advanced = False
        if state["ladder_level"] < len(LADDER):
            rung = LADDER[state["ladder_level"]]
            if syl == rung:
                state["next_rung_reps"] += 1
                if state["next_rung_reps"] >= REPS_TO_MASTER:
                    state["mastered"].append(rung)
                    state["ladder_level"] += 1
                    state["next_rung_reps"] = 0
                    advanced = True
        save_state(root)
    return {"heard_syllable": syl, "eran_says": echo,
            "times_heard": state["heard"][syl],
            "turns": state["babble_turns"],
            "advanced": advanced, "ladder": milestone(state), "who": who}


def milestone(state: dict) -> dict:
    lvl = state["ladder_level"]
    return {"level": lvl, "of": len(LADDER),
            "mastered": list(state["mastered"]),
            "next": LADDER[lvl] if lvl < len(LADDER) else None,
            "next_rung_reps": state["next_rung_reps"],
            "reps_to_master": REPS_TO_MASTER}


# -- gentle state: calm / curious / happy -----------------------------------
# Honest label (see archived gentle_state.py): Eran is an INFANT model. This is
# NOT emotion or feeling — it is deterministic expressive responsiveness, like a
# baby toy that lights up when talked to. A cue maps to a state; quiet decays it
# back toward calm. Priority: owner-voice/name -> happy; novelty -> curious.
MOOD_HE = {"calm": "רגוע", "curious": "סקרן", "happy": "שמח"}
NAME_CUES = {"eran", "ערן", "abba", "אבא", "ima", "אימא", "ido", "עידו", "name", "owner", "voice"}
NOVELTY_CUES = {"novelty", "new", "toy", "object", "scene", "move", "חדש"}
QUIET_DECAY = 2  # quiet cues in a row before the mood eases one step calmer


def gentle_state(root: dict, cue: str, who: str = "eran") -> dict:
    """Map one input cue to a gentle state, persisting the result."""
    state = child_state(root, who)
    c = (cue or "quiet").strip().lower()[:16]
    with _LOCK:
        state["mood_cues"] += 1
        if c in NAME_CUES:
            state["mood"] = "happy"
            state["quiet_streak"] = 0
            reason = "owner-voice / name heard"
        elif c in NOVELTY_CUES:
            # novelty only lifts calm->curious; it never overrides happy
            if state["mood"] != "happy":
                state["mood"] = "curious"
            state["quiet_streak"] = 0
            reason = "novelty in the eyes"
        else:  # quiet / unknown cue -> decay one step toward calm
            state["quiet_streak"] += 1
            reason = "quiet"
            if state["quiet_streak"] >= QUIET_DECAY:
                state["mood"] = {"happy": "curious", "curious": "calm",
                                 "calm": "calm"}[state["mood"]]
                state["quiet_streak"] = 0
        save_state(root)
    return {"cue": c, "mood": state["mood"], "mood_he": MOOD_HE[state["mood"]],
            "reason": reason, "quiet_streak": state["quiet_streak"],
            "mood_cues": state["mood_cues"], "scaffold": True, "who": who}


def status(root: dict, who: str = "eran") -> dict:
    state = child_state(root, who)
    return {
        "scaffold": True,
        "who": who, "who_he": CHILD_HE.get(who, who),
        "banner_he": "אמולציה — חדר משחקים התפתחותי (המוח האמיתי מתאמן ב-DGX)",
        "banner_en": "SCAFFOLD — developmental rec room (real cortex trains on DGX)",
        "pursuit_reps": state["pursuit_reps"],
        "pursuit_skill": round(pursuit_skill(state["pursuit_reps"]), 3),
        "babble_turns": state["babble_turns"],
        "milestone": milestone(state),
        "mood": state["mood"],
        "mood_he": MOOD_HE[state["mood"]],
    }


def cave(root: dict) -> dict:
    """Side-by-side Baby Cave snapshot: every registered child's milestone
    ladder + skills. Not limited to a fixed pair — reports whoever is
    present. Each child's state is independent (no cross-contamination
    between children's play), but this is isolation, not a scientific
    control-vs-experimental comparison."""
    names = cave_children(root)
    return {
        "scaffold": True,
        "cave": "Baby Cave / מערת התינוקות — same architecture, independent children",
        "isolation": "each child's state is independent during formation",
        "count": len(names),
        "children": {w: status(root, w) for w in names},
    }


# --------------------------------------------------------------- server -----

class H(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        b = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(b)

    def log_message(self, *a):
        pass

    def do_GET(self):
        u = urlparse(self.path)
        p, q = u.path, parse_qs(u.query)
        st = load_state()
        who = q.get("who", ["eran"])[0]
        if p in ("/", "/index.html"):
            self._send(200, (HERE / "room.html").read_text(encoding="utf-8"),
                       "text/html; charset=utf-8")
        elif p == "/status":
            self._send(200, json.dumps(status(st, who), ensure_ascii=False))
        elif p in ("/cave", "/twins"):   # "/twins" kept as a back-compat alias
            self._send(200, json.dumps(cave(st), ensure_ascii=False))
        elif p == "/track":
            t = int(q.get("t", ["0"])[0] or 0)
            self._send(200, json.dumps(track(st, t, who), ensure_ascii=False))
        elif p == "/babble":
            syl = q.get("syl", ["ba"])[0]
            self._send(200, json.dumps(babble(st, syl, who), ensure_ascii=False))
        elif p == "/mood":
            cue = q.get("cue", ["quiet"])[0]
            self._send(200, json.dumps(gentle_state(st, cue, who), ensure_ascii=False))
        elif p == "/reset":
            save_state(dict(DEFAULT_STATE))
            self._send(200, json.dumps({"ok": True}, ensure_ascii=False))
        else:
            self._send(404, "{}")


def main():
    if not STATE_PATH.exists():
        save_state(dict(DEFAULT_STATE))
    print(f"[rec-room] חדר המשחקים של ערן  ->  http://{HOST}:{PORT}/   (loopback)",
          flush=True)
    print("[rec-room] SCAFFOLD — inference-only emulation, no DGX, no camera.",
          flush=True)
    ThreadingHTTPServer((HOST, PORT), H).serve_forever()


if __name__ == "__main__":
    main()
