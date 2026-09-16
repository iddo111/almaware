# -*- coding: utf-8 -*-
"""compose.py — DJ ALMIDO's composer: model tokens -> a MIDI the renderer plays.

לזכרה של עלמה ז״ל ולזכרו של לָאוֹר ז״ל.

DJ ALMIDO is עלמה + עידו. The name is his sister and himself, on the decks,
and the move is Darwish's move: take the loss and turn it into something that
can be heard.

WHERE THIS SITS
---------------
`dj-alma/bridge/` is the DAW arm: an 18-command Hebrew grammar, a MIDI wire
protocol and a Mixcraft controller script. It is finished and tested, and it
CANNOT MAKE A SOUND on this machine, because neither Mixcraft nor loopMIDI is
installed (verified 2026-09-04, re-verified 2026-09-05). So the booth is the
other arm: same grammar, no DAW, straight to audio through psy_render_v4.

WHAT THIS FILE DOES AND, MORE IMPORTANTLY, WHAT IT DOES NOT
------------------------------------------------------------
It asks the Darwish model for tokens, decodes them with the v2 alphabet, cuts a
passage of the requested length, and hands the renderer the list of SIMULTANEOUS
pitches it needs in order to play a chord as a chord.

It does not compose. There is no progression generator here, no chord table, no
key-aware voice leading. If harmony comes out, the model put it there; if it
does not, this file will not paper over it. Every take records which source
produced it -- `model-v2` or `corpus-transcription` -- and the page prints that
label beside the audio, so nobody has to guess whether they are hearing the
transformer or a fallback.

WHAT IS HIS AND WHAT IS THE ENGINE'S
-------------------------------------
The model's: every pitch, every duration, every chord, the drum pattern.
The engine's: timbre, the 38-bar arrangement, the mix — exactly the division
psy_render_v4 already documents, unchanged.
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter

DARWISH_AI = r"D:\CLAUDE\darwish-ai"
GALERIA = r"D:\CLAUDE\eran-brain\judging\galeria\darwish"
for _p in (DARWISH_AI, os.path.join(DARWISH_AI, "code-midi"), GALERIA):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import poly_tok as PT                                            # noqa: E402

CKPT_V2 = os.path.join(DARWISH_AI, "ckpt-poly", "best.pt")
TOKENS_POLY = os.path.join(DARWISH_AI, "tokens-poly")

# Hebrew section names -> how the passage should feel. The model produces one
# long stream; a section is a WINDOW over it chosen by measuring the model's own
# output, not a different generator per section.
SECTIONS = {
    "SECTION_INTRO":  {"he": "אינטרו",    "en": "intro",     "want": "sparse"},
    "SECTION_BUILD":  {"he": "בילד אפ",   "en": "build-up",  "want": "rising"},
    "SECTION_DROP":   {"he": "דרופ",      "en": "drop",      "want": "dense"},
    "SECTION_BREAK":  {"he": "ברייקדאון", "en": "breakdown", "want": "harmonic"},
    "SECTION_OUTRO":  {"he": "אאוטרו",    "en": "outro",     "want": "sparse"},
}


def _density(sc: PT.Score, s0: int, s1: int):
    """(onset density, mean simultaneous pitches, drum density) in a window."""
    notes = [n for n in sc.notes if s0 <= n.step < s1]
    drums = [d for d in sc.drums if s0 <= d.step < s1]
    span = max(s1 - s0, 1)
    if not notes:
        return 0.0, 0.0, len(drums) / span
    active = [0] * span
    for n in notes:
        for s in range(max(n.step, s0), min(n.step + n.dur, s1)):
            active[s - s0] += 1
    sounding = [a for a in active if a]
    return (len({n.step for n in notes}) / span,
            sum(sounding) / max(len(sounding), 1),
            len(drums) / span)


def pick_window(sc: PT.Score, bars: int, want: str):
    """Choose the passage that best matches what the Hebrew command asked for.

    Selection is by MEASUREMENT of the model's own output — the densest window
    becomes the drop, the most harmonic one becomes the breakdown. Nothing is
    generated differently per section; the same stream is read differently.
    """
    span = bars * PT.STEPS_PER_BAR
    best, best_s, best_info = None, 0, {}
    for s0 in range(0, max(sc.n_steps - span, 1), PT.STEPS_PER_BAR):
        od, poly, dd = _density(sc, s0, s0 + span)
        if want == "dense":
            v = 2.0 * od + 1.0 * dd + 0.5 * poly
        elif want == "sparse":
            v = -(1.6 * od + 1.0 * dd) + 0.4 * poly
        elif want == "harmonic":
            v = 2.5 * poly + 0.4 * od - 0.6 * dd
        else:                                        # rising
            a = _density(sc, s0, s0 + span // 2)
            b = _density(sc, s0 + span // 2, s0 + span)
            v = (b[0] - a[0]) * 3.0 + (b[2] - a[2]) * 2.0
        if best is None or v > best:
            best, best_s = v, s0
            best_info = {"onset_density": round(od, 3),
                         "poly_mean": round(poly, 3),
                         "drum_density": round(dd, 3),
                         "window_score": round(v, 3)}
    return best_s, best_s + span, best_info


def slice_score(sc: PT.Score, s0: int, s1: int, bpm: float) -> PT.Score:
    notes = [PT.Note(n.step - s0, n.midi, max(1, min(n.dur, s1 - n.step)))
             for n in sc.notes if s0 <= n.step < s1]
    drums = [PT.Drum(d.step - s0, d.which, d.vel)
             for d in sc.drums if s0 <= d.step < s1]
    return PT.Score(bpm, sc.key_pc, s1 - s0, notes, drums).normalised()


def chord_events(sc: PT.Score, min_voices=2, max_events=64):
    """[(bar_float, [midi,...])] — the SIMULTANEOUS pitches, for the pad voice.

    Only genuine verticals: a bar's chord is the set of pitches sounding
    together at its downbeat, emitted only when there are at least two. If the
    model wrote no harmony this list comes back EMPTY, the renderer is given
    chord_notes=None, and the page says so. That is the point of not having a
    progression layer to fall back on.
    """
    out = []
    bars = max(sc.n_steps // PT.STEPS_PER_BAR, 1)
    for b in range(bars):
        s = b * PT.STEPS_PER_BAR
        sounding = sorted({n.midi for n in sc.notes if n.step <= s < n.step + n.dur})
        if len(sounding) >= min_voices:
            out.append((float(b), sounding[:5]))
        if len(out) >= max_events:
            break
    return out


def from_model(ckpt, bars=16, want="dense", seed=17, temp=1.1, n_tokens=1500,
               device="cpu", tries=4):
    """Sample until the passage is long enough to arrange, then cut a window.

    n_tokens is sized to the request, not set large "to be safe": sampling has
    no KV cache, so it is O(n^2) and the first take measured 695 s for 4000
    tokens (63 bars) to fill a 16-bar window. At v2's measured 3.4 tokens per
    step, 1500 tokens is ~28 bars -- enough headroom to choose a window from,
    and about five times faster.

    The retry is not cherry-picking for quality — nothing about the MUSIC is
    scored here. It exists because a model can legitimately emit EOS early and
    the renderer needs at least `bars` bars of material. Every attempt is
    counted and reported, so a checkpoint that needs four tries to produce
    sixteen bars cannot look like one that produced them first time.
    """
    import poly_sample as PS
    model, cfg, ck = PS.load(ckpt, device)
    need = bars * PT.STEPS_PER_BAR
    attempts = []
    full = None
    for i in range(tries):
        toks, ent = PS.generate(model, n_tokens=n_tokens, temperature=temp,
                                top_k=0, seed=seed + i * 101, device=device,
                                grammar=True, min_tokens=n_tokens // 2)
        cand = PT.decode(toks, 143.55, 0, source=ckpt)
        attempts.append({"seed": seed + i * 101, "tokens": len(toks),
                         "steps": cand.n_steps, "notes": len(cand.notes)})
        if full is None or cand.n_steps > full.n_steps:
            full = cand
        if cand.n_steps >= need:
            full = cand
            break
    s0, s1, info = pick_window(full, bars, want)
    return slice_score(full, s0, s1, full.bpm), {
        "attempts": attempts, "n_attempts": len(attempts),
        "source": "model-v2", "ckpt": ckpt, "model_step": ck.get("step"),
        "heldout_ce": ck.get("best_held"), "n_tokens_generated": len(toks),
        "entropy_by_window_bits": ent, "window": info,
        "full_steps": full.n_steps, "temp": temp, "top_k": 0, "seed": seed,
    }


def from_corpus(bars=16, want="dense", seed=17):
    """Fallback: a passage of REAL Darwish, as heard by poly_hear.

    Used only when no trained v2 checkpoint exists yet. Labelled
    `corpus-transcription` everywhere, so it can never be mistaken for the
    model's own composition.
    """
    import random
    if not os.path.isdir(TOKENS_POLY):
        raise RuntimeError("no tokens-poly on this machine")
    files = sorted(f for f in os.listdir(TOKENS_POLY) if f.endswith(".json"))
    if not files:
        raise RuntimeError("tokens-poly is empty")
    rnd = random.Random(seed)
    d = json.load(open(os.path.join(TOKENS_POLY, rnd.choice(files)), encoding="utf-8"))
    full = PT.decode(d["tokens"], d["bpm"], d["key_pc"], source=d["path"])
    s0, s1, info = pick_window(full, bars, want)
    return slice_score(full, s0, s1, full.bpm), {
        "source": "corpus-transcription",
        "track": os.path.basename(d["path"]), "window": info,
        "full_steps": full.n_steps, "seed": seed,
    }


def have_model() -> bool:
    return os.path.exists(CKPT_V2)


def compose(bars=16, section="SECTION_DROP", seed=17, bpm=None, device="cpu"):
    want = SECTIONS.get(section, SECTIONS["SECTION_DROP"])["want"]
    if have_model():
        # ~3.4 tokens per sixteenth measured on the corpus, plus 75% headroom so
        # pick_window has real choice rather than one candidate.
        budget = int(bars * PT.STEPS_PER_BAR * 3.4 * 1.75)
        sc, meta = from_model(CKPT_V2, bars=bars, want=want, seed=seed,
                              device=device, n_tokens=max(800, budget))
    else:
        sc, meta = from_corpus(bars=bars, want=want, seed=seed)
    if bpm:
        sc.bpm = float(bpm)
    prof = sc.polyphony_profile()
    ch = chord_events(sc)
    meta.update({
        "section": section, "section_he": SECTIONS[section]["he"],
        "section_en": SECTIONS[section]["en"], "bars": bars,
        "bpm": round(sc.bpm, 2), "key_pc": sc.key_pc,
        "n_notes": prof["n_notes"], "n_drums": len(sc.drums),
        "poly_max": prof["max"], "poly_mean_sounding": prof["mean_sounding"],
        "poly_frac_steps_2plus": prof["frac_steps_poly"],
        "n_chord_events": len(ch),
        "pitch_classes": dict(Counter(n.midi % 12 for n in sc.notes)),
        "roles": role_summary(sc),
        "bass_roots": {str(k): v for k, v in bass_roots(sc).items()},
    })
    return sc, ch, meta


# ===================================================== VOICE SEPARATION ====
# Iddo, 2026-09-05 18:35, after hearing the first four takes:
#   "האלמידו נשמע רע ברמות, אין לזה שום הרמוניה, שום מלודיה. גועל נפש."
#
# Measured before changing anything: the chords WERE in the MIDI (max 6-10
# simultaneous pitches, mean 2.3-2.9). They were not the problem. Two things
# were, and both live between the composition and the speaker:
#
#   1. `PT.score_to_midi` writes EVERY pitched note on channel 0 with ONE
#      program (81). Bass, lead and inner chord voices arrive as one timbre.
#   2. `psy_render_v4` then reads that flat channel-0 list with
#      `load_ch0_notes` and lays it on a monophonic grid, bumping collisions
#      forward -- so a chord is heard as an arpeggio in a single voice.
#
# This file now assigns each of the model's notes a ROLE, taken from the
# model's own vertical structure, and writes each role to its own channel and
# its own GM program. Nothing is transposed and nothing is invented: the same
# notes, sorted into voices.
#
# THE RULE, stated so it can be argued with:
#   * of the notes sounding together at a given moment, the HIGHEST is lead
#     and the LOWEST is bass; anything between them is an inner (pad) voice.
#   * a note sounding alone is bass if it is below MIDI 52 (the same register
#     line the booth's piano roll already draws in red), otherwise lead.
# If the model wrote no low register in a take, the bass role comes back
# EMPTY and that is reported rather than filled in.
ROLE_CHANNEL = {"lead": 0, "bass": 1, "pad": 2}
ROLE_PROGRAM = {"lead": 81, "bass": 38, "pad": 89}   # square lead, synth bass, warm pad
SOLO_BASS_BELOW = 52


def split_roles(sc: PT.Score) -> list[str]:
    """One role per note, in the order sc.notes is given. See the rule above."""
    notes = sc.notes
    roles = []
    for n in notes:
        grp = [m for m in notes
               if m.step < n.step + n.dur and n.step < m.step + m.dur]
        if len(grp) <= 1:
            roles.append("bass" if n.midi < SOLO_BASS_BELOW else "lead")
            continue
        hi = max(m.midi for m in grp)
        lo = min(m.midi for m in grp)
        if n.midi == hi:
            roles.append("lead")
        elif n.midi == lo:
            roles.append("bass")
        else:
            roles.append("pad")
    return roles


def role_notes(sc: PT.Score, role: str) -> list[PT.Note]:
    return [n for n, r in zip(sc.notes, split_roles(sc)) if r == role]


def bass_roots(sc: PT.Score) -> dict:
    """{bar_index: midi} from the model's OWN bass-role notes.

    The renderer otherwise votes a bar's bass root out of the lead line, which
    is a guess about a part the model actually wrote. Bars with no bass-role
    note are simply absent from this dict and the renderer keeps its old
    behaviour for them -- no bar is invented.
    """
    out = {}
    bars = {}
    for n in role_notes(sc, "bass"):
        bars.setdefault(n.step // PT.STEPS_PER_BAR, []).append(n)
    for b, ns in bars.items():
        ns.sort(key=lambda x: (x.step, x.midi))
        out[b] = int(ns[0].midi)          # first (and lowest) bass note of the bar
    return out


def role_summary(sc: PT.Score) -> dict:
    roles = split_roles(sc)
    out = {}
    for r in ("lead", "bass", "pad"):
        ms = [n.midi for n, rr in zip(sc.notes, roles) if rr == r]
        out[r] = {"n": len(ms),
                  "midi_lo": min(ms) if ms else None,
                  "midi_hi": max(ms) if ms else None}
    return out


def write_midi(sc: PT.Score, path):
    """Write the score with each ROLE on its own channel and GM program.

    Channels: 0 lead, 1 bass, 2 pad, 9 drums. This replaces
    `PT.score_to_midi`, which wrote all pitched notes to channel 0 under one
    program -- correct for a tokenizer round-trip, wrong for anything that has
    to be heard. `poly_tok` itself is untouched, because the training pipeline
    round-trips through it and must not move.
    """
    import mido
    tpb, grid = 480, 16
    tps = int(tpb * 4 / grid)
    mf = mido.MidiFile(ticks_per_beat=tpb)
    tr = mido.MidiTrack()
    mf.tracks.append(tr)
    tr.append(mido.MetaMessage("set_tempo",
                               tempo=int(60_000_000 / max(sc.bpm, 1e-6)), time=0))
    for role, ch in ROLE_CHANNEL.items():
        tr.append(mido.Message("program_change", channel=ch,
                               program=ROLE_PROGRAM[role], time=0))

    ev = []
    for n, r in zip(sc.notes, split_roles(sc)):
        ch = ROLE_CHANNEL[r]
        vel = {"lead": 100, "bass": 104, "pad": 78}[r]
        ev.append((n.step * tps, 1, ch, n.midi, vel))
        ev.append(((n.step + n.dur) * tps, 0, ch, n.midi, 0))
    for d in sc.drums:
        ev.append((d.step * tps, 1, 9, PT.GM_DRUM[d.which],
                   PT.DRUM_VEL_MIDI[d.vel]))
        ev.append((d.step * tps + tps // 2, 0, 9, PT.GM_DRUM[d.which], 0))
    ev.sort(key=lambda e: (e[0], e[1]))

    last = 0
    for tick, on, ch, note, vel in ev:
        tr.append(mido.Message("note_on" if on else "note_off", channel=ch,
                               note=int(note), velocity=int(vel),
                               time=max(0, tick - last)))
        last = tick
    mf.save(str(path))
    return path
