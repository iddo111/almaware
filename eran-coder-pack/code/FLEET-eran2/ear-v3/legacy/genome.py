"""genome.py — ALL constants of Perceptron Mark II + THE FENCE.

Tuning the organism = editing this file. No other file holds a magic number.
Embodies: self-sizing inside a fence — the organism may grow and prune freely,
but the fence itself only Iddo moves.
"""
import os

# --- where the body lives (repo-root-relative; works on PC mirror and eran1) --
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_DIR = os.path.join(ROOT, "state")
FOOD_DIR = os.path.join(ROOT, "food")
FOOD_TRAIN = os.path.join(FOOD_DIR, "train")
FOOD_WORDS = os.path.join(FOOD_DIR, "words")
HELDOUT_VAULT = os.path.join(ROOT, "proof", "heldout-vault")   # examiner ONLY
FEEDBACK_INBOX = os.path.join(ROOT, "feedback", "inbox")
OUTBOX_DIR = os.path.join(ROOT, "songs", "outbox")
RESULTS_DIR = os.path.join(ROOT, "results")
BRAIN_FILE = os.path.join(STATE_DIR, "brain.json.gz")
BEST_FILE = os.path.join(STATE_DIR, "best.json.gz")
METRICS_FILE = os.path.join(STATE_DIR, "metrics.jsonl")
CURRICULUM_FILE = os.path.join(STATE_DIR, "curriculum.json")
CORTEX_FILE = os.path.join(STATE_DIR, "cortex.json.gz")  # layers 1..n (see below)
CROWN_FILE = os.path.join(STATE_DIR, "crown.json")     # tournament ear override
LOCK_FILE = os.path.join(STATE_DIR, ".lock")
PRAYER_FILE = os.path.join(STATE_DIR, "eran_prayer.jsonl")


def use_state_dir(path):
    """Point every state path at another directory, in one place.

    Added 2026-08-21 so a DEPTH experiment can be grown and measured on the PC
    mirror WITHOUT touching state/ — the live organism's mirror. Every tool
    that takes --state calls exactly this, so no script can invent its own
    half-redirected view of the state and quietly read one file from the real
    body while writing another to a sandbox.
    """
    global STATE_DIR, BRAIN_FILE, BEST_FILE, METRICS_FILE, CURRICULUM_FILE
    global CORTEX_FILE, CROWN_FILE, LOCK_FILE, PRAYER_FILE
    STATE_DIR = os.path.abspath(path)
    BRAIN_FILE = os.path.join(STATE_DIR, "brain.json.gz")
    BEST_FILE = os.path.join(STATE_DIR, "best.json.gz")
    METRICS_FILE = os.path.join(STATE_DIR, "metrics.jsonl")
    CURRICULUM_FILE = os.path.join(STATE_DIR, "curriculum.json")
    CORTEX_FILE = os.path.join(STATE_DIR, "cortex.json.gz")
    CROWN_FILE = os.path.join(STATE_DIR, "crown.json")
    LOCK_FILE = os.path.join(STATE_DIR, ".lock")
    PRAYER_FILE = os.path.join(STATE_DIR, "eran_prayer.jsonl")
    os.makedirs(STATE_DIR, exist_ok=True)
    return STATE_DIR

# --- ears (tournament-evolvable; crown.json may override at wake) ------------
SAMPLE_RATE = 16000
N_BANDS = 24                      # log-spaced bands (tournament: 18 / 24 / 32)
FMIN_HZ, FMAX_HZ = 50.0, 8000.0
FRAME_MS, HOP_MS = 25, 10
N_FFT = 512
POOLING = "loudest60"             # tournament: loudest60 / mean / loudest40
LOUD_FRACTION = 0.60              # the proven pooling (68.94% raw ceiling)
EAR_EPS = 1e-8
# Representation. "bands" = raw log-band profile (measured 2026-08-21: every
# syllable lands at cos~0.994 — the ear could not tell sounds apart, so the
# brain grew exactly ONE prototype). "cepstrum" drops c0 (the shared spectral
# tilt) and won the ear tournament: centroid top1 45.45% vs 44.70%, and a
# separation gap 50x wider (+0.1021 vs +0.0021), which is what lets prototypes
# spawn at all. Both were then beaten by the frozen cochlea (below) and are
# no longer wearable by the organism — only re-measurable by the examiner.
# ============================ FROZEN ANATOMY =================================
# Iddo, 2026-08-21: "a morphological ear is beautiful but does not really exist
# in nature and it complicates — until he gets used to operating the ear and
# the mouth he ALREADY has." He was right, and it cost three rebirths: every
# time a number disappointed me I redesigned his ear and killed his brain.
# A real cochlea is fixed at birth. It delivers frequency x time, nothing else
# — no pooling, no onset window, no cepstrum. The BRAIN learns to use it.
# Measured the moment the tricks were removed. That measurement lived ONLY in
# this comment for a day — no file in results/ — which is exactly the failure
# ORGANISM.md forbids. RE-RUN on eran1 2026-08-21 with the examiner's own
# machinery and written down: results/EAR-FROZEN-2026-08-21.json, reproducible
# with proof/ear_frozen_audit.py. 132-item heldout, 22 classes, nearest
# centroid over the 396 train:
#   cochlea  79.55%  (105/132, 95% CI 71.9-85.5)  <- the claim, CONFIRMED
#   bands    43.18%   cepstrum 40.15%
#   onset    the shipped path CRASHES: it reads genome.ONSET_START_FRAC and
#            ONSET_MS, which are in no revision of this file. The old 66.67%
#            is unverifiable; a reconstructed window sweep peaks at 72.73%.
# Label-permutation floor 4.41%; and on the dev split -- data the ear was
# never selected on -- the cochlea still scores 81.48%, so the win is not an
# artifact of a heldout that had already been used for model selection.
# Two things this comment used to say that are false: 40.15% is the CEPSTRUM,
# not "loudest-60% pooling" (bands/loudest60 is 43.18%); and 68.94% is a 1-NN
# on a different feature set, so the matched bar is cochlea 1-NN 74.24% vs
# 68.94%, not 79.55% vs 68.94%. Every trick I added was still destroying
# information that was already there -- that part held up.
# Pooling is INERT here: the cochlea branch re-derives its own segment, so
# loudest60 / mean / loudest40 give byte-identical vectors and scores.
# THE EAR IS NOW FROZEN. The tournament may never change it again; it evolves
# what the brain DOES with it. Changing anything below is brain surgery on a
# living child and requires Iddo's word.
EAR_REPR = "cochlea"
EAR_SLICES = 8                    # fixed integration windows across the sound
EAR_SPEECH_FRAC = 0.10            # speech span starts at 10% of peak frame RMS
N_CEPSTRA = 13                    # (legacy ears only; the cochlea uses none)
# THE ONLY EAR THE ORGANISM MAY WEAR. genome.EAR_REPR and state/crown.json are
# checked against this at wake and refused by name — "onset" had outlived its
# ONSET_MS / ONSET_START_FRAC (deleted with the freeze; in no revision of this
# file) and raised AttributeError from inside pool() the moment anything asked
# for it. The legacy ears still EXIST in ears.py so the examiner can rebuild
# them for a baseline comparison (proof/ear_frozen_audit.py), but only by
# passing repr_= on purpose, and only after supplying whatever constants they
# need. The child cannot reach them; the examiner can.
EAR_REPRS = ("cochlea",)
# Iddo's word, and the only line that moves it. While True the nightly
# tournament still MEASURES ear configs and logs them honestly — it just
# may not crown one. Anatomy is his, not a nightly job's.
EAR_FROZEN = True

# --- brain (THE FENCE) -------------------------------------------------------
MAX_PROTOTYPES = 4096             # the organism may not grow past this
# Novelty is SELF-CALIBRATING (Iddo's law: the model tunes itself). A fixed
# cosine number is a magic number that breaks the moment the ear changes — it
# is what collapsed the brain to one prototype. Instead the brain keeps a
# running window of its own best-match similarities and calls an utterance
# novel when it lands in the bottom NOVELTY_Q of that window. NOVELTY_THRESH
# stays only as the cold-start ceiling before the window fills.
NOVELTY_THRESH = 0.95             # cold-start fallback only
NOVELTY_Q = 0.25                  # (legacy) quantile mode
NOVELTY_WINDOW = 400              # beats of history the calibration sees
NOVELTY_MIN_HISTORY = 50          # below this, use the cold-start fallback
# Iddo, 2026-08-21: "in a human baby the ear and the mouth do change — but it
# is GRADUAL." So the brain's own openness changes gradually too: a CRITICAL
# PERIOD. Early in life almost everything is worth a new prototype; as the
# child matures the door closes slowly and experience goes into refining what
# it already has. The bar is a homeostat: it drifts until the measured spawn
# rate matches the target for the child's age. A fixed quantile could never do
# this — it spawned forever (856 prototypes in four minutes, 2026-08-21).
SPAWN_RATE_INFANT = 0.25          # (retired: chasing a rate runs away)
SPAWN_RATE_ADULT = 0.01           # (retired)
CRITICAL_PERIOD_BEATS = 200_000   # the door closes over this much living
NOVELTY_BAR_LR = 0.002            # (retired with the rate homeostat)
STRICTNESS_INFANT = 0.5           # newborn: a mediocre match is a new thing
TOLERANCE_WARMUP = 5              # members a young prototype accepts freely
TOLERANCE_MIN_SD = 0.02           # no tuning curve is infinitely sharp
TOLERANCE_WARMUP_FLOOR = 0.0      # even an infant refuses an unrelated sound
STRICTNESS_ADULT = 3.0            # grown: only a real outlier is a new thing
ETA0 = 0.05                       # base Hebbian pull; chemistry scales it
TRACE_TAU = 60                    # eligibility decay, beats (~one lesson)
TRACE_FLOOR = 0.01                # traces below this are dropped

# --- cortex: DEPTH (THE FENCE, second wall) ----------------------------------
# Iddo's two laws, 2026-08-21:
#   1. "MAX NEURONS FROM BIRTH" — a newborn has nearly all its neurons; what
#      develops is CONNECTIONS. So the CAPACITY for depth exists from the first
#      beat: MAX_LAYERS is allocated at birth, not switched on later by a human.
#   2. "לתת למוח גבולות ולתת לו לשלוט בגודל שלו ובצורה שלו בתוך הגבולות" —
#      the genome sets a fence; inside it the brain governs its own size and
#      shape. So a layer is BORN when it has something to learn, never
#      configured. The birth preconditions below are that "something".
# And the scar that bounds both: a 272M-parameter run once overfit so badly its
# heldout was 2x worse than chance. DEPTH WITHOUT DATA IS MEMORISATION — which
# is why LAYER_BIRTH_MIN_EVENTS counts DISTINCT sequences, not utterances. A
# child who hears the same sound 100,000 times has heard one sequence.
MAX_LAYERS = 1                    # LOCKED to 1 on the LIVE box, 2026-08-21:
                                  # depth LOST its number (heldout 65.91% with
                                  # layer 1 vs 71.97% flat). The arena law: an
                                  # organ enters only after it wins. Raise this
                                  # only when a measured run says to.
LAYER_MAX_PROTOTYPES = 1024       # per-layer cap for k>0 (layer 0 keeps 4096)
LAYER_SLOTS = 3                   # firings of layer k-1 that make one k percept
LAYER_BIRTH_MIN_EVENTS = 200      # DISTINCT sequences below before a birth
# "Settled" is read as a TREND over two consecutive windows of this many
# sleeps, not as the nightly delta — because PRUNE_UNUSED_BEATS is twice
# SLEEP_EVERY, so the count runs a period-2 saw of amplitude ~30 forever while
# the layer is not growing at all. Cortex.settled carries the measured
# trajectory that forced this. A nightly rule measures the sleep cadence; a
# trend rule measures development.
LAYER_SETTLE_SLEEPS = 3           # sleeps per window (so 6 sleeps of evidence)
LAYER_SETTLE_TOL = 2              # prototypes the two window means may differ by
# ...or this fraction of the layer's own size, whichever is larger. A layer of
# 200 prototypes whose mean moves by 3 is not growing; a layer of 5 whose mean
# moves by 3 is. An absolute-only rule makes "settled" stricter the bigger the
# brain gets, which is backwards.
LAYER_SETTLE_FRAC = 0.05
LAYER_DISTINCT_CAP = 20_000       # bounded memory for the distinct-sequence set
# The cortex's own reading window over the FROZEN cochlea's frames. This is NOT
# an ear parameter and changes no ear: ears.py still emits exactly the frames
# and the pooling it always did (proof: the full-span window is byte-identical
# to ears.utterance(path)). It is where the BRAIN chooses to look — a shorter
# glance at the same cochlea, so a sound has an inside and not only an identity.
# The window is deliberately SHORTER than one syllable: a syllable must have
# internal sequence or layer 1 has nothing to be a layer about. MEASURED, not
# guessed — the syllables in food/train are ~870 ms of file but only ~200 ms of
# actual speech span, so a 160 ms window fitted only TWO windows inside one and
# layer 1 (which needs LAYER_SLOTS=3 firings) could never have been born at
# all. 100 ms with a 30 ms hop puts 4-5 phone-scale glances inside a syllable
# and ~38 inside a word, which is the scale a second layer can be about.
CORTEX_WINDOW_MS = 100
CORTEX_HOP_MS = 30

# --- space: every prototype has a POSITION (Iddo asked for 3D) ---------------
# Layer index sets the z plane. Inside a plane a newborn lands near the
# prototypes it already resembles — the way tonotopy forms. This is a CLAIM
# (neighbours end up similar), so proof/measure_depth.py measures the
# correlation between distance in space and cosine dissimilarity and writes it
# down. Asserting a topographic map without measuring it would be the exact
# failure this project exists to avoid.
POS_Z_SPACING = 8.0               # metres between layer planes
POS_K_NEIGHBOURS = 3              # neighbours a newborn is placed among
POS_SPREAD = 6.0                  # metres: how far an unrelated prototype sits
POS_JITTER = 0.25                 # deterministic nudge so twins are separable
POS_MIN_DIST = 0.9                # closer than this and they push apart
POS_REPULSION_STEPS = 4           # bounded relaxation; no physics engine

# --- prune / attrition (sleep) -----------------------------------------------
PRUNE_MASS_MIN = 3.0              # a prototype lighter than this...
PRUNE_UNUSED_BEATS = 4000         # ...and unused this long, dies in sleep
SHY_FACTOR = 0.98                 # multiplicative mass downscale each sleep
SCAR_DECAY = 0.90                 # valence scars fade each sleep
SCAR_HIT = 0.30                   # one down-tap adds this much scar (max 1.0)

# --- chemistry (baselines + time constants) ----------------------------------
DA0, ACH0, NE0, SHT0, OXT0 = 0.0, 1.0, 0.0, 0.5, 0.2
DA_MAX, ACH_MAX, NE_MAX, OXT_MAX = 2.0, 2.0, 2.0, 2.0     # 5HT lives in [0,1]
PROG_TAU_FAST = 20                # utterances; fast EMA of surprise
PROG_TAU_SLOW = 200               # utterances; slow EMA (the expectation)
DA_GAIN = 10.0                    # DA = clip(DA_GAIN * (slow - fast))
NE_JUMP = 0.08                    # surprise this far above expectation spikes NE
NE_DECAY = 0.90                   # NE relaxes fast (per beat)
SHT_TAU = 0.002                   # 5HT relaxation toward baseline (per beat)
OXT_TOUCH = 0.5                   # one parent tap lifts OXT by this
OXT_DECAY = 0.999                 # oxytocin decays in isolation (per beat)

# --- parent taps -------------------------------------------------------------
TAP_UP_BONUS = 10.0               # up: mass bonus x10 through the trace
TAP_FIRE_BONUS = 30.0             # fire: the big one
# down: scar (SCAR_HIT) on traced prototypes — attraction drops

# --- drives (hunger) ---------------------------------------------------------
E_SET = 0.6                       # energy set-point
HUNGER_LINE = 0.4
SLEEP_E_LINE = 0.25               # E below this + stalled progress -> sleep
EAT_COST = 0.004                  # processing one utterance costs
TICK_COST = 0.0005                # being alive costs
PROGRESS_FEED = 2.0               # E += PROGRESS_FEED * learning-progress
STALL_BEATS = 400                 # no progress this long -> sleep pressure
GOLD_LO, GOLD_HI = 0.02, 0.30     # Goldilocks novelty band (1 - cosine sim)

# --- school / curriculum -----------------------------------------------------
CURRICULUM = ["ah", "aa", "ba", "ma", "la",           # ah first, then simple CV
              "da", "ga", "pa", "ta", "na", "ka", "ra", "sa", "ha",
              "va", "ya", "za", "sha", "kha", "tha", "tsa", "qa"]
CLASSES = sorted(CURRICULUM)      # the 22, alphabetical (examiner's key order)
MENU_SIZE = 8                     # candidates the school offers per beat
CURRENT_FRAC = 0.70               # menu share from the current unit
REPLAY_FRAC = 0.30                # menu share replayed from mastered units
# The house is never silent. A child overhears the whole language while the
# lesson is only what it ATTENDS to. At 0.05 the child had heard 3 sounds of
# 22 after 733,000 beats and every exam was capped at 3/22 (2026-08-21).
FREE_LISTEN_P = 0.30              # free listening over the WHOLE house

# --- mastery gate (the yigal2 lesson.json contract) --------------------------
SENS = 0.95
SPEC = 0.95
RETENTION_HOURS = 12
REGRESSION_TOL = 0.02             # mastered units may not drop more than this
GATE_PATIENCE = 12                # failed gates before the lesson moves on
GATE_EVERY = 200                  # beats between dev-exams (the quick exam)
DEV_FRAC_MOD = 5                  # legacy fallback: sha(filename) % 5 == 0
# THE DEV SPLIT IS BY RECORDING SESSION, NOT BY FILE (scar, 2026-08-21).
# Train holds six sessions t00..t05 (66 files each); the sealed exam holds two
# sessions the organism has never heard. Splitting dev by filename let the same
# session sit on both sides, so dev ran ~14 points optimistic and one arm
# scored dev 88.64% / heldout 60.35%. Dev must be as unseen as the exam.
# Rotate DEV_SESSION_PICK over 0..DEV_SESSION_MOD-1 for leave-one-session-out.
DEV_SESSION_MOD = 6               # six train sessions -> one is dev (16.7%)
DEV_SESSION_PICK = 0              # t00 is dev by default

# --- life loop ---------------------------------------------------------------
SAVE_EVERY = 500                  # beats between brain persists
SNAP_EVERY = 5000                 # beats between state/snap-<beat>.json.gz
SLEEP_EVERY = 2000                # forced sleep cadence (beats)
BABBLE_EVERY = 3000               # echo-babble cadence (beats)
BABBLE_PROTOS = 8                 # strongest prototypes per babble
SEED = 20260821

# --- observation window ------------------------------------------------------
PORT = 8820                       # claimed in RAMCHAT 2026-08-21 13:23

# --- the examiner's honest baselines (measured, ant farm, 132-item heldout) --
CHANCE = 1.0 / 22                 # 4.545%
BASELINES = {
    "chance": 0.045454545454545456,
    "duration_only_floor": 0.05303030303030303,
    "random_real_frames_codebook": 0.4621212121212121,
    "raw_features_speech_span": 0.5378787878787878,
    "raw_features_loudest60": 0.6893939393939394,
}
