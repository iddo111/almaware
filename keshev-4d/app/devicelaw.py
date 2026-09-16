# app/devicelaw.py
import sys
import os

# Hard Law: Module location
APP_DIR = r"D:\CLAUDE\keshev-4d"
sys.path.insert(0, APP_DIR)

# Hard Law: Internal Journaling
class Journal:
    def __init__(self):
        self.events = []
    
    def event(self, event_id, **kwargs):
        self.events.append((event_id, kwargs))

journal = Journal()

# Hard Law: Forbidden Devices
_NEVER_MIC = ("WH-1000", "Hands-Free", "Headset", "Bluetooth")

# Hard Law: Allowed Substrings
ALLOWED_SUBSTRINGS = ("BRIO", "Scarlett", "USBAudio")

def is_forbidden(name):
    """
    Reachability Test (a): Checks if a device name matches the forbidden tuple.
    Wiring Test (b): Called by choose_device to filter out bad hardware.
    """
    if not isinstance(name, str):
        return False
    
    name_lower = name.lower()
    for forbidden in _NEVER_MIC:
        if forbidden.lower() in name_lower:
            return True
    return False

def choose_device(device_names, allowed=ALLOWED_SUBSTRINGS):
    """
    Reachability Test (a): 
    1. 'BRIO' is in allowed and not forbidden -> returns 'BRIO'.
    2. 'Microphone (WH-1000XM4 Hands-Free AG Audio)' is forbidden -> returns None.
    3. Empty list -> returns None.
    
    Wiring Test (b): 
    1. Returns None -> calls journal.event(IDLE_NO_MIC).
    2. Returns valid name -> does NOT call journal.event.
    """
    if not isinstance(device_names, list):
        return None

    for name in device_names:
        # Hard Law: Non-string entries are skipped
        if not isinstance(name, str):
            continue

        # Hard Law: Case-insensitive substring matching
        name_lower = name.lower()
        allowed_lower = [a.lower() for a in allowed]
        
        # Check if name matches any allowed substring
        if not any(allowed_sub in name_lower for allowed_sub in allowed_lower):
            continue

        # Check if name is forbidden
        if is_forbidden(name):
            continue

        # Hard Law: Return ORIGINAL name with ORIGINAL casing
        return name

    # Hard Law: Nothing qualifies -> journal IDLE_NO_MIC
    journal.event("IDLE_NO_MIC")
    return None
