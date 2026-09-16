# -*- coding: utf-8 -*-
"""darwish-ai/judge/common.py -- shared plumbing for the DARWISH judge + human gate.

Same shape as miko/teacher/common.py on purpose (Iddo, 2026-09-12: "one idea in
this house, not two"): utf8(), lower_priority(), jsonl read/write, an append-
only run log. The one thing this file does NOT carry over is call_fleet() --
see judge.py's docstring for why no fleet model is called here.

Paths point at the REAL files already on disk tonight, built by other slices
of the same swarm:
  RATINGS_CSV  -- his ear, captured (claude-cli-SONNET-psytaste's taste_server.py)
  MODES_DIR    -- body/modes.py, the scale table (claude-cli-SONNET-psymode)
  CORPUS_STATS -- real Darwish, transcribed and measured (darwish-ai/corpus_stats.json)
  REF_CLIPS    -- three real Darwish mp3s used for the human-or-machine blind test
This module only reads them; nothing here writes to another slice's files.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent               # D:\CLAUDE\darwish-ai\judge
DARWISH_AI = HERE.parent                              # D:\CLAUDE\darwish-ai
DATA = HERE / "data"
RUNS = HERE / "runs"
DATA.mkdir(exist_ok=True)
RUNS.mkdir(exist_ok=True)

RATINGS_CSV = Path(r"D:\CLAUDE\darwish-ai\darwish_ratings.csv")
TASTE_LOG = Path(r"D:\CLAUDE\_deliverables\darwish-taste\darwish_taste_log.jsonl")
CORPUS_STATS = DARWISH_AI / "corpus_stats.json"
REF_CLIPS_DIR = Path(r"D:\CLAUDE\_deliverables\darwish-ab\clips2")
REF_CLIPS = [REF_CLIPS_DIR / "human1.mp3", REF_CLIPS_DIR / "human2.mp3", REF_CLIPS_DIR / "human3.mp3"]

JUDGED_LOG = DATA / "judged_log.jsonl"          # every judge.py --score call, appended
QUEUE_MAP = DATA / "queue_mapping.jsonl"        # neutral_id -> true sample identity (never served)
GATE_STATUS = DATA / "gate_status.json"         # latest calibration verdict
GATE_LOG = DATA / "gate_log.jsonl"              # calibration history, one line per run
RUN_LOG = RUNS / "run_log.jsonl"                # step, held-out loss, judge score, his verdict

# The scale table lives in ONE place: darwish-midi/body/modes.py, built tonight
# by claude-cli-SONNET-psymode. Importing it (not copying the tuples) means a
# future change to the scale definitions cannot silently desync the judge from
# the renderer.
_MODES_DIR = Path(r"D:\CLAUDE\darwish-midi")
if str(_MODES_DIR) not in sys.path:
    sys.path.insert(0, str(_MODES_DIR))
from body.modes import SCALES  # noqa: E402  -- {"minor":..., "freygish":..., "hijaz":...}

ROOT_PC = 9  # A -- CORPUS_KEY_PC in eran4's midi_sample.py, root=45 (A1) in midi_out.bass_note()


def utf8() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def lower_priority() -> None:
    """BELOW_NORMAL on Windows. His mic and the live brains come first, always."""
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.kernel32.SetPriorityClass(
                ctypes.windll.kernel32.GetCurrentProcess(), 0x00004000)
        except Exception:
            pass


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def read_jsonl(path):
    p = Path(path)
    if not p.exists():
        return []
    out = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return out


def append_jsonl(path, rec) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def log_run(record: dict, path=None) -> Path:
    p = Path(path or RUN_LOG)
    record = dict(record)
    record.setdefault("ts", now())
    append_jsonl(p, record)
    return p


def kappa(a, b) -> float:
    """Cohen's kappa for two binary raters, plain arithmetic -- same formula as
    miko/teacher/judge.py's kappa(), kept identical on purpose."""
    n = len(a)
    if n == 0:
        return float("nan")
    agree = sum(1 for x, y in zip(a, b) if x == y) / n
    pa1, pb1 = sum(a) / n, sum(b) / n
    chance = pa1 * pb1 + (1 - pa1) * (1 - pb1)
    return (agree - chance) / (1 - chance) if abs(1 - chance) > 1e-12 else float("nan")


def load_corpus_stats() -> dict:
    if CORPUS_STATS.exists():
        return json.loads(CORPUS_STATS.read_text(encoding="utf-8"))
    return {}
