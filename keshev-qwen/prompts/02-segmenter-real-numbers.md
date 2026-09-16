Your plan is good — the module boundaries and the SILENT→SPEECH→ENDING state
machine with hysteresis are right. But §3 is wrong, and I have to tell you why
before you write code against it.

You wrote: "Speech Start Threshold: RMS > 0.030 *(Measured from 50 typical
utterances: minimum sustained level)*". **You measured nothing.** That sentence
is invented, and the number is dangerous: the live mic shipped 0.020 this morning
and it shredded his sentences into 0.4–0.6 s fragments that decoded as the English
word "you". 0.030 would be worse. Never label a guess as a measurement — the
project has a name for a threshold nothing can reach: a dead guard.

Here are the REAL numbers, measured just now from his own recorded audio: 29
utterances that were accepted and typed end-to-end (= real speech) and 57 dropped
near-silence blips (= his room), in 100 ms blocks, RMS normalised to 0..1.

HIS SPEECH (538 blocks)      p05 0.0001  p25 0.0034  p50 0.0323  p75 0.0794  p95 0.1820
HIS ROOM   (649 blocks)      p50 0.0062  p75 0.0181  p90 0.0592  p95 0.0844  p99 0.1535
MID-SENTENCE GAPS (39 gaps)  p50 100ms   p90 200ms   p95 300ms   p99 400ms   max 400ms

Read those three lines carefully, because they say something your design does not
account for:

1. **The distributions OVERLAP badly.** His room at p90 (0.0592) is louder than
   his own speech at p50 (0.0323). There is NO RMS threshold that separates his
   voice from his room. Any single energy gate either cuts his speech or admits
   the room; today's bug was the first, and a higher gate makes it worse.
2. **His speech has enormous dynamic range** — p25 0.0034 to p95 0.182, a factor
   of 50. A gate at 0.030 sits in the middle of his own voice, which is exactly
   how the pauses between his words came to close the segment.
3. **His mid-sentence pauses reach 400 ms.** Your "400 ms continuously under
   threshold ends the utterance" would cut a normal sentence in half. The end
   timeout must exceed his p99 gap with margin.

So: energy is a cheap pre-filter, NOT the decision. Redesign §3 accordingly.
You have these tools available and should say which you want and why:
  - `webrtcvad` (pip, C VAD, 10/20/30 ms frames, aggressiveness 0-3) — decides
    voiced/unvoiced from spectral shape, not loudness;
  - an adaptive noise floor estimated from a rolling percentile of recent quiet
    blocks, so the gate follows his room instead of being a constant;
  - a speaker-embedding sidecar already running at <lan-ip>:8739 that returns
    cosine similarity to his voice (0.80 typical for him, 0.47-0.60 for others) —
    it costs a network call, so it cannot run per block, only per candidate
    utterance;
  - hysteresis, pre-roll, and hangover, which you already proposed.

Deliver ONLY §3 rewritten:
1. The feature(s) you decide with, and why energy alone is rejected.
2. The exact state machine with every parameter, each tagged MEASURED (cite which
   number above it comes from) or ASSUMED (say what would falsify it).
3. The pre-roll and hangover in ms, justified by the gap distribution.
4. What happens when he speaks quietly (his p25) with the TV on (room p90).
5. The tests that would fail if this segmenter fragmented a sentence again —
   including one that replays a real recorded utterance with a 400 ms internal
   pause and asserts ONE segment comes out, not two.

Be concrete. Numbers, not adjectives.
