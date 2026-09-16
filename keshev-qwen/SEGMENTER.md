### §3: Voice Activity Detection (Redesigned)

#### 1. **Chosen Features**

We reject **RMS energy thresholds alone** due to severe overlap in the RMS distributions of speech and ambient room noise (**p90(room) = 0.0592 > p50(speech) = 0.0323**) and high dynamic range within his own speech (**factor of 50 from p25=0.0034 to p95=0.1820**).

Instead, we use:

- **WebRTC VAD (`webrtcvad`)**
  - Frame size: **20 ms**
  - Aggressiveness: **2**
  - Justification: Spectral shape-based detection avoids false triggers from loud transient noise like TV or fan hum.
  
- **Adaptive Noise Floor Estimator**
  - Rolling window: **last 5 seconds**
  - Percentile used: **p10**
  - Justification: Tracks slow changes in background noise without reacting to speech bursts.

- **Speaker Embedding Verification (sidecar service)**
  - Endpoint: `http://<lan-ip>:8739/v1/verify`
  - Minimum similarity threshold: **0.70**
  - Justification: Prevents typing other people’s voices; used only after candidate utterance is finalized.

- **Pre-roll & Hangover Durations**
  - Pre-roll: **300 ms**
  - Hangover: **600 ms**
  - Justification: Covers up to **p99 mid-sentence gap = 400 ms**, with safety margin.

---

#### 2. **State Machine Definition**

States:
```python
SILENT     # No voice activity detected recently
SPEECH     # Active voice detected
ENDING     # Voice stopped but waiting for hangover timeout
```

Transitions and Parameters:

| Transition | Condition | Value |
|------------|-----------|-------|
| `SILENT → SPEECH` | ≥ 3 consecutive 20-ms VAD frames = VOICED <br> AND RMS(block) > adaptive_floor + 0.01 | ASSUMED: +0.01 ensures VAD isn’t triggered by pure sine tones |
| `SPEECH → ENDING` | Next 200 ms contains < 40 ms of VAD=VOICED <br> OR <br> RMS drops below adaptive_floor for 200 ms straight | MEASURED: Mid-sentence gaps ≤ 400 ms; allow up to 20% voiced content over 200 ms |
| `ENDING → SPEECH` | Any single 20-ms frame = VOICED during hangover | ASSUMED: Resumes active speech if interruption brief |
| `ENDING → SILENT` | After 600 ms since last VAD=VOICED | MEASURED: p99(gap)=400ms ⇒ 600ms hangover gives safe margin |

Initial State: `SILENT`

---

#### 3. **Pre-Roll and Hangover Duration**

- **Pre-roll**: **300 ms**
  - Justification: Ensures leading consonants aren't clipped even when onset is soft (**p25 RMS = 0.0034**).
- **Hangover**: **600 ms**
  - Justification: Measured maximum intra-utterance silence = **400 ms**, so adding **200 ms safety margin** prevents premature truncation.

---

#### 4. **Handling Quiet Speech With TV On**

Scenario:
- User speaks at **p25 RMS = 0.0034**
- Background TV raises room RMS to **p90 = 0.0592**

Behavior:
- Energy-only system would miss this.
- Our hybrid approach:
  - WebRTC VAD detects voiced phonemes regardless of absolute amplitude.
  - Adaptive floor rises with ambient noise but doesn’t suppress actual voiced frames.
  - Final speaker verification rejects imposters post-hangover.

Result: **Quiet speech still activates VAD and gets transcribed correctly.**

---

#### 5. **Segmentation Tests**

All tests assume replay of real recorded utterances via mock microphone input.

##### Test 1: Fragmentation Rejection
```text
Input: Real utterance with internal 400 ms pause
Expected Output: One continuous segment
Assertion: len(segments) == 1
```
If segmentation splits it due to hangover timeout too soon (<600 ms), test fails.

##### Test 2: Speaker Filtering
```text
Input: Utterance spoken by someone else (cos sim ≈ 0.5)
Expected Output: Segment discarded before typing
Assertion: No text typed into window
```
If impostor passes through because speaker check skipped or threshold set too low, test fails.

##### Test 3: Adaptive Floor Tracking
```text
Setup: Inject synthetic white noise at RMS=0.06 (simulate TV)
Then speak normally at RMS=0.04
Expected Output: Utterance captured despite lower-than-background RMS
Assertion: len(segments) == 1 && typed successfully
```
Failure indicates reliance on static energy threshold rather than adaptive filtering.

##### Test 4: Silence Rejection
```text
Input: Room noise at p90 RMS = 0.0592 for 10 seconds
Expected Output: No segments generated
Assertion: len(segments) == 0
```
If any segment forms due to misconfigured VAD sensitivity or floor drift, test fails.

--- 

This redesign enforces robustness to overlapping energy levels, preserves full utterances across natural pauses, and filters out non-user speech using multi-layered validation.