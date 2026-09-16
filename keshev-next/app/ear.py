import sys
import numpy as np
import sounddevice as sd
from scipy.signal import decimate

# Configuration constants
RATE_IN = 48000
RATE_OUT = 16000
DECIMATION_FACTOR = 3
CHUNK_SIZE_SAMPLES = 1024  # Output block size
DTYPE_OUT = np.int16

class EarProcessor:
    """
    Captures audio at 48kHz, decimates to 16kHz, and hands
    fixed-size int16 blocks to a callback.
    """

    def __init__(self, block_callback):
        """
        Initialize the processor.
        
        :param block_callback: Function taking (numpy array of int16, rms: float).
        """
        self.callback = block_callback
        # Allocate buffer to hold leftover samples between chunks
        self._buffer = np.array([], dtype=np.int32)
        # We process in 48kHz samples, but target 16kHz output
        self._block_size_out = CHUNK_SIZE_SAMPLES

    def _process(self, indata: np.ndarray) -> None:
        """
        Core processing logic: decimate, convert, buffer, and chunk.
        This method is pure logic and easily unit-testable.
        """
        # 1. Decimate (Low-pass filter + downsample 48k -> 16k)
        # Note: scipy.decimate assumes a 1D array and filters along that axis.
        # We use int32 for calculation to avoid overflow before casting to int16.
        try:
            # Ensure input is int32 for safe decimation math
            if indata.dtype != np.int32:
                indata = indata.astype(np.int32)
            
            # Apply decimation filter. axis=0 handles column vectors (mono)
            decimated = decimate(indata[:, 0], DECIMATION_FACTOR, zero_phase=True)
            
            # 2. Normalize and convert to target int16
            # Decimation reduces amplitude roughly by the factor, but we want full range
            # We scale to utilize the full int16 dynamic range (-32768 to 32767)
            # Simple scaling: shift bit-depth (int32 -> int16) with clamping.
            # To keep loudness consistent, we usually scale up by the decimation factor
            # or normalize. For simplicity and robustness in noise:
            decimated = np.clip(decimated, -32768, 32767).astype(DTYPE_OUT)
            
            # 3. Handle chunking with leftover buffering
            # Append new data to the residual buffer
            self._buffer = np.concatenate((self._buffer, decimated))
            
            # While we have enough data for a full block
            while len(self._buffer) >= self._block_size_out:
                # Extract a fixed-size block
                block = self._buffer[:self._block_size_out]
                # Keep remaining samples
                self._buffer = self._buffer[self._block_size_out:]
                
                # 4. Calculate RMS and invoke callback
                # RMS = sqrt(mean(x^2))
                rms = np.sqrt(np.mean(block.astype(np.float64) ** 2))
                self.callback(block, rms)

        except Exception as e:
            print(f"Processing error: {e}", file=sys.stderr)

    def feed(self, raw_bytes: bytes) -> None:
        """
        Feed raw bytes (48kHz, mono, int16) into the processor.
        This method allows testing without sounddevice.
        
        :param raw_bytes: Raw audio bytes (little-endian).
        """
        # Convert bytes to numpy array
        if len(raw_bytes) % 2 != 0:
            raise ValueError("Raw audio bytes length must be even (int16).")
            
        arr = np.frombuffer(raw_bytes, dtype=np.int16)
        # Reshape to (n_samples, 1) to match stream callback format
        arr = arr.reshape(-1, 1)
        self._process(arr)

    def start(self) -> None:
        """Start audio capture using sounddevice."""
        try:
            with sd.InputStream(
                samplerate=RATE_IN,
                channels=1,
                dtype='int16',
                blocksize=CHUNK_SIZE_SAMPLES * DECIMATION_FACTOR,
                callback=self._sd_callback
            ):
                print(f"Listening at {RATE_IN}Hz... (Press Ctrl+C to stop)")
                sd.sleep(10**6)  # Long sleep; Ctrl+C to break
        except sd.SoundDeviceError as e:
            print(f"SoundDevice error: {e}", file=sys.stderr)

    def _sd_callback(self, indata, frames, time, status):
        """Callback expected by sounddevice.InputStream."""
        if status:
            print(status, file=sys.stderr)
        self._process(indata)


# Example usage block (only runs if executed directly)
if __name__ == "__main__":
    def my_output(block: np.ndarray, rms: float):
        print(f"Block RMS: {rms:.2f}")

    # Create processor instance
    processor = EarProcessor(my_output)

    # If running interactively, we could call processor.start()
    # But for demonstration, we'll simulate a feed:
    import math
    # Generate 100ms of 1kHz sine wave at 48kHz
    duration_s = 0.1
    t = np.arange(0, duration_s * RATE_IN) / RATE_IN
    sine_48k = np.sin(2 * np.pi * 1000 * t)
    # Scale to int16
    sine_48k_int16 = (sine_48k * 30000).astype(np.int16)
    raw_bytes = sine_48k_int16.tobytes()
    
    # Feed it
    processor.feed(raw_bytes)
    
    # Expected: ~30000 * 0.707 ~ 21213 RMS (after decimation, gain stays similar)
    # Decimation preserves amplitude if scaled, but we clamped in _process.
    # Without explicit normalization in decimate, amplitude ~30000*0.707.
