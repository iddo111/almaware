# -*- coding: utf-8 -*-
r"""
matzav_plan.py — PLAN. A pure function: (mode, state) -> Plan | Refusal.

No I/O. No SSH. No files. Unit-testable offline, which is the whole point:
the sacred guard and the budget must be able to INSPECT what a mode will do
before anything is executed.

GATE 2 of the sacred guard lives here. Two refusal classes, both worded as
refusals with numbers, never as failures:
  direct   — the plan would stop a sacred unit
  resource — the budget can only be met by taking a resource a sacred unit holds
"""
import time

from matzav_sacred import (PC_HOSTS_NO_MODES, holders_of, is_sacred,
                           sacred_for_box)

OBS_MAX_AGE_S = 30


def _fmt_gb(x):
    return ("%.1f" % x).rstrip("0").rstrip(".")


class Refusal(dict):
    def __init__(self, kind, he, detail=None, numbers=None):
        super().__init__(refused=True, kind=kind, he=he, detail=detail or [],
                         numbers=numbers or {})


def plan(mode, units, state, now=None):
    now = now or time.time()
    steps, notes, warnings = [], [], []

    # ---- 0. a mode that has never been run is a claim, not a feature -------
    if not mode.get("runnable"):
        st = (mode.get("demonstrated") or {}).get("status", "planned")
        return Refusal(
            "never-run",
            "המצב הזה מעולם לא הורץ — הוא הצהרה, לא כפתור.",
            [(mode.get("demonstrated") or {}).get("evidence", ""),
             mode.get("honesty", "")] +
            ["בעיה בהגדרה: " + e for e in mode.get("validation_errors", [])],
            {"status": st})

    want = [units[u] for u in mode.get("want", []) if u in units]
    concede_ids = list(mode.get("concede", []))
    boxes_involved = sorted({u["box"] for u in want} |
                            {units[c]["box"] for c in concede_ids if c in units})

    # ---- 1. the PC hosts no modes. Structural. -----------------------------
    if PC_HOSTS_NO_MODES and "pc" in boxes_involved:
        gpu_holders = holders_of("pc:gpu")
        return Refusal(
            "sacred-resource",
            "מסורב: ה-PC לא מארח מצבים.",
            ["ה-VRAM היחיד כאן (8 GB) מוחזק במלואו על ידי " +
             ", ".join(u for u, _ in gpu_holders) +
             " — המיקרופון של עידו והקו שלו לקלוד.",
             "נמדד 04/09: 0.6–0.9 GB פנויים מתוך 8, ומעבד 56–86% על 4 ליבות "
             "כשהמיקרופון כבר רץ."],
            {"vram_free_gb": 0.6})

    # ---- 2. pre-flight: every involved box must have answered recently -----
    obs_age = now - state.get("ts", now)
    if obs_age > OBS_MAX_AGE_S:
        return Refusal("stale-observation",
                       "מסורב: המדידה בת %d שניות. מודדים מחדש לפני שמתכננים."
                       % obs_age, [], {"age_s": int(obs_age)})
    for b in boxes_involved:
        bs = state["boxes"].get(b) or {}
        if bs.get("reachable") is not True:
            return Refusal(
                "box-unknown",
                "מסורב: %s לא ענה למדידה." % b,
                ["רוב חצאי-המעברים נמנעים בכך שלא מתחילים.",
                 "שגיאה: %s" % (bs.get("err") or "לא ידוע")],
                {"box": b})
        # a sacred probe failing on an involved box halts everything
        for s in sacred_for_box(b):
            if s.kind == "audio":
                continue
            uid = "%s/%s" % (b, s.unit.replace(".service", ""))
            us = state["units"].get(uid)
            if us and us["real"] != "up":
                return Refusal(
                    "sacred-down",
                    "מסורב: שירות קדוש על %s לא עונה — %s." % (b, s.unit),
                    ["\"%s\"" % s.why,
                     "כשהקדוש לא בסדר, אף מצב לא זז. קודם מתקנים את החלון השבור."],
                    {"box": b, "unit": s.unit})

    # ---- 3. GATE 2 direct: never stop a sacred unit -------------------------
    for cid in concede_ids:
        u = units.get(cid)
        if u and (u.get("sacred") or is_sacred(u["box"], u["unit"])):
            return Refusal("sacred-direct",
                           "מסורב: המצב היה עוצר שירות קדוש — %s." % cid,
                           [u.get("sacred_why", "")], {"unit": cid})

    # ---- 4. what needs to start -------------------------------------------
    to_start = []
    for u in want:
        us = state["units"].get(u["id"]) or {}
        if us.get("real") != "up":
            if not u.get("start"):
                return Refusal(
                    "no-start-verb",
                    "מסורב: אין דרך להפעיל את %s בלחיצה." % u["id"],
                    [u.get("broken_window") or
                     "אין ליחידה הזאת פועל הפעלה ברישום.",
                     "זה לא כשל של MATZAV — זה חלון שבור בצי. "
                     "כותבים ליחידה קובץ systemd, ואז זה יעבוד."],
                    {"unit": u["id"]})
            to_start.append(u)

    # ---- 5. budget, per box. A budget, not a list. -------------------------
    to_stop, budget = [], {}
    quiet = bool(mode.get("quiet"))

    if quiet:
        for cid in concede_ids:
            u, us = units.get(cid), state["units"].get(cid) or {}
            if not u or us.get("real") != "up":
                continue
            if not u.get("stop"):
                warnings.append("%s רץ אבל אין לו פועל עצירה — נשאר." % cid)
                continue
            if us.get("human_hold"):
                warnings.append("%s — %s. לא נגעתי בו."
                                % (cid, us.get("human_hold_why")))
                continue
            to_stop.append(u)

    for b in boxes_involved:
        bs = state["boxes"][b]
        avail = bs.get("ram_avail_gb") or 0
        reserve = bs.get("reserve_gb", 8)
        free = round(avail - reserve, 1)
        need = round(sum((u["cost"].get("ram_gb") or 0)
                         for u in to_start if u["box"] == b), 1)
        freed = round(sum((u["cost"].get("ram_gb") or 0)
                          for u in to_stop if u["box"] == b), 1)
        picked = []
        if not quiet and need > free:
            # greedily concede the largest conceded units on this box
            cands = []
            for cid in concede_ids:
                u, us = units.get(cid), state["units"].get(cid) or {}
                if (not u or u["box"] != b or us.get("real") != "up" or
                        not u.get("stop")):
                    continue
                if us.get("human_hold"):
                    warnings.append(
                        "%s — %s. מצב לא עוצר תהליך שאדם הפעיל."
                        % (cid, us.get("human_hold_why")))
                    continue
                cands.append((u["cost"].get("ram_gb") or 0, u))
            cands.sort(key=lambda t: -t[0])
            for gb, u in cands:
                if need <= free + freed:
                    break
                picked.append(u)
                freed = round(freed + gb, 1)
            to_stop.extend(picked)

        short = round(need - (free + freed), 1)
        budget[b] = {
            "ram_avail_gb": avail, "reserve_gb": reserve, "free_gb": free,
            "need_gb": need, "freed_gb": freed, "short_gb": max(0.0, short),
            "fits": short <= 0,
            "gpu_held_gb": bs.get("gpu_held_gb"),
            "disk_avail_gb": bs.get("disk_avail_gb"),
            "load_ratio": bs.get("load_ratio"),
            "gpu_gauge_note": "GB10: אין מד VRAM — nvidia-smi מחזיר N/A. "
                              "התקציב הוא MemAvailable.",
        }
        if short > 0:
            # is the only way to fit through a resource a sacred unit holds?
            hold = holders_of("%s:gpu" % b) + holders_of("%s:ram" % b)
            detail = ["חסר %s GB על %s. פנוי %s GB (מתוך %s, פחות שמורה של %s)."
                      % (_fmt_gb(short), b, _fmt_gb(free), _fmt_gb(avail),
                         _fmt_gb(reserve))]
            if hold:
                detail.append(
                    "מה שהיה סוגר את הפער מוחזק על ידי שירות קדוש: %s — \"%s\"."
                    % (hold[0][0], hold[0][1]))
            rest = [c for c in concede_ids
                    if units.get(c, {}).get("box") == b and
                    (state["units"].get(c) or {}).get("real") == "up"]
            if rest:
                detail.append("המצב הזה מוותר רק על: %s." % ", ".join(rest))
            else:
                detail.append("המצב הזה לא מוותר על כלום על %s — "
                              "בכוונה. תקרה הורגת ניסוי חי." % b)
            return Refusal("budget", "אדום: לא נכנס.", detail,
                           {"box": b, "short_gb": short, "free_gb": free,
                            "need_gb": need})

    # ---- 6. order: stops before starts, per box ---------------------------
    for u in to_stop:
        steps.append({"act": "stop", "unit": u["id"], "box": u["box"],
                      "title": u.get("title_he"),
                      "frees_gb": u["cost"].get("ram_gb"),
                      "gpu_gb": u["cost"].get("gpu_gb"),
                      "verb": u["stop"]})
    for u in to_start:
        us = state["units"].get(u["id"]) or {}
        warm = bool(us.get("warm"))
        steps.append({"act": "start", "unit": u["id"], "box": u["box"],
                      "title": u.get("title_he"),
                      "costs_gb": u["cost"].get("ram_gb"),
                      "warm": warm,
                      "seconds": (u["cost"].get("load_s_warm") if warm
                                  else u["cost"].get("load_s_cold")),
                      "estimated": bool(u["cost"].get("estimated")),
                      "verb": u["start"]})

    # ---- 7. cost before the click -----------------------------------------
    per_box = {}
    for s in steps:
        per_box.setdefault(s["box"], 0)
        per_box[s["box"]] += s.get("seconds") or 3
    wall = max(per_box.values()) if per_box else 0
    est = any(s.get("estimated") for s in steps)

    already = [u["id"] for u in want
               if (state["units"].get(u["id"]) or {}).get("real") == "up"]
    if not steps:
        notes.append("המצב כבר מתקיים — אין מה לעשות. %s"
                     % ("כל היחידות למעלה: " + ", ".join(already)
                        if already else ""))

    return {
        "refused": False, "mode": mode["id"], "title_he": mode.get("title_he"),
        "steps": steps, "budget": budget, "notes": notes,
        "warnings": warnings, "boxes": boxes_involved,
        "wall_s": wall, "estimated": est, "already_up": already,
        "obs_age_s": round(obs_age, 1),
        "honesty": mode.get("honesty"),
        "observed_at": state.get("ts"),
    }


def summarize_he(p):
    """One line per action, in Hebrew, with the box, the number and the reason."""
    if p.get("refused"):
        return [p["he"]] + list(p.get("detail") or [])
    out = []
    for s in p["steps"]:
        if s["act"] == "stop":
            out.append("עוצר · %s · %s — מפנה %s GB%s"
                       % (s["box"], s["title"], _fmt_gb(s.get("frees_gb") or 0),
                          (" (מתוכם %s GB GPU)" % _fmt_gb(s["gpu_gb"]))
                          if s.get("gpu_gb") else ""))
        else:
            out.append("מפעיל · %s · %s — %s, %s שניות%s"
                       % (s["box"], s["title"],
                          "חם" if s.get("warm") else "קר",
                          s.get("seconds"),
                          " (אומדן)" if s.get("estimated") else ""))
    for n in p.get("notes", []):
        out.append(n)
    for w in p.get("warnings", []):
        out.append("⚠ " + w)
    return out
