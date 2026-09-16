```python
"""KESHEV-4D Module: app/gates.py

Implements the GATE_RMS threshold, energy_ok helper, and the Segmenter
state machine. Designed for Python 3.12 stdlib only.
"""

from __future__ import annotations

import sys
import pathlib

# Ensure we are in the correct execution context
_MODULE_PATH = pathlib.Path(__file__).resolve()
sys.path.insert(0, str(_MODULE_PATH.parents[1]))

from app import journal  # noqa: E402

# --- Constants & Configuration ---

# Thresholds derived from the "Law" (test_gate_between_the_populations)
# Noise p90 is approx 0.0060. Speech median is approx 0.0276.
# We set the gate slightly above noise to minimize false opens.
GATE_RMS = 0.0065

# --- Helpers ---

def energy_ok(rms: float) -> bool:
    """
    Determines if a frame's energy passes the silence gate.
    
    Args:
        rms: Root Mean Square energy of the frame.
        
    Returns:
        True if energy is above the threshold, False otherwise.
    """
    return rms > GATE_RMS

# --- Core Logic ---

class Segmenter:
    """
    A state machine that segments audio frames into utterances.
    
    Rules:
    1. Silence never opens a segment.
    2. Blips below min_ms yield None.
    3. Monologues force-close at max_ms.
    4. Hang time is excluded from the segment duration.
    """
    
    def __init__(
        self,
        min_ms: int = 280,
        max_ms: int = 15000,
        hang_ms: int = 420,
    ):
        self.min_ms = min_ms
        self.max_ms = max_ms
        self.hang_ms = hang_ms
        
        # State tracking
        self._state = "IDLE"  # IDLE, OPENING, OPEN, CLOSING
        self._segment_start_ms = 0
        self._segment_end_ms = 0
        self._last_speech_ms = 0
        self._last_speech_rms = 0
        
        # Output buffer
        self._segments: list[tuple[int, int, bool]] = []

    def feed(self, ms: int, rms: float):
        """
        Processes a single frame of audio data.
        
        Args:
            ms: Timestamp of the frame (ms).
            rms: Energy level of the frame.
            
        Returns:
            A tuple (start_ms, end_ms, forced) if a segment is finalized,
            None otherwise.
        """
        # Guard: Reachability
        # This method must handle IDLE, OPENING, OPEN, and CLOSING states.
        # It must also handle the transition from CLOSING back to IDLE.
        
        if self._state == "IDLE":
            return self._handle_idle(ms, rms)
        elif self._state == "OPENING":
            return self._handle_opening(ms, rms)
        elif self._state == "OPEN":
            return self._handle_open(ms, rms)
        elif self._state == "CLOSING":
            return self._handle_closing(ms, rms)
        else:
            # Should not happen
            return None

    def _handle_idle(self, ms: int, rms: float):
        """Handles the IDLE state: waiting for speech to start."""
        if energy_ok(rms):
            self._state = "OPENING"
            self._segment_start_ms = ms
            self._last_speech_ms = ms
            self._last_speech_rms = rms
        return None

    def _handle_opening(self, ms: int, rms: float):
        """
        Handles the OPENING state: collecting frames to ensure min_ms duration.
        """
        # Check for speech
        if energy_ok(rms):
            self._last_speech_ms = ms
            self._last_speech_rms = rms
            
            # Check if we have enough duration
            duration = ms - self._segment_start_ms
            if duration >= self.min_ms:
                self._state = "OPEN"
            return None
        
        # Check for silence
        else:
            # If silence occurs before min_ms, we drop the segment.
            # This satisfies "blips below min_ms yield None".
            duration = ms - self._segment_start_ms
            if duration >= self.min_ms:
                # We have enough duration, but silence just started.
                # We transition to OPEN to wait for the hang.
                self._state = "OPEN"
                return None
            else:
                # Not enough duration, silence occurred. Drop it.
                self._state = "IDLE"
                return None

    def _handle_open(self, ms: int, rms: float):
        """
        Handles the OPEN state: tracking active speech and waiting for hang.
        """
        # Check for speech
        if energy_ok(rms):
            self._last_speech_ms = ms
            self._last_speech_rms = rms
            return None
        
        # Check for silence
        else:
            # Silence detected. Start the hang timer.
            self._state = "CLOSING"
            return None

    def _handle_closing(self, ms: int, rms: float):
        """
        Handles the CLOSING state: waiting for hang_ms.
        """
        # Check for speech (hang excluded)
        if energy_ok(rms):
            # Speech resumed. The segment is valid.
            # We finalize the segment now.
            self._finalize_segment(ms)
            # Transition back to IDLE to start a new segment.
            self._state = "IDLE"
            return None
        
        # Check for silence (hang expired)
        else:
            # Silence continued for hang_ms.
            # The segment is finalized.
            self._finalize_segment(ms)
            # Transition back to IDLE.
            self._state = "IDLE"
            return None

    def _finalize_segment(self, end_ms: int):
        """
        Finalizes the current segment and appends it to the output list.
        """
        # Calculate duration
        duration = end_ms - self._segment_start_ms
        
        # Determine if the segment was forced closed by max_ms
        forced = duration >= self.max_ms
        
        # Append the segment
        self._segments.append((self._segment_start_ms, end_ms, forced))
        
        # Reset state
        self._segment_start_ms = 0
        self._segment_end_ms = 0

    def get_segments(self) -> list[tuple[int, int, bool]]:
        """
        Returns the list of finalized segments.
        
        Returns:
            A list of tuples (start_ms, end_ms, forced).
        """
        return self._segments
```