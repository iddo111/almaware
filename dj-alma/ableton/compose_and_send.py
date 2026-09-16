# -*- coding: utf-8 -*-
"""compose_and_send.py -- CLI glue: ask the Darwish model (via
booth/compose.py, unmodified) for one section, convert it with
score_bridge.py, and send it to DJ_ALMIDO as one CREATE_MIDI_TRACK + one
WRITE_NOTES.

Not wired to any voice command yet -- bridge/grammar.py's 18 commands are
all transport/mixer/section-TRIGGER (fire an existing scene), none of them
says "compose me a new drop". This is the plumbing for a 19th command Iddo
can ask for later ("תכתוב לי דרופ חדש" or similar); today it is a CLI, useful
on its own for manual use and for smoke-testing WRITE_NOTES against a real
Live session without waiting on the voice path.

    python compose_and_send.py --section SECTION_DROP --bars 16 --name "ALMIDO Drop 1"
    python compose_and_send.py --dry-run --section SECTION_BREAK --bars 8
"""
import argparse

import score_bridge
import send
import compose  # booth/compose.py -- already on sys.path via score_bridge's own insert


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--section", default="SECTION_DROP", choices=list(compose.SECTIONS))
    ap.add_argument("--bars", type=int, default=16)
    ap.add_argument("--seed", type=int, default=17)
    ap.add_argument("--name", default=None)
    ap.add_argument("--track-index", type=int, default=None,
                     help="write into an existing track instead of creating one")
    ap.add_argument("--clip-slot", type=int, default=0)
    ap.add_argument("--host", default=send.HOST)
    ap.add_argument("--port", type=int, default=send.PORT)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    sc, ch, meta = compose.compose(bars=args.bars, section=args.section, seed=args.seed)
    notes = score_bridge.score_to_notes(sc)
    length_beats = score_bridge.score_length_beats(sc)
    print(f"composed {len(notes)} notes over {length_beats:.1f} beats "
          f"(source={meta.get('source')}, section={args.section})")

    with send.Sender(args.host, args.port, dry_run=args.dry_run) as sender:
        track_index = args.track_index
        if track_index is None:
            name = args.name or f"ALMIDO {args.section}"
            reply = sender.send_command("CREATE_MIDI_TRACK", name=name)
            if not reply.get("ok"):
                raise RuntimeError(f"CREATE_MIDI_TRACK failed: {reply.get('error')}")
            track_index = (reply["result"] or {}).get("track_index", 0)
            print(f"created track {track_index} ({name!r})")

        reply = sender.send_command(
            "WRITE_NOTES",
            track_index=track_index,
            clip_slot_index=args.clip_slot,
            notes=notes,
            clip_length_beats=length_beats,
        )
        if not reply.get("ok"):
            raise RuntimeError(f"WRITE_NOTES failed: {reply.get('error')}")
        result = reply["result"] or {}
        print(f"wrote {result.get('n_notes')} notes into track {track_index}, "
              f"clip slot {args.clip_slot}")


if __name__ == "__main__":
    main()
