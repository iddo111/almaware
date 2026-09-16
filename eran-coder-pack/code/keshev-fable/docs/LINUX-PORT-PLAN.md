# LINUX-PORT-PLAN.md

## 1. Audio Capture: `sounddevice` & ALSA Device Selection

The Windows version relies on WASAPI. On Linux, we must switch to `sounddevice` (wrapping PortAudio) or raw ALSA. Crucially, the "USB-only law" (device appears only when plugged in) requires a dynamic device list refresh before every capture session.

**The Problem:** `sounddevice.default.device` might return a default HDMI or internal mic, ignoring the user's specific USB headset. We need a function to query PortAudio and filter for `HostApiSpecificStreamInfo` matching a USB device.

**The Solution:**
```python
import sounddevice as sd
import soundfile as sf
import numpy as np
import re

def get_usb_device_index():
    """
    Scans PortAudio devices to find a USB microphone.
    Returns the device index or None.
    """
    # Filter for USB devices (HostApiSpecificStreamInfo)
    # Note: The 'hostapi' index 4 is typically ALSA on most systems
    usb_devices = [d for d in sd.query_devices() 
                   if d['hostapi'] == 4 and 'USB' in d['name']]

    if not usb_devices:
        return None

    # Prefer the first available USB device
    return usb_devices[0]['index']

def capture_audio(filename, device_index=None):
    if device_index is None:
        device_index = get_usb_device_index()
        if device_index is None:
            raise RuntimeError("No USB audio device found.")

    # Configure the stream
    # 16kHz, Mono, 16-bit PCM (standard for speech)
    samplerate = 16000
    channels = 1
    dtype = np.int16

    print(f"Capturing audio from device {device_index}...")
    
    # Capture for 3 seconds (example)
    # In the real app, this would be a continuous stream
    recording = sd.rec(int(samplerate * 3), samplerate=samplerate, 
                       channels=channels, dtype=dtype, 
                       device=device_index)
    sd.wait() # Wait until recording is finished
    sf.write(filename, recording, samplerate)
```

## 2. Typing Backend: `xdotool` vs `wtype` vs `uinput`

The Windows version uses `SendInput`. On Linux, we have three viable backends, each with different stability and Wayland support.

1.  **`xdotool` (X11):** The most robust for X11. It simulates keystrokes at the X11 level. It is the default fallback.
2.  **`wtype` (Wayland):** A native Wayland client. It is faster and more secure but requires the app to run under a Wayland session.
3.  **`uinput` (Kernel):** The most direct method. We write to `/dev/uinput`. This bypasses any display server but is complex to implement correctly (handling dead keys, modifiers, and Hebrew layout).

**Detection Order & Fallbacks:**
1.  Check for `wtype` (Wayland).
2.  Check for `xdotool` (X11).
3.  Fallback to `uinput` (if we implement it).

**Code Snippet:**
```python
import subprocess
import os

def get_typing_backend():
    # 1. Check for Wayland (wtype)
    if os.environ.get('WAYLAND_DISPLAY'):
        try:
            subprocess.run(['wtype', '--version'], check=True, capture_output=True)
            return 'wtype'
        except FileNotFoundError:
            pass # wtype not installed, fall through

    # 2. Check for X11 (xdotool)
    if os.environ.get('DISPLAY'):
        try:
            subprocess.run(['xdotool', '--version'], check=True, capture_output=True)
            return 'xdotool'
        except FileNotFoundError:
            pass # xdotool not installed, fall through

    # 3. Fallback to uinput (if implemented)
    # For this plan, we assume uinput is implemented as a last resort
    return 'uinput'

def type_text(text):
    backend = get_typing_backend()
    print(f"Using backend: {backend}")

    if backend == 'wtype':
        # wtype handles UTF-8 natively
        subprocess.run(['wtype', text], check=True)
    elif backend == 'xdotool':
        # xdotool requires key sequences, not raw text
        # We must map each character to its key name
        for char in text:
            # Simple mapping for ASCII, complex for Hebrew
            # Ideally, use a library like 'xkeysym' or 'pyxdotool'
            subprocess.run(['xdotool', 'type', char], check=True)
    elif backend == 'uinput':
        # Write to /dev/uinput
        # This requires a complex C-extension or a library like 'pyinput'
        pass
```

**Hebrew Caveats:** When using `xdotool`, typing Hebrew characters requires knowing the X11 key symbol names (e.g., `hebrew_lamed`, `hebrew_aleph`). A simple `xdotool type "שלום"` will likely type "slm" or fail depending on the active keyboard layout. The application must ensure the target window has the correct Hebrew layout active or map characters to their specific X11 keycodes.

## 3. Presence/Idle Detection

The Windows version uses `GetLastInputInfo`. On Linux, we need to query the system's idle state.

1.  **`xprintidle` (X11):** A command-line tool that returns the milliseconds since the last user input. It is the most common method for X11.
2.  **`logind` (Systemd):** A more robust method that queries the `org.freedesktop.login1` D-Bus interface. It provides an `IdleHint` property.
3.  **Wayland Idle Protocols:** Wayland has native protocols (`org.freedesktop.portal.Idle`) that applications can query.

**Code Snippet:**
```python
import subprocess
import dbus

def is_idle():
    # 1. Try logind (Systemd) - Most robust
    bus = dbus.SystemBus()
    manager = bus.get_object('org.freedesktop.login1', '/org/freedesktop/login1')
    manager = dbus.Interface(manager, 'org.freedesktop.login1.Manager')

    try:
        idle_hint = manager.GetProperty('org.freedesktop.login1.Manager').get('IdleHint')
        return idle_hint
    except dbus.exceptions.DBusException:
        pass

    # 2. Try xprintidle (X11)
    if os.environ.get('DISPLAY'):
        try:
            output = subprocess.check_output(['xprintidle']).decode('utf-8')
            idle_time = int(output.strip())
            # If idle for more than 10 seconds, consider idle
            return idle_time > 10000
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass

    # 3. Fallback: Assume not idle
    return False
```

## 4. Single-Instance: `flock` on `/run/user/<uid>/keshev.lock`

To prevent multiple instances of the dictation app from running simultaneously (which would cause audio capture conflicts), we use `flock`.

**The Solution:**
We open the lock file with `O_CREAT | O_RDWR` and the `fcntl.flock` lock type `LOCK_EX`. We also set `O_CLOEXEC` to ensure the file descriptor is closed automatically when we fork/exec a new process (e.g., when starting the STT server).

**Code Snippet:**
```python
import os
import fcntl

def acquire_single_instance_lock():
    # Get the user's runtime directory
    runtime_dir = os.environ.get('XDG_RUNTIME_DIR', '/tmp')
    lock_file_path = os.path.join(runtime_dir, 'keshev.lock')

    # Open the lock file
    fd = os.open(lock_file_path, os.O_CREAT | os.O_RDWR | os.O_CLOEXEC)

    try:
        # Acquire an exclusive lock
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

        # If we get here, we have the lock
        print("Single instance lock acquired.")
        return fd
    except BlockingIOError:
        # Lock was not acquired
        print("Another instance is already running.")
        os.close(fd)
        exit(1)
```

## 5. Autostart: Systemd User Unit

To make the app start automatically on login, we create a systemd user unit file.

**The Unit File:**
Save this as `~/.config/systemd/user/keshev.service`.

```ini
[Unit]
Description=Keshev Fable Dictation
After=sound.target

[Service]
Type=simple
ExecStart=/usr/local/bin/python3 /opt/keshev-fable/main.py
Restart=on-failure
RestartSec=5

# Environment variables for the app
Environment="DISPLAY=:0"
Environment="WAYLAND_DISPLAY=wayland-0"

# Ensure the app has access to audio devices
# (Optional, depending on user permissions)
# AmbientCapabilities=CAP_SYS_RAWIO

[Install]
WantedBy=default.target
```

To enable and start the service:
```bash
systemctl --user daemon-reload
systemctl --user enable keshev.service
systemctl --user start keshev.service
```

## 6. What Needs NO Change (Pure Modules)

The following core modules of the Keshev Fable architecture are platform-agnostic and require **no modification**:

1.  **`segmenter.py`**: The logic that splits raw audio into chunks (e.g., 3-second windows) is purely mathematical and independent of the OS.
2.  **`spool.py`**: The file I/O logic for buffering audio chunks to disk (e.g., writing to `/tmp/keshev_spool/`) is standard POSIX file I/O and works identically on Linux.
3.  **`gates.py`**: The logic that checks for idle time and microphone permission is abstracted. While the *implementation* of the idle check changes (see section 3), the *interface* (a function returning a boolean) remains the same.
4.  **`journal.py`**: The JSONL logging module uses standard Python `json` and `open()`. The format and data structure are unchanged.
5.  **`kernel_mutex`**: The logic for managing internal state (e.g., preventing concurrent typing events) is a Python `threading.Lock` or `multiprocessing.Lock`, which is fully supported on Linux.
6.  **`typer` (Windows-specific `SendInput`)**: This is the only component that is fundamentally tied to the Windows API. It must be replaced with the Linux backends described in Section 2.