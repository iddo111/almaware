from dataclasses import dataclass
from typing import Optional


@dataclass
class Segment:
    start_ms: int
    end_ms: int


class Segmenter:
    """
    Detects voiced speech segments from an incoming stream of audio frame rms values.

    The detection logic follows these rules:
    1. Silence MUST NEVER start a new segment.
    2. Segments start when the RMS exceeds a `gate` threshold.
    3. Segments end naturally after a fixed duration (`max_ms`) if not already ended.
    4. Segments end abruptly when silence is detected for a duration (`silence_ms`).
    5. Final segments shorter than `min_ms` are discarded to prevent noise pockets.
    """

    def __init__(
        self,
        min_ms: int = 300,
        max_ms: int = 15000,
        silence_ms: int = 1000,
        gate: float = 0.02,
        vad_silence_ms: int = 0,
    ):
        self.min_ms = min_ms
        self.max_ms = max_ms
        self.silence_ms = silence_ms
        self.allowed_gate = gate
        # 2026-08-31: endpoint on VOICE, not loudness. Measured that morning: the room
        # sits at RMS ~1187 against a gate of 300, so RMS-silence never fires -- every
        # segment ran to the max_ms cap and the mic decoded the fan all day ("תודה"
        # flood, one request every ~4 s, 1196 of them). Loudness cannot solve this room
        # (the 08-28 note above the gate proved a high floor blocks his real speech).
        # So: a frame that carries no VOICE (webrtcvad) counts toward its own, longer
        # silence window. Longer, because his far-field speech scores only ~0.3 voiced
        # ratio -- short unvoiced runs happen INSIDE his sentences, and an in-sentence
        # pause is 200-400 ms. 0 disables (old behaviour exactly).
        self.vad_silence_ms = vad_silence_ms
        self.sensitivity = None  # Optional object with .gate attribute

        # Internal state
        self._state = "IDLE"  # IDLE, SPEAKING, SILENCE
        self._last_rms = 0.0
        self._speech_start_time = None
        self._silence_start_time = None
        self._unvoiced_start_time = None
        self._clock = 0

    def _read_gate(self) -> float:
        """Reads the dynamic gate from sensitivity or returns fixed gate."""
        if self.sensitivity is not None and hasattr(self.sensitivity, "gate"):
            return self.sensitivity.gate
        return self.allowed_gate

    def feed(self, frame_ms: int, rms: float, voiced: bool = True) -> Optional[Segment]:
        """
        Processes one frame and potentially closes a segment.

        :param frame_ms: The duration of the current audio frame in milliseconds.
        :param rms: The Root Mean Square energy of the current frame.
        :param voiced: webrtcvad's verdict on this frame. Callers that do not
                       compute VAD pass nothing and get the old behaviour exactly.
        :return: A Segment object if a speech chunk was closed and is valid,
                 otherwise None.
        """
        gate = self._read_gate()
        vad_on = self.vad_silence_ms > 0
        self._clock += frame_ms

        # State Machine
        if self._state == "IDLE":
            # A loud UNVOICED frame is the fan, not him: with the gate at 300 and the
            # room at ~1187, loudness alone opened a segment every time. Voice opens.
            if rms >= gate and (voiced or not vad_on):
                # Start of speech
                self._state = "SPEAKING"
                self._speech_start_time = self._clock - frame_ms  # Capture start ms
                self._last_rms = rms
                self._unvoiced_start_time = None
                return None

        elif self._state == "SPEAKING":
            self._last_rms = rms

            # Rule 1: Silence MUST NEVER OPEN A SEGMENT.
            # We only transition to silence if we were already speaking.
            if rms < gate:
                if self._silence_start_time is None:
                    self._silence_start_time = self._clock
                # Check if silence duration is sufficient to end segment
                if (self._clock - self._silence_start_time) >= self.silence_ms:
                    self._state = "IDLE"
                    self._silence_start_time = None
                    self._unvoiced_start_time = None
                    return self._create_segment()
            else:
                self._silence_start_time = None

            # The VOICE endpoint: loud-but-unvoiced frames (the room) close the
            # segment too, on their own longer window -- so a sentence ends ~when he
            # stops speaking instead of at the max_ms cap, and the decoder gets his
            # words cut at a real boundary instead of mid-syllable at second five.
            if vad_on:
                if not voiced:
                    if self._unvoiced_start_time is None:
                        self._unvoiced_start_time = self._clock
                    if (self._clock - self._unvoiced_start_time) >= self.vad_silence_ms:
                        self._state = "IDLE"
                        self._silence_start_time = None
                        self._unvoiced_start_time = None
                        return self._create_segment()
                else:
                    self._unvoiced_start_time = None

            # Rule 4: Max duration check
            if self._clock - self._speech_start_time >= self.max_ms:
                self._state = "IDLE"
                self._unvoiced_start_time = None
                return self._create_segment()

        elif self._state == "SILENCE":
            # If we enter this state (e.g. from previous iteration), simply check if speech starts later
            if rms >= gate:
                self._state = "SPEAKING"
                self._speech_start_time = self._clock - frame_ms
                self._silence_start_time = None
                return None
            else:
                # Stay in silence, waiting for speech
                return None

        return None

    def _create_segment(self) -> Optional[Segment]:
        """Helper to create a Segment and validate it against min_ms."""
        # The start time was captured in the SPEAKING branch
        end_ms = self._clock
        
        # Calculate duration
        duration_ms = end_ms - self._speech_start_time
        
        # Rule 5: Discard if shorter than min_ms
        if duration_ms < self.min_ms:
            return None
            
        return Segment(start_ms=self._speech_start_time, end_ms=end_ms)
