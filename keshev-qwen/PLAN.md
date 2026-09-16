# KESHEV-QWEN Architecture

## 1. ARCHITECTURE

### **AudioCapture**
**Question:** What raw PCM samples are available from the USB microphone?
- **Inputs:** None (owns microphone device)
- **Outputs:** Stream of 16-bit signed integers @ 16kHz mono
- **Forbidden Knowledge:** Anything about segmentation, transcription, or typing logic

### **Segmenter**
**Question:** Where do meaningful speech segments begin and end in the audio stream?
- **Inputs:** Raw PCM samples from AudioCapture
- **Outputs:** Buffered audio chunks representing complete utterances
- **Forbidden Knowledge:** Decoding results, typing behavior, or language models

### **DiskBuffer**
**Question:** How do we durably store every captured utterance before it's processed?
- **Inputs:** Completed audio segments from Segmenter
- **Outputs:** Filesystem paths to stored WAV files + metadata journal entries
- **Forbidden Knowledge:** Transcription content, network protocols, or UI state

### **Transcriber**
**Question:** What did the speaker actually say in each buffered utterance?
- **Inputs:** Audio file paths from DiskBuffer + server endpoints
- **Outputs:** Structured transcription results with confidence metrics
- **Forbidden Knowledge:** Real-time audio processing, keyboard input simulation

### **LanguageResolver**
**Question:** Which transcription result (Hebrew/English/auto) is most accurate for ambiguous speech?
- **Inputs:** Dual-language transcription results from Transcriber
- **Outputs:** Single best transcription with resolved language tag
- **Forbidden Knowledge:** Audio capture mechanics, file storage details

### **Filter**
**Question:** Is this transcription legitimate text or junk that should be rejected?
- **Inputs:** Resolved transcriptions from LanguageResolver
- **Outputs:** Boolean pass/fail decision + clean text if passed
- **Forbidden Knowledge:** Audio data, network communication, or typing mechanisms

### **Typer**
**Question:** How do we reliably deliver valid transcriptions to the focused application?
- **Inputs:** Clean filtered text from Filter
- **Outputs:** Simulated keystrokes via SendInput + Enter key events
- **Forbidden Knowledge:** Audio processing, transcription algorithms, or storage internals

### **HealthMonitor**
**Question:** Is the entire pipeline functioning correctly end-to-end?
- **Inputs:** Component status reports, typing confirmation events
- **Outputs:** Health status logs + system-wide operational decisions
- **Forbidden Knowledge:** Low-level implementation details of other components

### **Journal**
**Question:** What happened when, and how can we reconstruct or audit the system's behavior?
- **Inputs:** Events from all components
- **Outputs:** Append-only JSONL log files
- **Forbidden Knowledge:** Direct control over hardware or user interfaces

---

## 2. THREADS

### **Main Thread**
- **Owns:** Health monitoring, configuration loading, graceful shutdown coordination
- **Death Impact:** System terminates - requires restart by user

### **Audio Capture Thread**
- **Owns:** Continuous microphone access, sample buffering
- **Death Impact:** Recording stops immediately - triggers health alert but preserves existing buffers

### **Segmentation Thread**
- **Owns:** Audio analysis, silence detection, chunk creation
- **Death Impact:** No new segments created - existing ones proceed through pipeline

### **Transcription Thread Pool (2 threads)**
- **Owns:** Network requests to transcription servers, response handling
- **Death Impact:** Individual transcriptions fail - retried automatically; others continue

### **Typing Thread**
- **Owns:** Window focus verification, SendInput operations, idle time tracking
- **Death Impact:** No typing occurs - transcriptions accumulate safely in buffer

### **Background Cleanup Thread**
- **Owns:** Journal rotation, old file deletion, disk space management
- **Death Impact:** Disk usage grows unchecked - no functional impact on core operation

**Recovery Policy:** Any non-main thread death causes immediate health failure notification. Main thread death requires manual restart.

---

## 3. THE SEGMENTER

The segmenter uses a dual-threshold voice activity detection approach:

### **Parameters:**

#### Calibrated Thresholds (based on Iddo's measured speech patterns):
- **Speech Start Threshold:** RMS > 0.030  
  *(Measured from 50 typical utterances: minimum sustained level)*
- **Speech End Threshold:** RMS < 0.025 for 400ms continuously  
  *(Based on natural pause duration distribution)*

#### Guessed/Fallback Thresholds:
- **Maximum Segment Duration:** 8 seconds  
  *(UNCALIBRATED - prevents infinite growth during sustained noise)*
- **Minimum Segment Duration:** 300ms  
  *(UNCALIBRATED - filters key clicks and breaths)*
- **Post-Segment Silence:** 800ms additional silence required after end detection  
  *(Prevents immediate restart on overlapping speech)*

### **Algorithm:**
1. Maintain rolling 100ms RMS window
2. Track state: SILENT → SPEECH_IN_PROGRESS → ENDING → SILENT
3. In ENDING state, require continuous sub-threshold for full timeout period
4. Apply hysteresis: return to SPEECH_IN_PROGRESS if threshold re-crossed during ending phase
5. Force segment closure at maximum duration limit

This design prevents fragmentation while maintaining responsiveness to genuine silences.

---

## 4. FAILURE TABLE

| Failure Mode | User Sees | Journal Records | Recovery |
|--------------|-----------|-----------------|----------|
| **No USB Mic Present** | Red LED indicator, no recording icon | "MICROPHONE_UNAVAILABLE" event with error details | Auto-retry every 30s until detected |
| **Transcription Server Down** | Orange warning icon, continued recording | "TRANSCRIPTION_SERVER_ERROR" with HTTP status codes | Fallback between localhost/remote servers, queue buildup acceptable |
| **Window Focus Lost** | Yellow indicator, no typing attempts | "FOCUS_LOST" event with target window info | Resume typing when focus returns within session timeout |
| **Junk Decode Detected** | Green recording continues, no visible output | "FILTER_REJECT" event with rejected text pattern | Normal pipeline continuation with next segment |
| **Any Worker Thread Dies** | Red system failure alert | "THREAD_CRASH" with stack trace | Immediate shutdown - requires manual restart |
| **Machine Reboot** | Cold start, previous session summary shown | Graceful shutdown recorded, followed by startup event | Resume normal operation, replay any unsent transcriptions |

---

## 5. TEST PLAN

### Core Constraint Enforcement Tests:
1. **Test_USBOnlyMicRequired** – Verify Bluetooth devices ignored when USB mic absent
2. **Test_NoAudioPlaybackEver** – Confirm zero sound output APIs called anywhere
3. **Test_HttpOnlyTranscription** – Ensure no local model/torch dependencies exist
4. **Test_PersistentAudioStorage** – Validate all segments written to disk pre-decode
5. **Test_SendInputOnlyTyping** – Check Win32 SendInput used exclusively for typing
6. **Test_HebrewForcedFallback** – Demonstrate dual-pass decoding for ambiguous Hebrew
7. **Test_JunkFilterBlocksGarbage** – Show rejection of known hallucination patterns
8. **Test_AppendOnlyJsonLogging** – Verify strict sequential JSONL event writing
9. **Test_SounddeviceOnlyDependency** – Confirm no external audio libraries imported
10. **Test_NoBashDependencies** – Ensure pure Python execution without shell scripts

### Functional Behavior Tests:
11. **Test_SegmentContinuityUnderPauseVariation** – Validate natural pauses don't fragment sentences
12. **Test_ThreadCrashKillsSystem** – Confirm any component crash leads to immediate termination
13. **Test_IdleTimeoutBehavior** – Check correct typing suppression based on user idle times
14. **Test_ServerFailoverHandling** – Demonstrate transparent switching between transcription servers
15. **Test_EndToEndLatencyBudget** – Measure total path: capture→decode→type under 1 second

Each test directly maps to a constraint violation scenario observed in past failures.

---

## 6. BUILD ORDER

### Phase 1: Foundation & Logging
1. `journal.py` – Implement append-only JSONL logging backbone
2. `config.py` – Load static settings (mic ID, server URLs, thresholds)
3. `health_monitor.py` – Basic lifecycle monitoring framework

### Phase 2: Audio Pipeline Core
4. `audio_capture.py` – USB microphone access with sounddevice
5. `segmenter.py` – Voice activity detection with calibrated thresholds
6. `disk_buffer.py` – Persistent WAV storage with cleanup policies

### Phase 3: Intelligence Layer
7. `transcriber.py` – HTTP client for dual-server transcription API
8. `language_resolver.py` – Confidence-based Hebrew/English selection logic
9. `filter.py` – Pattern matching against known junk phrases/repetitions

### Phase 4: Output & Integration
10. `typer.py` – Win32 SendInput integration with idle timeouts
11. `main.py` – Thread orchestration, graceful shutdown, health reporting

### Phase 5: Validation
12. All unit/integration tests listed above

Start with **`journal.py`** as it provides the observability foundation needed to validate every subsequent component.