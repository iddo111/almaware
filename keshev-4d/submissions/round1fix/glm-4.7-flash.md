```python
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
```

```python
# tests/test_devicelaw.py
import unittest
import sys
import os

# Hard Law: Module location
APP_DIR = r"D:\CLAUDE\keshev-4d"
sys.path.insert(0, APP_DIR)

from app.devicelaw import choose_device, is_forbidden, journal

class TestDeviceLaw(unittest.TestCase):
    def setUp(self):
        self.journal_backup = journal.events
        journal.events = []

    def tearDown(self):
        journal.events = self.journal_backup

    def test_choose_device_keeps_original_casing(self):
        """
        Wiring Test (b): Verifies the public API returns the original casing.
        """
        devices = ["brio", "Brio", "BRIo", "BRIO"]
        result = choose_device(devices)
        # The first match is 'brio'. It must be returned exactly as is.
        self.assertEqual(result, "brio")

    def test_choose_device_refuses_forbidden_device(self):
        """
        Reachability Test (a): 'Microphone (WH-1000XM4 Hands-Free AG Audio)' is forbidden.
        """
        devices = ["Microphone (WH-1000XM4 Hands-Free AG Audio)"]
        result = choose_device(devices)
        self.assertIsNone(result)
        self.assertEqual(journal.events, [("IDLE_NO_MIC", {})])

    def test_choose_device_empty_list(self):
        """
        Reachability Test (a): Empty list returns None.
        """
        devices = []
        result = choose_device(devices)
        self.assertIsNone(result)
        self.assertEqual(journal.events, [("IDLE_NO_MIC", {})])

    def test_choose_device_non_string_entry(self):
        """
        Reachability Test (a): Non-string entries are skipped.
        """
        devices = ["Valid Device", 123, None, "Another Valid Device"]
        result = choose_device(devices)
        # 'Valid Device' is not in allowed substrings, so it is skipped.
        # 'Another Valid Device' is not in allowed substrings, so it is skipped.
        # '123' and 'None' are skipped.
        self.assertIsNone(result)
        self.assertEqual(journal.events, [("IDLE_NO_MIC", {})])

    def test_choose_device_non_string_entry_with_match(self):
        """
        Wiring Test (b): Non-string entries are skipped, even if they look like strings.
        """
        devices = ["BRIO", 123, "Scarlett"]
        result = choose_device(devices)
        # 'BRIO' is the first valid match.
        self.assertEqual(result, "BRIO")
        self.assertEqual(journal.events, [])

    def test_choose_device_case_insensitive_matching(self):
        """
        Reachability Test (a): Case-insensitive substring matching works.
        """
        devices = ["brio", "Brio", "BRIo", "BRIO"]
        result = choose_device(devices)
        self.assertEqual(result, "brio")

    def test_choose_device_allowed_substrings(self):
        """
        Wiring Test (b): Verifies the public API respects the allowed parameter.
        """
        devices = ["BRIO", "Microphone (WH-1000XM4 Hands-Free AG Audio)", "Scarlett"]
        result = choose_device(devices)
        self.assertEqual(result, "BRIO")

    def test_is_forbidden(self):
        """
        Reachability Test (a): is_forbidden returns True for forbidden devices.
        """
        self.assertTrue(is_forbidden("WH-1000XM4"))
        self.assertTrue(is_forbidden("Hands-Free"))
        self.assertTrue(is_forbidden("Headset"))
        self.assertTrue(is_forbidden("Bluetooth"))

    def test_is_forbidden_false(self):
        """
        Reachability Test (a): is_forbidden returns False for allowed devices.
        """
        self.assertFalse(is_forbidden("BRIO"))
        self.assertFalse(is_forbidden("Scarlett"))
        self.assertFalse(is_forbidden("USBAudio"))
```

```python
# tests/test_devicelaw.py
import unittest
import sys
import os

# Hard Law: Module location
APP_DIR = r"D:\CLAUDE\keshev-4d"
sys.path.insert(0, APP_DIR)

from app.devicelaw import choose_device, is_forbidden, journal

class TestDeviceLaw(unittest.TestCase):
    def setUp(self):
        self.journal_backup = journal.events
        journal.events = []

    def tearDown(self):
        journal.events = self.journal_backup

    def test_choose_device_keeps_original_casing(self):
        """
        Wiring Test (b): Verifies the public API returns the original casing.
        """
        devices = ["brio", "Brio", "BRIo", "BRIO"]
        result = choose_device(devices)
        # The first match is 'brio'. It must be returned exactly as is.
        self.assertEqual(result, "brio")

    def test_choose_device_refuses_forbidden_device(self):
        """
        Reachability Test (a): 'Microphone (WH-1000XM4 Hands-Free AG Audio)' is forbidden.
        """
        devices = ["Microphone (WH-1000XM4 Hands-Free AG Audio)"]
        result = choose_device(devices)
        self.assertIsNone(result)
        self.assertEqual(journal.events, [("IDLE_NO_MIC", {})])

    def test_choose_device_empty_list(self):
        """
        Reachability Test (a): Empty list returns None.
        """
        devices = []
        result = choose_device(devices)
        self.assertIsNone(result)
        self.assertEqual(journal.events, [("IDLE_NO_MIC", {})])

    def test_choose_device_non_string_entry(self):
        """
        Reachability Test (a): Non-string entries are skipped.
        """
        devices = ["Valid Device", 123, None, "Another Valid Device"]
        result = choose_device(devices)
        # 'Valid Device' is not in allowed substrings, so it is skipped.
        # 'Another Valid Device' is not in allowed substrings, so it is skipped.
        # '123' and 'None' are skipped.
        self.assertIsNone(result)
        self.assertEqual(journal.events, [("IDLE_NO_MIC", {})])

    def test_choose_device_non_string_entry_with_match(self):
        """
        Wiring Test (b): Non-string entries are skipped, even if they look like strings.
        """
        devices = ["BRIO", 123, "Scarlett"]
        result = choose_device(devices)
        # 'BRIO' is the first valid match.
        self.assertEqual(result, "BRIO")
        self.assertEqual(journal.events, [])

    def test_choose_device_case_insensitive_matching(self):
        """
        Reachability Test (a): Case-insensitive substring matching works.
        """
        devices = ["brio", "Brio", "BRIo", "BRIO"]
        result = choose_device(devices)
        self.assertEqual(result, "brio")

    def test_choose_device_allowed_substrings(self):
        """
        Wiring Test (b): Verifies the public API respects the allowed parameter.
        """
        devices = ["BRIO", "Microphone (WH-1000XM4 Hands-Free AG Audio)", "Scarlett"]
        result = choose_device(devices)
        self.assertEqual(result, "BRIO")

    def test_is_forbidden(self):
        """
        Reachability Test (a): is_forbidden returns True for forbidden devices.
        """
        self.assertTrue(is_forbidden("WH-1000XM4"))
        self.assertTrue(is_forbidden("Hands-Free"))
        self.assertTrue(is_forbidden("Headset"))
        self.assertTrue(is_forbidden("Bluetooth"))

    def test_is_forbidden_false(self):
        """
        Reachability Test (a): is_forbidden returns False for allowed devices.
        """
        self.assertFalse(is_forbidden("BRIO"))
        self.assertFalse(is_forbidden("Scarlett"))
        self.assertFalse(is_forbidden("USBAudio"))
```