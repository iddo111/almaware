# -*- coding: utf-8 -*-
"""test_grammar_keys_tempo.py -- musical-director grammar: exact tempo words
and key changes. No audio, no Ableton -- pure text in, command out. Run with
plain pytest or directly with `python test_grammar_keys_tempo.py`.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ABLETON_DIR = os.path.dirname(HERE)  # D:\CLAUDE\dj-alma\ableton
BRIDGE_DIR = os.path.join(os.path.dirname(ABLETON_DIR), "bridge")
for _p in (BRIDGE_DIR, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import protocol
from grammar import parse


def test_digits_first_bpm():
    p = parse("increase to 160 bpm")
    assert p is not None and p.command == "SET_TEMPO"
    assert p.param == protocol.bpm_to_param(160.0) == 127
    assert p.fields["bpm"] == 160.0


def test_tempo_word_first_still_works():
    p = parse("טמפו 143")
    assert p is not None and p.command == "SET_TEMPO"
    assert p.fields["bpm"] == 143.0


def test_bare_number_ignored():
    assert parse("160") is None  # bars? param? noise? never guessed


def test_go_to_c_sharp():
    p = parse("go to C#")
    assert p is not None and p.command == "SET_SONG_SCALE"
    assert p.fields["root_note"] == 1 and p.param == 1
    assert p.fields["scale_name"] == "Minor"  # documented default


def test_hebrew_key():
    p = parse("עבור לסול")
    assert p is not None and p.command == "SET_SONG_SCALE"
    assert p.fields["root_note"] == 7


def test_key_with_scale_word():
    p = parse("סולם לה מזור")
    assert p is not None and p.fields["scale_name"] == "Major"
    assert p.fields["root_note"] == 9


def test_stray_note_no_retune():
    assert parse("תן לי מי") is None  # "מי"=who, no key context
    assert parse("נגן") is not None  # PLAY still works


def test_old_shape_compatible():
    p = parse("נגן")
    assert p.command == "PLAY" and p.param == 0 and p.fields == {}


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"{len(fns)} passed")
