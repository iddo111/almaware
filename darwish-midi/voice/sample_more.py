"""voice/sample_more.py — sing a few extra songs from the CURRENT brain
without touching any persisted state.

Read-only wrt state/*: loads brain.json.gz + organs.json (for 5HT
temperature) exactly as darwish_life.py does at startup, then calls
voice.sing() the same way _sing_and_audition() does. Singing is
documented as ACh=0 ("the stage never rewires, it only tags") so this
never mutates the live organism's weights, and this script never saves
brain.json.gz/organs.json/metrics.jsonl back — only new files land in
songs/outbox/, which tap_server.py and darwish_life.py already read/write
concurrently without a lock. Safe to run next to the live dmidi-life
systemd unit. Not wired into the service; a manual utility only.
"""
import datetime
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "body"))
sys.path.insert(0, os.path.join(ROOT, "voice"))

import genome                  # noqa: E402
from brain import Brain        # noqa: E402
from chemistry import Chemistry  # noqa: E402
import voice                   # noqa: E402
import midi_out                # noqa: E402
import synth                   # noqa: E402
import psy_synth                # noqa: E402

STATE_DIR = os.path.join(ROOT, "state")
OUTBOX_DIR = os.path.join(ROOT, "songs", "outbox")


def main(n=2, seed0=99001):
    brain = Brain.load(os.path.join(STATE_DIR, "brain.json.gz"))
    with open(os.path.join(STATE_DIR, "organs.json"), "r", encoding="utf-8") as f:
        organs = json.load(f)
    bpm = psy_synth.corpus_bpm()
    for i in range(n):
        chem = Chemistry(organs.get("chemistry"))   # fresh copy each time, never saved
        song_id = f"chai-{datetime.datetime.now():%Y%m%d-%H%M%S}-x{i}"
        tokens, trace = voice.sing(brain, chem, bars=genome.SONG_BARS, seed=seed0 + i)
        os.makedirs(OUTBOX_DIR, exist_ok=True)
        voice.save_song(song_id, tokens, trace, OUTBOX_DIR)
        midi_out.write(os.path.join(OUTBOX_DIR, song_id + ".mid"), tokens, bpm=bpm)
        synth.render(os.path.join(OUTBOX_DIR, song_id + "-basic.wav"), tokens, bpm=bpm)
        dur = psy_synth.render(os.path.join(OUTBOX_DIR, song_id + ".wav"), tokens, bpm=bpm)
        m = psy_synth.measure_wav(os.path.join(OUTBOX_DIR, song_id + ".wav"))
        print(f"[sample_more] {song_id}: {dur:.1f}s @ {bpm:.1f} BPM  "
              f"rms={m['rms_dbfs']}dBFS truepeak={m['true_peak_dbfs']}dBFS "
              f"centroid={m['spectral_centroid_hz']}Hz low80={m['energy_below_80hz_fraction']}")


if __name__ == "__main__":
    main()
