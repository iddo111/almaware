#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""qol.py -- QOL / קוֹל, the letter board that gives sound. ERAN's 220 in two taps.

WHAT THIS IS
    A weave of 220 knots. Each knot is one written Hebrew syllable (letter x nekuda).
    Press a knot and it fires ONE spark: a real human take of that sound, recorded in
    the booth, streamed from disk. Press a hollow knot and nothing sounds -- instead it
    tells you exactly how to feed it.

    So the board is two organs in one body:
      - an EAR-side organ  : Iddo hears what ERAN has been given.
      - a HUNGER organ     : Iddo sees, at a glance, what ERAN has NOT been given.
    The empty squares are the point. They are the recording checklist.

NEVER TTS. Every spark on this board came out of a human mouth in booth.py, where the
    prompt IS the label. voice-ant-farm/corpus-syllables is 624 wavs of the same 22
    syllables and it is *synthesised* (facebook/mms-tts-heb, per its own manifest.json).
    It is refused here by path and the refusal is recorded as a scar on /fringe. A
    synthetic clip on this board would let Iddo hear a syllable ERAN was never given.

SACRED AUDIO LAW, as implemented (not as promised):
    - no <audio> element exists until a human click creates one; preload="none".
    - no AudioContext is ever constructed. no getUserMedia is ever called. This page
      cannot open a microphone, so it cannot flip a Bluetooth headset to HFP.
    - a HUSH knot (inhibition) in the sticky header. While hushed, a press builds no
      audio object at all -- it is not a volume of zero, it is silence by construction.
    - a STOP knot, and Escape, and losing page visibility, all silence the current spark.
    - only one spark sounds at a time; a new press stops the old one first.

ALMA LANGUAGE (D:\\CLAUDE\\alma-language\\SPEC.md, ALMA-BIOLOGY.md, ALMA-LIVING-NEURON.md).
    You address knots, never registers. The words used here and what they mean:
      weave     the whole 220-knot board                         (SPEC 1)
      knot      one written syllable, the unit of the board      (SPEC 3)
      tray      the takes waiting inside a knot                  (SPEC 3)
      spark     one take, in flight to the ear, on one press     (SPEC 1)
      beat      the unit of time; nothing is instant             (SPEC 1)
      fringe    the observable hem of the weave -- /fringe JSON  (SPEC 5, verb `fringe`)
      hush      inhibition: the press fires, the sound does not
      mass      how much heard substance a knot carries (takes)
      trace     how far the knot's substance spreads in time     (mouths, sittings)
      threshold the mass and trace a knot must cross to be whole (BIOLOGY 1)
      drive     hunger: the ranked list of what is still missing (BIOLOGY 6)
      scar      a source refused, with the reason, kept visible  (LIVING-NEURON)
      mouth     one talker = one leave-one-mouth-out fold
      sitting   one calendar day of recording
    No buffers, no flags, no indices, no handles anywhere in the names.

THE HONEST NUMBER THIS BOARD EXISTS TO SHOW
    657 takes on disk today, and every one of them is ONE mouth (t06 = Iddo) on ONE day
    (2026-08-23). trace = 1 everywhere. Leave-one-mouth-out has nothing to leave out.
    A knot with 100 takes from one sitting is worth less than a knot with 3 takes from
    3 mouths, and the board says so in colour: mass alone never turns a knot green.

RUN
    PYTHONIOENCODING=utf-8 python3 qol.py            # 0.0.0.0:8809
    QOL_PORT=8809 QOL_BIND=0.0.0.0 python3 qol.py

LAYOUT ON DISK
    qol.py
    BOARD-220.json          the weave, copied from eran-brain/booth/ -- source of truth
    heard/<mouth>/<boothunit>_<mouth>_<n>.wav      real human takes, from booth.py
    drive.json              Iddo's wish list, appended by the board, read by nobody else

Does not touch eran1. Does not touch keshev-stt. Does not open an audio device.
"""
import http.server
import json
import os
import re
import socketserver
import sys
import threading
import time
import unicodedata
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, parse_qs

BODY = Path(__file__).resolve().parent
WEAVE_FILE = Path(os.environ.get("QOL_WEAVE", BODY / "BOARD-220.json"))
HEARD = Path(os.environ.get("QOL_HEARD", BODY / "heard"))
DRIVE_FILE = BODY / "drive.json"

PORT = int(os.environ.get("QOL_PORT", "8809"))
BIND = os.environ.get("QOL_BIND", "0.0.0.0")

# --- thresholds: what a knot must cross before it counts as fed -----------------------
# mass alone is not enough and never will be. The session-leak scar
# (project_eran_session_leak_scar) cost ERAN ~14 points of imaginary accuracy because a
# split leaked recording sessions. A knot is WHOLE only when it can survive the honest
# exam: at least THRESHOLD_MOUTHS different mouths, so one of them can be held out.
THRESHOLD_MASS = 3
THRESHOLD_MOUTHS = 2

SENSE_FRESH_BEATS = 5.0   # re-sense the disk at most this often

# --- the booth's short unit names -> this board's sound classes -----------------------
# booth.py prompts 22 consonant+patah syllables, 4 isolated vowels and 5 family words.
# BOARD-220.json speaks in sound classes: "<consonant>/<vowel>", 140 of them.
# This is the whole bridge between the two, written out by hand so it can be checked.
SOUND_OF_BOOTH = {
    "ah": "'/a", "aa": "'/a",
    "ba": "b/a", "ma": "m/a", "la": "l/a", "da": "d/a", "ga": "g/a", "pa": "p/a",
    "ta": "t/a", "na": "n/a", "ka": "k/a", "ra": "r/a", "sa": "s/a", "ha": "h/a",
    "va": "v/a", "ya": "y/a", "za": "z/a", "sha": "sh/a", "kha": "kh/a",
    "tha": "t/a", "tsa": "ts/a", "qa": "q/a",
    "ih": "'/i", "eh": "'/e", "oh": "'/o", "uh": "'/u",
}
# The written form the booth actually put on the screen, so the board can tell the
# difference between "this exact written syllable was recorded" and "a syllable that
# sounds the same was recorded". BOARD-220.json itself says kamats and patah are one
# sound (140 distinct sounds from 220 written forms) -- but the reader is looking at
# the written form, so the board must not silently pretend the two are the same file.
WRITTEN_OF_BOOTH = {
    "ah": "alef_patah", "aa": "alef_kamats",
    "ba": "bet_patah", "ma": "mem_patah", "la": "lamed_patah", "da": "dalet_patah",
    "ga": "gimel_patah", "pa": "pe_patah", "ta": "tet_patah", "na": "nun_patah",
    "ka": "kaf_patah", "ra": "resh_patah", "sa": "samekh_patah", "ha": "he_patah",
    "va": "vav_patah", "ya": "yod_patah", "za": "zayin_patah", "sha": "shin_patah",
    "kha": "het_patah", "tha": "tav_patah", "tsa": "tsadi_patah", "qa": "qof_patah",
    "ih": "alef_hiriq", "eh": "alef_segol", "oh": "alef_holam", "uh": "alef_shuruq",
}
# Whole words. Not syllables, not part of the 220 -- but they are real human takes of
# the milestone itself, and Iddo should be able to press them.
WORD_TAKES = {
    "abba": ("אַבָּא", "the word"),
    "ima": ("אִמָּא", "the word"),
    "iddo": ("עִידוֹ", "the word"),
    "saba": ("סָבָא", "the word"),
    "safta": ("סָבְתָא", "the word"),
}

# Sources refused, kept visible on /fringe rather than quietly skipped.
SCARS = [
    {
        "source": "voice-ant-farm/corpus-syllables",
        "takes": 624,
        "refused": "synthetic",
        "why": ("its own manifest.json names the generator: facebook/mms-tts-heb, a TTS "
                "model. 396 synthetic clips transfer to a real mouth at chance "
                "(6.1% vs 4.5%). A TTS clip on this board would sound like a syllable "
                "ERAN was never given."),
    },
    {
        "source": "voice-ant-farm/corpus-big/human",
        "takes": 23683,
        "refused": "unlabelled",
        "why": ("real human Hebrew, but dictation and cafe sessions -- whole utterances "
                "with no syllable label. Cutting syllables out of it needs a recogniser, "
                "and the recogniser scored 5/22 on clips whose answer was already known."),
    },
]

# --- minted booth ids for the sounds booth.py cannot record yet -----------------------
# booth.py's UNITS table reaches 21 of the 140 sounds: every consonant with /a/, plus
# four isolated vowels. The other 119 sounds have no prompt in the booth at all. The
# board mints a safe id for each ([a-z0-9]{1,12}, booth's own SAFE regex) so the drive
# list it exports is directly usable the day that table grows.
CONS_ID = {"'": "a", "b": "b", "g": "g", "d": "d", "h": "h", "v": "v", "z": "z",
           "kh": "kh", "t": "t", "y": "y", "k": "k", "l": "l", "m": "m", "n": "n",
           "s": "s", "p": "p", "ts": "ts", "q": "q", "r": "r", "sh": "sh"}
VOW_ID = {"a": "a", "e": "e", "i": "i", "o": "o", "u": "u", "@": "0", "a:": "2"}
SAFE_ID = re.compile(r"^[a-z0-9]{1,12}$")

NEKUDA_HE = {
    "kamats": "קָמָץ", "patah": "פַּתָּח", "tsere": "צֵירֵי", "segol": "סֶגּוֹל",
    "hiriq": "חִירִיק", "holam": "חוֹלָם", "qubuts": "קֻבּוּץ", "shuruq": "שׁוּרוּק",
    "shva": "שְׁוָא", "hataf": "חֲטָף",
}
LETTER_HE = {
    "alef": "אָלֶף", "bet": "בֵּית", "gimel": "גִּימֶל", "dalet": "דָּלֶת", "he": "הֵא",
    "vav": "וָו", "zayin": "זַיִן", "het": "חֵית", "tet": "טֵית", "yod": "יוֹד",
    "kaf": "כָּף", "lamed": "לָמֶד", "mem": "מֵם", "nun": "נוּן", "samekh": "סָמֶךְ",
    "ayin": "עַיִן", "pe": "פֵּא", "tsadi": "צָדִי", "qof": "קוֹף", "resh": "רֵישׁ",
    "shin": "שִׁין", "tav": "תָּו",
}

WAV = re.compile(r"^(?P<unit>[a-z0-9]{1,12})_(?P<mouth>t\d{2,})_(?P<n>\d+)\.wav$")


def bare_letter(hebrew):
    """The letter with its nekudot taken off: 'אָ' -> 'א', 'אוּ' -> 'א'."""
    plain = "".join(c for c in hebrew if not unicodedata.combining(c))
    return plain[:1] if plain else hebrew[:1]


def load_weave():
    with open(WEAVE_FILE, encoding="utf-8") as fh:
        return json.load(fh)


WEAVE = load_weave()
KNOTS = WEAVE["units"]
KNOT_BY_NAME = {k["unit"]: k for k in KNOTS}
LETTER_ORDER = []
for _k in KNOTS:
    if _k["letter"] not in LETTER_ORDER:
        LETTER_ORDER.append(_k["letter"])
NEKUDA_ORDER = []
for _k in KNOTS:
    if _k["nekuda"] not in NEKUDA_ORDER:
        NEKUDA_ORDER.append(_k["nekuda"])
SOUNDS = sorted({k["sound"] for k in KNOTS})

# first booth id that reaches a sound wins (curriculum order), else mint one
BOOTH_ID_OF_SOUND = {}
for _u, _s in SOUND_OF_BOOTH.items():
    BOOTH_ID_OF_SOUND.setdefault(_s, _u)


def booth_id_for(sound):
    if sound in BOOTH_ID_OF_SOUND:
        return BOOTH_ID_OF_SOUND[sound], True
    cons, vow = sound.split("/", 1)
    minted = CONS_ID[cons] + VOW_ID[vow]
    if not SAFE_ID.match(minted):
        raise ValueError("minted id is not booth-safe: %r" % minted)
    return minted, False


# =====================================================================================
# SENSING -- what is actually on disk. No guesses, no manifests, only files.
# =====================================================================================
_sense_lock = threading.Lock()
_sense_cache = {"at": 0.0, "tray": None}


def sense_trays():
    """Walk heard/ and hand back {booth_unit: [take, ...]}.

    A take is what a knot holds in its tray: which mouth said it, which sitting, which
    file. Nothing here reads a manifest -- if a wav is not on disk it does not exist.
    """
    trays = {}
    if not HEARD.exists():
        return trays
    for mouth_dir in sorted(HEARD.iterdir()):
        if not mouth_dir.is_dir() or not re.fullmatch(r"t\d{2,}", mouth_dir.name):
            continue
        for wav in sorted(mouth_dir.glob("*.wav")):
            m = WAV.match(wav.name)
            if not m or m.group("mouth") != mouth_dir.name:
                continue
            unit = m.group("unit")
            try:
                stat = wav.stat()
            except OSError:
                continue
            trays.setdefault(unit, []).append({
                "mouth": mouth_dir.name,
                "sitting": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d"),
                "wav": wav.name,
                "weight": stat.st_size,
            })
    for takes in trays.values():
        takes.sort(key=lambda t: (t["mouth"], t["wav"]))
    return trays


def fresh_trays():
    with _sense_lock:
        now = time.monotonic()
        if _sense_cache["tray"] is None or now - _sense_cache["at"] > SENSE_FRESH_BEATS:
            _sense_cache["tray"] = sense_trays()
            _sense_cache["at"] = now
        return _sense_cache["tray"]


def state_of(mass, mouths):
    """A knot's life, from its mass and its trace. Mass alone never turns it green."""
    if mass == 0:
        return "hollow"
    if mass < THRESHOLD_MASS:
        return "thin"
    if mouths < THRESHOLD_MOUTHS:
        return "alive"          # fed, but one mouth -- nothing to hold out
    return "whole"


def build_fringe():
    """The observable hem of the weave. Everything the page knows, it knows from here."""
    trays = fresh_trays()

    # a sound's tray is every take of every booth unit that carries that sound
    tray_of_sound = {}
    for unit, takes in trays.items():
        sound = SOUND_OF_BOOTH.get(unit)
        if sound is None:
            continue                      # words, and anything unrecognised
        tray_of_sound.setdefault(sound, []).extend(
            dict(t, booth_unit=unit) for t in takes)

    knots_out = []
    for k in KNOTS:
        sound = k["sound"]
        takes = tray_of_sound.get(sound, [])
        mouths = sorted({t["mouth"] for t in takes})
        sittings = sorted({t["sitting"] for t in takes})
        # was this exact WRITTEN form the one on the booth screen?
        exact_units = {u for u, w in WRITTEN_OF_BOOTH.items() if w == k["unit"]}
        exact = sum(1 for t in takes if t["booth_unit"] in exact_units)
        heard_as = sorted({t["booth_unit"] for t in takes})
        bid, in_booth = booth_id_for(sound)
        knots_out.append({
            "knot": k["unit"],
            "hebrew": k["hebrew"],
            "letter": k["letter"],
            "nekuda": k["nekuda"],
            "sound": sound,
            "mass": len(takes),
            "exact_mass": exact,
            "mouths": mouths,
            "trace_mouths": len(mouths),
            "sittings": sittings,
            "trace_sittings": len(sittings),
            "heard_as": heard_as,
            "state": state_of(len(takes), len(mouths)),
            "booth_id": bid,
            "booth_has_prompt": in_booth,
        })

    sound_mass = {s: len(tray_of_sound.get(s, [])) for s in SOUNDS}
    sound_mouths = {s: len({t["mouth"] for t in tray_of_sound.get(s, [])}) for s in SOUNDS}

    words = []
    for wid, (heb, gloss) in WORD_TAKES.items():
        takes = trays.get(wid, [])
        mouths = sorted({t["mouth"] for t in takes})
        words.append({
            "knot": wid, "hebrew": heb, "gloss": gloss,
            "mass": len(takes), "mouths": mouths, "trace_mouths": len(mouths),
            "state": state_of(len(takes), len(mouths)),
        })

    all_mouths = sorted({t["mouth"] for takes in trays.values() for t in takes})
    all_sittings = sorted({t["sitting"] for takes in trays.values() for t in takes})
    takes_on_disk = sum(len(v) for v in trays.values())

    # DRIVE -- hunger. What to record next, hardest hunger first.
    drive = []
    for s in SOUNDS:
        mass, mth = sound_mass[s], sound_mouths[s]
        st = state_of(mass, mth)
        if st == "whole":
            continue
        bid, in_booth = booth_id_for(s)
        written = [k["unit"] for k in KNOTS if k["sound"] == s]
        drive.append({
            "sound": s, "booth_id": bid, "booth_has_prompt": in_booth,
            "mass": mass, "trace_mouths": mth, "state": st,
            "written_forms": written, "unlocks": len(written),
            "hebrew": KNOT_BY_NAME[written[0]]["hebrew"] if written else "",
        })
    order = {"hollow": 0, "thin": 1, "alive": 2}
    drive.sort(key=lambda d: (order[d["state"]], -d["unlocks"], d["sound"]))

    return {
        "organ": "QOL",
        "hebrew": "לוח האותיות שנותן קול",
        "beat": int(time.time() - BORN),
        "born": datetime.fromtimestamp(BORN).isoformat(timespec="seconds"),
        "threshold": {"mass": THRESHOLD_MASS, "mouths": THRESHOLD_MOUTHS},
        "weave": {
            "written_knots": len(KNOTS),
            "distinct_sounds": len(SOUNDS),
            "letters": len(LETTER_ORDER),
            "nekudot": len(NEKUDA_ORDER),
        },
        "census": {
            "takes_on_disk": takes_on_disk,
            "mouths": all_mouths,
            "sittings": all_sittings,
            "sounds_alive": sum(1 for s in SOUNDS if sound_mass[s] > 0),
            "sounds_whole": sum(1 for s in SOUNDS
                                if state_of(sound_mass[s], sound_mouths[s]) == "whole"),
            "written_alive": sum(1 for k in knots_out if k["mass"] > 0),
            "written_whole": sum(1 for k in knots_out if k["state"] == "whole"),
            "written_exact": sum(1 for k in knots_out if k["exact_mass"] > 0),
            "booth_reachable_sounds": sum(1 for s in SOUNDS if booth_id_for(s)[1]),
            "syllable_takes_used": sum(len(v) for v in tray_of_sound.values()),
            "word_takes": sum(w["mass"] for w in words),
        },
        "letter_order": LETTER_ORDER,
        "nekuda_order": NEKUDA_ORDER,
        "letter_he": LETTER_HE,
        "nekuda_he": NEKUDA_HE,
        "bare": {ltr: bare_letter(next(k["hebrew"] for k in KNOTS if k["letter"] == ltr))
                 for ltr in LETTER_ORDER},
        "knots": knots_out,
        "words": words,
        "drive": drive,
        "scars": SCARS,
        "law": ("every spark on this board is a real human take from booth.py, where the "
                "prompt is the label. no TTS, ever."),
    }


def spark_path(knot_name, turn):
    """The wav a press should hand to the ear, or None. Never joins a user string."""
    knot = KNOT_BY_NAME.get(knot_name)
    trays = fresh_trays()
    if knot is not None:
        takes = []
        for unit, tk in trays.items():
            if SOUND_OF_BOOTH.get(unit) == knot["sound"]:
                takes.extend(dict(t, booth_unit=unit) for t in tk)
        takes.sort(key=lambda t: (t["booth_unit"], t["mouth"], t["wav"]))
    elif knot_name in WORD_TAKES:
        takes = [dict(t, booth_unit=knot_name) for t in trays.get(knot_name, [])]
    else:
        return None, None
    if not takes:
        return None, None
    take = takes[turn % len(takes)]
    path = (HEARD / take["mouth"] / take["wav"]).resolve()
    if HEARD.resolve() not in path.parents:
        return None, None
    if not path.is_file():
        return None, None
    return path, take


def drive_txt():
    """The hunger list in booth.py's own list format: id<TAB>text<TAB>hint."""
    fr = build_fringe()
    out = [
        "# QOL drive -- what ERAN has not been given, hungriest first.",
        "# generated %s by qol.py" % datetime.now().strftime("%Y-%m-%d %H:%M"),
        "# id<TAB>text<TAB>hint  -- same shape as booth/lists/core31.txt",
        "# ids marked NEW have no prompt in booth.py UNITS yet.",
        "",
    ]
    for d in fr["drive"]:
        heb = d["hebrew"]
        tag = "" if d["booth_has_prompt"] else "  # NEW"
        hint = "%s  (%s, פותח %d צורות כתובות)" % (d["sound"], d["state"], d["unlocks"])
        out.append("%s\t%s\t%s%s" % (d["booth_id"], heb, hint, tag))
    return "\n".join(out) + "\n"


def read_wishes():
    if DRIVE_FILE.exists():
        try:
            with open(DRIVE_FILE, encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            return {"wishes": []}
    return {"wishes": []}


def add_wish(knot_name):
    knot = KNOT_BY_NAME.get(knot_name)
    if knot is None:
        return None
    wishes = read_wishes()
    bid, in_booth = booth_id_for(knot["sound"])
    entry = {"knot": knot_name, "hebrew": knot["hebrew"], "sound": knot["sound"],
             "booth_id": bid, "booth_has_prompt": in_booth,
             "asked": datetime.now().isoformat(timespec="seconds")}
    if not any(w["knot"] == knot_name for w in wishes["wishes"]):
        wishes["wishes"].append(entry)
        tmp = DRIVE_FILE.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(wishes, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, DRIVE_FILE)
    return entry


BORN = time.time()

# =====================================================================================
# THE PAGE
# =====================================================================================
PAGE = r"""<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8">
<title>קוֹל — לוח האותיות של ערן</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{
  --paper:#fffdf7; --ink:#1a1f28; --dim:#68717f; --line:#e6e2d6;
  --whole:#1f8b4c; --alive:#8fb400; --thin:#e08a00; --hollow:#c9d0da;
  --hollowink:#8a94a3; --gold:#e6b800; --hot:#c0392b;
}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);
  font-family:"Segoe UI","Noto Sans Hebrew",Arial,sans-serif;}
header{position:sticky;top:0;z-index:9;background:rgba(255,253,247,.97);
  border-bottom:2px solid var(--line);padding:10px 14px;
  box-shadow:0 2px 10px rgba(0,0,0,.04)}
h1{margin:0;font-size:22px;letter-spacing:.5px}
h1 small{font-size:13px;color:var(--dim);font-weight:400;margin-inline-start:8px}
.bar{display:flex;flex-wrap:wrap;gap:12px;align-items:center;margin-top:8px}
.meter{flex:1 1 200px;min-width:190px}
.meter b{font-size:13px}
.meter .track{height:9px;background:#eee9dc;border-radius:6px;overflow:hidden;margin-top:3px}
.meter .fill{height:100%;background:var(--whole);border-radius:6px;transition:width .3s}
.meter .fill.part{background:var(--alive)}
.meter small{color:var(--dim);font-size:11px}
button{font-family:inherit;cursor:pointer}
.ctl{display:flex;gap:8px;flex:0 0 auto}
.ctl button{border:2px solid var(--ink);background:#fff;border-radius:10px;
  padding:8px 14px;font-size:15px;font-weight:600}
.ctl button.on{background:var(--hot);border-color:var(--hot);color:#fff}
.ctl button:active{transform:translateY(1px)}
.warn{margin-top:8px;background:#fff4f2;border:2px solid var(--hot);color:#7d2018;
  border-radius:10px;padding:7px 11px;font-size:13px;line-height:1.5}
main{padding:14px;max-width:1100px;margin:0 auto}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(118px,1fr));gap:11px}
.tile{border:2px solid var(--line);background:#fff;border-radius:14px;padding:9px 6px 7px;
  text-align:center;display:flex;flex-direction:column;align-items:center;gap:5px}
.tile .glyph{font-size:44px;line-height:1;font-weight:600}
.tile .name{font-size:12px;color:var(--dim)}
.dots{display:flex;gap:3px}
.dots i{width:8px;height:8px;border-radius:50%;background:var(--hollow);display:block}
.dots i.whole{background:var(--whole)} .dots i.alive{background:var(--alive)}
.dots i.thin{background:var(--thin)}
.tile:hover{border-color:var(--gold)}
.knot{border:2px solid var(--line);background:#fff;border-radius:14px;padding:10px 6px;
  text-align:center;display:flex;flex-direction:column;align-items:center;gap:4px;
  min-height:132px;justify-content:center}
.knot .glyph{font-size:42px;line-height:1.05;font-weight:600}
.knot .nk{font-size:12px;color:var(--dim)}
.knot .mass{font-size:11px;color:var(--dim)}
.knot.whole{border-color:var(--whole);background:#f3fbf6}
.knot.alive{border-color:var(--alive);background:#fbfdf0}
.knot.thin{border-color:var(--thin);background:#fff8ee}
.knot.hollow{border-style:dashed;border-color:var(--hollow);color:var(--hollowink);
  background:#fafbfc}
.knot.hollow .glyph{opacity:.42}
.knot.ringing{box-shadow:0 0 0 4px rgba(230,184,0,.45)}
.back{border:2px solid var(--ink);background:#fff;border-radius:10px;padding:7px 14px;
  font-size:15px;font-weight:600;margin-bottom:12px}
h2{font-size:19px;margin:18px 0 9px}
h2 span{color:var(--dim);font-size:13px;font-weight:400}
.legend{display:flex;flex-wrap:wrap;gap:14px;margin:14px 0;font-size:12px;color:var(--dim)}
.legend b{display:inline-block;width:12px;height:12px;border-radius:4px;
  vertical-align:-2px;margin-inline-end:5px}
.sheet{position:fixed;inset:auto 0 0 0;background:#fff;border-top:3px solid var(--ink);
  border-radius:16px 16px 0 0;padding:14px 16px 18px;max-height:74vh;overflow:auto;
  box-shadow:0 -6px 26px rgba(0,0,0,.16);display:none;z-index:20}
.sheet.open{display:block}
.sheet h3{margin:0 0 6px;font-size:20px}
.sheet code{background:#f3f1e8;border:1px solid var(--line);border-radius:7px;
  padding:5px 8px;display:block;direction:ltr;text-align:left;font-size:13px;
  margin:8px 0;white-space:pre-wrap;word-break:break-all}
.sheet .row{display:flex;gap:8px;flex-wrap:wrap;margin-top:9px}
.sheet .row button{border:2px solid var(--ink);background:#fff;border-radius:10px;
  padding:8px 13px;font-size:14px;font-weight:600}
.sheet .row button.go{background:var(--ink);color:#fff}
.mini{font-size:12px;color:var(--dim);line-height:1.6}
footer{padding:18px 14px 40px;max-width:1100px;margin:0 auto;color:var(--dim);
  font-size:12px;line-height:1.7;border-top:1px solid var(--line);margin-top:22px}
footer b{color:var(--ink)}
.scar{background:#fff8f6;border-inline-start:4px solid var(--hot);padding:6px 10px;
  border-radius:6px;margin:6px 0}
</style></head><body>
<header>
  <h1>קוֹל <small>לוח האותיות שנותן קול · 220 הברות בשתי לחיצות</small></h1>
  <div class="bar">
    <div class="meter"><b id="m1">…</b><div class="track"><div class="fill part" id="f1" style="width:0"></div></div><small>צלילים שיש להם הקלטה אנושית אמיתית</small></div>
    <div class="meter"><b id="m2">…</b><div class="track"><div class="fill part" id="f2" style="width:0"></div></div><small>הברות כתובות שאפשר לשמוע</small></div>
    <div class="meter"><b id="m3">…</b><div class="track"><div class="fill" id="f3" style="width:0"></div></div><small>שלמות: 3 טייקים ומ‑2 פיות לפחות</small></div>
    <div class="ctl">
      <button id="hush">🔇 השתק</button>
      <button id="stop">■ עצור</button>
    </div>
  </div>
  <div class="warn" id="warn" style="display:none"></div>
</header>

<main>
  <div id="letters"></div>
  <div id="panel" style="display:none"></div>
  <div class="legend">
    <span><b style="background:var(--whole)"></b>שלם — 3+ טייקים, 2+ פיות</span>
    <span><b style="background:var(--alive)"></b>חי — הוקלט, אבל פה אחד בלבד</span>
    <span><b style="background:var(--thin)"></b>דק — 1‑2 טייקים</span>
    <span><b style="background:var(--hollow)"></b>ריק — ערן לא קיבל את זה מעולם</span>
  </div>
  <div id="words"></div>
</main>

<div class="sheet" id="sheet"></div>

<footer id="foot"></footer>

<script>
"use strict";
// SACRED AUDIO. Read this before changing anything below.
//  * no Audio object exists until a human click makes one.
//  * no AudioContext, no getUserMedia, anywhere in this file.
//  * hushed means no Audio object is created at all -- not volume 0.
var FRINGE = null, MOUTH = null, HUSH = false, TURN = {}, RINGING = null;

function silence(){
  if (MOUTH){ try{ MOUTH.pause(); MOUTH.currentTime = 0; }catch(e){} MOUTH.src=""; MOUTH=null; }
  if (RINGING){ RINGING.classList.remove("ringing"); RINGING = null; }
}
document.getElementById("stop").onclick = silence;
document.getElementById("hush").onclick = function(){
  HUSH = !HUSH; this.classList.toggle("on", HUSH);
  this.textContent = HUSH ? "🔇 מושתק — לחץ לביטול" : "🔇 השתק";
  if (HUSH) silence();
};
document.addEventListener("keydown", function(e){ if(e.key==="Escape") silence(); });
document.addEventListener("visibilitychange", function(){ if(document.hidden) silence(); });

// ONE press == ONE spark. Nothing here runs unless a finger caused it.
function press(knot, el){
  silence();
  if (HUSH) return;
  var t = TURN[knot] = (TURN[knot]||0);
  TURN[knot] = t + 1;
  var a = new Audio();
  a.preload = "none";
  a.src = "/spark?knot=" + encodeURIComponent(knot) + "&turn=" + t;
  MOUTH = a; RINGING = el; if (el) el.classList.add("ringing");
  a.onended = function(){ if(el) el.classList.remove("ringing"); };
  a.onerror = function(){ if(el) el.classList.remove("ringing"); };
  a.play().catch(function(){ if(el) el.classList.remove("ringing"); });
}

function esc(s){ return String(s).replace(/[&<>"]/g, function(c){
  return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]; }); }

// Hebrew counts one, counts many. "1 פיות" is not Hebrew.
function nTake(n){ return n===1 ? "טייק אחד" : n+" טייקים"; }
function nMouth(n){ return n===1 ? "פה אחד" : n+" פיות"; }
function nSit(n){ return n===1 ? "ישיבה אחת" : n+" ישיבות"; }

function meter(id, fid, label, have, total){
  document.getElementById(id).textContent = label + " " + have + " / " + total;
  document.getElementById(fid).style.width = (total ? (100*have/total) : 0) + "%";
}

function drawLetters(){
  var f = FRINGE, byLetter = {};
  f.knots.forEach(function(k){ (byLetter[k.letter] = byLetter[k.letter]||[]).push(k); });
  var h = '<h2>אותיות <span>לחץ אות → 10 הניקודים שלה</span></h2><div class="grid">';
  f.letter_order.forEach(function(L){
    var ks = byLetter[L] || [];
    var dots = ks.map(function(k){ return '<i class="'+k.state+'"></i>'; }).join("");
    var live = ks.filter(function(k){ return k.mass>0; }).length;
    h += '<button class="tile" data-letter="'+esc(L)+'">'
       + '<span class="glyph">'+esc(f.bare[L]||"")+'</span>'
       + '<span class="name">'+esc(f.letter_he[L]||L)+'</span>'
       + '<span class="dots">'+dots+'</span>'
       + '<span class="name">'+live+'/10</span></button>';
  });
  document.getElementById("letters").innerHTML = h + "</div>";
  Array.prototype.forEach.call(document.querySelectorAll(".tile"), function(b){
    b.onclick = function(){ drawLetter(b.dataset.letter); };
  });
}

function drawLetter(L){
  var f = FRINGE;
  var ks = f.knots.filter(function(k){ return k.letter === L; });
  var h = '<button class="back" id="back">← כל האותיות</button>'
        + '<h2>'+esc(f.bare[L]||"")+' · '+esc(f.letter_he[L]||L)
        + ' <span>לחיצה על ריבוע = צליל אנושי אמיתי אחד</span></h2><div class="grid">';
  ks.forEach(function(k){
    var sub = k.mass ? (nTake(k.mass) + " · " + nMouth(k.trace_mouths))
                     : "ריק — הקלט אותי";
    h += '<button class="knot '+k.state+'" data-knot="'+esc(k.knot)+'">'
       + '<span class="glyph">'+esc(k.hebrew)+'</span>'
       + '<span class="nk">'+esc(f.nekuda_he[k.nekuda]||k.nekuda)+'</span>'
       + '<span class="mass">'+esc(sub)+'</span></button>';
  });
  var p = document.getElementById("panel");
  p.innerHTML = h + "</div>";
  p.style.display = "";
  document.getElementById("letters").style.display = "none";
  document.getElementById("back").onclick = function(){
    silence(); p.style.display="none";
    document.getElementById("letters").style.display="";
    closeSheet(); window.scrollTo(0,0);
  };
  Array.prototype.forEach.call(p.querySelectorAll(".knot"), function(b){
    var k = f.knots.filter(function(x){ return x.knot === b.dataset.knot; })[0];
    b.onclick = function(){
      if (k.mass > 0) press(k.knot, b);
      openSheet(k);
    };
  });
  window.scrollTo(0,0);
}

function closeSheet(){ document.getElementById("sheet").classList.remove("open"); }

function openSheet(k){
  var s = document.getElementById("sheet");
  var cmd = "cd D:\\CLAUDE\\eran-brain\\booth\n"
          + "# עידו שוב, אותו פה:\n"
          + "PYTHONIOENCODING=utf-8 python booth.py --talker t06 --units "
          + k.booth_id + " --takes 10\n"
          + "# מישהו חדש — פה שני. זה מה שחסר הכי הרבה:\n"
          + "PYTHONIOENCODING=utf-8 python booth.py --units " + k.booth_id
          + " --takes 10";
  var h = '<h3>'+esc(k.hebrew)+' <span class="mini">· '+esc(k.knot)
        + ' · צליל '+esc(k.sound)+'</span></h3>';
  if (k.mass > 0){
    h += '<p class="mini">'
       + '<b>'+nTake(k.mass)+'</b> אנושיים · <b>'+nMouth(k.trace_mouths)+'</b> ('
       + esc(k.mouths.join(", ")) + ') · <b>'+nSit(k.trace_sittings)+'</b> ('
       + esc(k.sittings.join(", ")) + ')<br>'
       + 'הוקלט תחת: <b>'+esc(k.heard_as.join(", "))+'</b>'
       + (k.exact_mass ? ' — כולל <b>'+k.exact_mass+'</b> בצורה הכתובה הזו בדיוק.'
                       : ' — <b>לא</b> בצורה הכתובה הזו; אותו צליל, ניקוד אחר.')
       + '</p>';
    if (k.trace_mouths < 2){
      h += '<p class="mini" style="color:#7d2018">פה אחד בלבד. אי אפשר לבחון את זה '
         + 'ב‑leave‑one‑session‑out — צריך מישהו נוסף שיקליט אותו.</p>';
    }
    h += '<div class="row"><button class="go" id="again">▶ שוב</button>'
       + '<button id="close">סגור</button></div>';
  } else {
    h += '<p class="mini">ריק. ערן לא שמע את הצליל הזה מעולם מפה אנושי.'
       + (k.booth_has_prompt ? '' :
          '<br><b>אין עדיין הנחיה בתא ההקלטה לצליל הזה</b> — booth.py מכיר '
          + FRINGE.census.booth_reachable_sounds + ' מתוך '
          + FRINGE.weave.distinct_sounds + ' הצלילים. המזהה <b>'
          + esc(k.booth_id) + '</b> מחכה מוכן, אבל <b style="color:#7d2018">הפקודה '
          + 'למטה תיכשל היום</b> עד שיוסיפו אותו לטבלת UNITS ב‑booth.py.')
       + '</p><code>'+esc(cmd)+'</code>'
       + '<div class="row"><button class="go" id="wish">➕ הוסף לרשימת ההקלטה</button>'
       + '<button id="copy">העתק פקודה</button>'
       + '<button id="close">סגור</button></div>';
  }
  s.innerHTML = h; s.classList.add("open");
  var c = document.getElementById("close"); if (c) c.onclick = closeSheet;
  var a = document.getElementById("again");
  if (a) a.onclick = function(){ press(k.knot, null); };
  var cp = document.getElementById("copy");
  if (cp) cp.onclick = function(){
    navigator.clipboard.writeText(cmd).then(function(){ cp.textContent="הועתק ✓"; },
      function(){ cp.textContent="העתק ידנית"; });
  };
  var w = document.getElementById("wish");
  if (w) w.onclick = function(){
    fetch("/drive/add?knot="+encodeURIComponent(k.knot), {method:"POST"})
      .then(function(r){ return r.json(); })
      .then(function(){ w.textContent = "ברשימה ✓"; })
      .catch(function(){ w.textContent = "לא נשמר"; });
  };
}

function drawWords(){
  var f = FRINGE;
  var live = f.words.filter(function(w){ return w.mass>0; });
  if (!live.length){ return; }
  var h = '<h2>מילים שלמות <span>לא חלק מ‑220 — אבל הן אמיתיות, והן המטרה</span></h2>'
        + '<div class="grid">';
  live.forEach(function(w){
    h += '<button class="knot '+w.state+'" data-word="'+esc(w.knot)+'">'
       + '<span class="glyph" style="font-size:32px">'+esc(w.hebrew)+'</span>'
       + '<span class="mass">'+nTake(w.mass)+' · '+nMouth(w.trace_mouths)+'</span></button>';
  });
  document.getElementById("words").innerHTML = h + "</div>";
  Array.prototype.forEach.call(document.querySelectorAll("[data-word]"), function(b){
    b.onclick = function(){ press(b.dataset.word, b); };
  });
}

function drawFoot(){
  var f = FRINGE, c = f.census;
  var h = '<p><b>מה יש על הדיסק ממש עכשיו:</b> '+c.takes_on_disk+' קבצי wav אנושיים — '
        + c.syllable_takes_used + ' הברות + ' + c.word_takes + ' מילים. '
        + 'פיות: <b>'+esc(f.census.mouths.join(", ") || "אין")+'</b>. '
        + 'ישיבות: <b>'+esc(f.census.sittings.join(", ") || "אין")+'</b>.</p>'
        + '<p>booth.py מגיע ל‑<b>'+c.booth_reachable_sounds+'</b> מתוך '
        + f.weave.distinct_sounds + ' הצלילים (22 עיצורים עם פתח + 4 תנועות). '
        + 'שאר ' + (f.weave.distinct_sounds - c.booth_reachable_sounds)
        + ' הצלילים עדיין בלי הנחיית הקלטה.</p>'
        + '<p><b>מה נדחה, ולמה:</b></p>';
  f.scars.forEach(function(s){
    h += '<div class="scar"><b>'+esc(s.source)+'</b> ('+s.takes+' קבצים) — נדחה: '
       + esc(s.refused) + '. ' + esc(s.why) + '</div>';
  });
  h += '<p class="mini">' + esc(f.law) + '<br>'
     + 'הדף הזה לא פותח מיקרופון ולא יוצר AudioContext. קול יוצא רק מלחיצה של אדם. '
     + 'פעימה ' + f.beat + '. <a href="/fringe">/fringe</a> · '
     + '<a href="/drive.txt">/drive.txt</a></p>';
  document.getElementById("foot").innerHTML = h;
}

fetch("/fringe").then(function(r){ return r.json(); }).then(function(f){
  FRINGE = f;
  meter("m1","f1","צלילים", f.census.sounds_alive, f.weave.distinct_sounds);
  meter("m2","f2","הברות כתובות", f.census.written_alive, f.weave.written_knots);
  meter("m3","f3","שלמות", f.census.written_whole, f.weave.written_knots);
  if (f.census.mouths.length < 2){
    var w = document.getElementById("warn");
    w.style.display = "";
    w.innerHTML = "<b>פה אחד בלבד.</b> כל " + f.census.takes_on_disk +
      " ההקלטות הן של " + esc(f.census.mouths.join(", ")) + ", ב" +
      nSit(f.census.sittings.length) + ". אין ממה לעשות leave‑one‑session‑out, ולכן " +
      "אף ריבוע לא יכול להיות ירוק. 100 טייקים מפה אחד שווים פחות מ‑3 טייקים מ‑3 פיות.";
  }
  drawLetters(); drawWords(); drawFoot();
});
</script>
</body></html>
"""


# =====================================================================================
# THE LOOM -- it answers, it never speaks first
# =====================================================================================
class Loom(http.server.BaseHTTPRequestHandler):
    server_version = "QOL/1.0"

    def _send(self, code, body, ctype, extra=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False, indent=1),
                   "application/json; charset=utf-8")

    def do_POST(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path == "/drive/add":
            knot = (q.get("knot") or [""])[0]
            entry = add_wish(knot)
            if entry is None:
                return self._json({"error": "no such knot", "knot": knot}, 404)
            return self._json({"wished": entry, "wishes": len(read_wishes()["wishes"])})
        self._json({"error": "not here"}, 404)

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        p = u.path

        if p in ("/", "/index.html"):
            return self._send(200, PAGE, "text/html; charset=utf-8")

        if p == "/fringe":
            return self._json(build_fringe())

        if p == "/beat":
            return self._json({"organ": "QOL", "beat": int(time.time() - BORN),
                               "alive": True})

        if p == "/knot":
            name = (q.get("knot") or [""])[0]
            fr = build_fringe()
            for k in fr["knots"]:
                if k["knot"] == name:
                    return self._json(k)
            return self._json({"error": "no such knot", "knot": name}, 404)

        if p == "/drive":
            return self._json(build_fringe()["drive"])

        if p == "/drive.txt":
            return self._send(200, drive_txt(), "text/plain; charset=utf-8")

        if p == "/wishes":
            return self._json(read_wishes())

        if p == "/spark":
            # a spark leaves only because a finger asked for it. one take, one press.
            name = (q.get("knot") or [""])[0]
            try:
                turn = int((q.get("turn") or ["0"])[0])
            except ValueError:
                turn = 0
            path, take = spark_path(name, max(turn, 0))
            if path is None:
                return self._json({"error": "hollow knot -- nothing to sound",
                                   "knot": name}, 404)
            body = path.read_bytes()
            return self._send(200, body, "audio/wav",
                              {"X-Qol-Mouth": take["mouth"],
                               "X-Qol-Take": take["wav"],
                               "X-Qol-Booth-Unit": take["booth_unit"]})

        self._json({"error": "not here", "path": p}, 404)

    def log_message(self, fmt, *args):
        if "/spark" in (args[0] if args else ""):
            sys.stdout.write("[qol] %s\n" % (fmt % args))
            sys.stdout.flush()


class Weave(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main():
    fr = build_fringe()
    c = fr["census"]
    print("QOL -- לוח האותיות שנותן קול")
    print("  weave        : %d written knots, %d distinct sounds"
          % (fr["weave"]["written_knots"], fr["weave"]["distinct_sounds"]))
    print("  takes on disk: %d human wavs, mouths=%s sittings=%s"
          % (c["takes_on_disk"], c["mouths"], c["sittings"]))
    print("  alive        : %d/%d sounds, %d/%d written knots"
          % (c["sounds_alive"], fr["weave"]["distinct_sounds"],
             c["written_alive"], fr["weave"]["written_knots"]))
    print("  whole        : %d/%d written knots (needs mass>=%d and mouths>=%d)"
          % (c["written_whole"], fr["weave"]["written_knots"],
             THRESHOLD_MASS, THRESHOLD_MOUTHS))
    print("  serving      : http://%s:%d/" % (BIND, PORT))
    sys.stdout.flush()
    Weave((BIND, PORT), Loom).serve_forever()


if __name__ == "__main__":
    main()
