"""ears.py — the shard streamer. The bird eats through here, and hears itself here.

Respects split.json (never feeds heldout). Refuses to write anywhere.
"""
import json
import os

import genome


class Ears:
    def __init__(self, food_dir, split_path):
        self.food_dir = food_dir
        with open(split_path, "r", encoding="utf-8") as f:
            split = json.load(f)
        self.train = list(split["train"])
        self.heldout = list(split["heldout"])

    def _shard_path(self, name):
        p = os.path.join(self.food_dir, name)
        if not os.path.exists(p) and not name.endswith(".json"):
            p = p + ".json"
        return p

    def load(self, name):
        with open(self._shard_path(name), "r", encoding="utf-8") as f:
            return json.load(f)

    def feed(self, name):
        """Yield (token, phase) for one shard. Phase = step-in-bar, 0..15.

        Phase advances only on musical (non-structural) tokens; BAR resets it —
        the bird carries the beat as cell activity, not as extra input.
        """
        shard = self.load(name)
        phase = 0
        for tok in shard["tokens"]:
            yield tok, phase
            if tok == genome.TOK_BAR:
                phase = 0
            elif tok not in genome.STRUCTURAL:
                phase = (phase + 1) % genome.STEPS_PER_BAR

    def audition(self, tokens):
        """Hear our own song: yield (token, phase) from a raw token list."""
        phase = 0
        for tok in tokens:
            yield tok, phase
            if tok == genome.TOK_BAR:
                phase = 0
            elif tok not in genome.STRUCTURAL:
                phase = (phase + 1) % genome.STEPS_PER_BAR
