```python
# FILE: a70_relay.py
import argparse
import socket
import struct
import sys
import time

import numpy as np
import sounddevice as sd


def list_devices():
    print("Available audio devices:")
    print(sd.query_devices())
    return 0


def find_loopback_device():
    devices = sd.query_devices()
    for i, dev in enumerate(devices):
        if 'loopback' in dev['name'].lower() or (dev['max_input_channels'] > 0 and 'output' in dev['name'].lower()):
            return i
    raise RuntimeError("No loopback device found")


def main():
    parser = argparse.ArgumentParser(description="A70 Audio Relay - PC side")
    parser.add_argument('--host', required=True, help='Target host IP')
    parser.add_argument('--port', type=int, default=5005, help='Target port (default: 5005)')
    parser.add_argument('--list-devices', action='store_true', help='List audio devices and exit')

    args = parser.parse_args()

    if args.list_devices:
        return list_devices()

    HOST = args.host
    PORT = args.port
    SAMPLE_RATE = 44100
    CHANNELS = 2
    BLOCKSIZE = 512
    DTYPE = np.int16

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    seq_num = 0

    def callback(indata, frames, time_info, status):
        nonlocal seq_num
        if status:
            print(status, file=sys.stderr)

        # Flatten and convert to bytes
        data = indata.astype(DTYPE).tobytes()

        header = struct.pack('<II', seq_num, len(data) // (2 * CHANNELS))
        packet = header + data

        try:
            sock.sendto(packet, (HOST, PORT))
        except Exception as e:
            print(f"Send error: {e}", file=sys.stderr)

        seq_num += 1

    device_idx = find_loopback_device()
    print(f"Using loopback device index: {device_idx}")

    with sd.InputStream(
        device=device_idx,
        channels=CHANNELS,
        samplerate=SAMPLE_RATE,
        blocksize=BLOCKSIZE,
        dtype=np.float32,
        callback=callback
    ):
        print("Streaming... Press Ctrl+C to stop.")
        try:
            while True:
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("\nStopping stream.")

    sock.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
```

```python
# FILE: a70_receive.py
import argparse
import socket
import struct
import sys
import time
from collections import defaultdict


def main():
    parser = argparse.ArgumentParser(description="A70 Audio Receiver - Android/Termux side")
    parser.add_argument('--port', type=int, default=5005, help='UDP port to listen on (default: 5005)')
    args = parser.parse_args()

    PORT = args.port
    SAMPLES_PER_PACKET = 512
    BYTES_PER_SAMPLE = 4  # int16 stereo = 2 * 2 bytes
    PACKET_INTERVAL_SEC = SAMPLES_PER_PACKET / 44100.0  # ~11.6ms

    # Jitter buffer: store packets by sequence number
    jitter_buffer_ms = 60
    jitter_buffer_size = int(jitter_buffer_ms / (PACKET_INTERVAL_SEC * 1000)) + 1  # in packets

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('', PORT))
    sock.settimeout(0.5)

    buffer = {}
    expected_seq = 0
    last_play_time = 0

    print(f"Listening on UDP port {PORT}, jitter buffer: {jitter_buffer_ms}ms", file=sys.stderr)

    while True:
        try:
            data, addr = sock.recvfrom(65536)
        except socket.timeout:
            continue

        if len(data) < 8:
            continue

        seq_num, sample_count = struct.unpack('<II', data[:8])
        payload = data[8:]

        # Store in buffer
        buffer[seq_num] = payload

        # Try to play out packets when buffer is full enough
        while expected_seq in buffer or (len(buffer) >= jitter_buffer_size):
            if expected_seq in buffer:
                payload = buffer.pop(expected_seq)
                sys.stdout.buffer.write(payload)
                sys.stdout.flush()
                expected_seq += 1
            else:
                # Missing packet: fill with silence
                missing_bytes = SAMPLES_PER_PACKET * BYTES_PER_SAMPLE
                sys.stdout.buffer.write(b'\x00' * missing_bytes)
                sys.stdout.flush()
                expected_seq += 1


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
```

```python
# FILE: a70_latency.py
import argparse
import wave
import numpy as np
from scipy.signal import find_peaks


def generate_click_track(filename, sample_rate=44100, duration_sec=10, click_interval_sec=1.0):
    total_samples = int(sample_rate * duration_sec)
    audio_data = np.zeros(total_samples, dtype=np.int16)

    click_samples = int(sample_rate * 0.001)  # 1ms click
    click_value = 32767

    for i in range(int(duration_sec / click_interval_sec)):
        idx = int(i * sample_rate * click_interval_sec)
        if idx + click_samples < total_samples:
            audio_data[idx:idx+click_samples] = click_value

    with wave.open(filename, 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio_data.tobytes())

    print(f"Generated click track: {filename}")


def measure_latency(click_file, recorded_file):
    with wave.open(click_file, 'r') as wf:
        click_sr = wf.getframerate()
        click_data = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)

    with wave.open(recorded_file, 'r') as wf:
        rec_sr = wf.getframerate()
        rec_data = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)

    if click_sr != rec_sr:
        raise ValueError("Sample rates must match")

    # Normalize
    click_data = click_data.astype(np.float32)
    rec_data = rec_data.astype(np.float32)
    if np.max(np.abs(click_data)) > 0:
        click_data /= np.max(np.abs(click_data))
    if np.max(np.abs(rec_data)) > 0:
        rec_data /= np.max(np.abs(rec_data))

    # Cross-correlation
    correlation = np.correlate(rec_data, click_data, mode='full')
    lags = np.arange(-len(click_data) + 1, len(rec_data))
    lag_max = lags[np.argmax(correlation)]

    latency_samples = -lag_max
    latency_ms = (latency_samples / rec_sr) * 1000

    print(f"Latency: {latency_samples} samples ({latency_ms:.2f} ms)")
    return latency_ms


def main():
    parser = argparse.ArgumentParser(description="A70 Latency Measurement Tool")
    subparsers = parser.add_subparsers(dest='command')

    gen_parser = subparsers.add_parser('generate', help='Generate click track WAV')
    gen_parser.add_argument('--output', required=True, help='Output WAV file')
    gen_parser.add_argument('--duration', type=int, default=10, help='Duration in seconds')
    gen_parser.add_argument('--interval', type=float, default=1.0, help='Click interval in seconds')

    measure_parser = subparsers.add_parser('measure', help='Measure latency from recording')
    measure_parser.add_argument('--click', required=True, help='Original click track WAV')
    measure_parser.add_argument('--recorded', required=True, help='Recorded WAV file')

    args = parser.parse_args()

    if args.command == 'generate':
        generate_click_track(args.output, duration_sec=args.duration, click_interval_sec=args.interval)
    elif args.command == 'measure':
        measure_latency(args.click, args.recorded)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
```