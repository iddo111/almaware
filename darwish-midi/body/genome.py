"""genome.py — ALL constants of Chai the Songbird in one legible file.

Tuning the bird = editing this file. Nothing else holds magic numbers.
"""

# --- vocabulary (frozen v0, byte-compatible with the adopted corpus) ---------
VOCAB = 108
TOK_BAR, TOK_PHRASE, TOK_BOS, TOK_EOS = 104, 105, 106, 107
STRUCTURAL = {TOK_BAR, TOK_PHRASE, TOK_BOS, TOK_EOS}
DRUM_BASE = 13                    # token = drums*13 + bass_degree  (drums 0..7)
STEPS_PER_BAR = 16
BARS_PER_PHRASE = 16

# --- brain -------------------------------------------------------------------
ORDER_MAX = 4                     # variable-order contexts, k = 1..4
GROW_MIN = 3                      # parent must be seen >= this to bear a child
GROW_SURPRISE = 2.0               # ...and still surprised by > this (bits)
MASS_MAX = 2_000_000              # synapse cap (metabolic budget)
FILE_MAX_MB = 32                  # brain.json.gz hard cap
W_MAX, W_MIN = 64.0, 0.05         # per-synapse ceiling / prune floor
LAMBDA_C = 2.0                    # reliability lambda(ctx) = n / (n + LAMBDA_C)
K_BUMP = 4.0                      # bar-phase bump sharpness (Gidon dendrite)
PHASE_GAIN = 0.35                 # how loudly phase cells vote

# --- plasticity (the three-factor rule) --------------------------------------
ETA0 = 1.0                        # online digestion learning rate
ETA_PARENT = 10.0                 # the father's voice is x10
TRACE_TAU = 128                   # eligibility decay, steps (= one phrase)
V_TAP = 1.0                       # thumb value; fire = 2.0
SCAR_SLEEPS = 3

# --- chemistry ---------------------------------------------------------------
DA_BASE, DA_MAX = 0.0, 2.0        # dopamine: reward-prediction-error gain
DA_TAU = 500                      # steps, EMA horizon for expected surprise
SEROTONIN_BASE = 0.5              # 5HT: patience/mood in [0,1]
ACH_FEED, ACH_PARENT, ACH_AUDIT, ACH_PERFORM = 1.0, 1.5, 0.2, 0.0

# --- drives ------------------------------------------------------------------
E_SET, HUNGER_LINE, SATIETY_LINE = 0.6, 0.4, 0.8
EAT_GAIN_MAX = 0.15               # most one meal can lift E (drives.eat)
# DW-01: HUNGER_LINE + EAT_GAIN_MAX = 0.55 < SATIETY_LINE, so a bird that only
# eats while below the hunger line can NEVER be sated and never sings. Hysteresis
# (keep eating until sated) is what makes the satiety line reachable; the boot
# gate drives.assert_satiety_reachable() refuses a genome where neither holds.
EAT_HYSTERESIS = True
SONG_COST = 0.25
GOLDILOCKS_LO, GOLDILOCKS_HI = 0.5, 4.0   # bits of surprise = nutritious band
APPETITE_PROBE = 512              # tokens sampled to estimate a shard's nutrition

# --- appetite / diet (DW-02: the meal is SAMPLED, never argmax) ---------------
MEAL_BETA = 8.0                   # softmax sharpness on nutrition (0 = uniform)
MEAL_RECENT_EXCLUDE = 8           # never repeat a shard inside this many meals
DIET_WINDOW = 200                 # meals kept in the diet histogram
DIET_WINDOW_MIN = 20              # ...before the dominance cap can bite
DIET_DOMINANCE_CAP = 0.5          # no shard may own more than half the window

# --- singing -----------------------------------------------------------------
T0 = 1.0                          # base sampling temperature (scaled by 5HT)
SONG_BARS = 32
# DW-01: a working loop sings roughly once per three meals. At ~2.75 beats/s that
# is ~1,300 songs/day, each a full psy_synth render (~12 MB of wav) on a box with
# no free memory. Cadence cap + outbox rotation ship WITH the fix, not after it.
SONG_MIN_INTERVAL_S = 900         # >= 15 min between songs
SONG_MAX_PER_DAY = 48             # ...and at most this many in a calendar day
OUTBOX_KEEP = 40                  # songs kept in songs/outbox (older -> archive)
SONG_SILENCE_WARN_BEATS = 20_000  # liveness: warn if the bird has not sung
CRITIC_VALENCE_GAIN = 0.3         # DW-04: the critic's verdict moves mood too

# --- housekeeping ------------------------------------------------------------
SLEEP_EVERY = 2000                # beats
SAVE_EVERY = 50_000               # digested tokens between persists
METRICS_HEARTBEAT_S = 60          # DW-07: idle beats are no longer journalled;
                                  # this is the seconds between heartbeat lines
SEED = 20260820
