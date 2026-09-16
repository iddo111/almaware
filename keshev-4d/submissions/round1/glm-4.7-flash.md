```python
# app/devicelaw.py
import re
from typing import List, Optional, Tuple

_NEVER_MIC: Tuple[str, ...] = ("WH-1000", "Hands-Free", "Headset", "Bluetooth")

_ALLOWED_SUBSTRINGS_DEFAULT: Tuple[str, ...] = ("BRIO", "Scarlett", "USBAudio")

def is_forbidden(device_name: str) -> bool:
    """
    Determines if a device name is part of the hard-coded blacklist.
    """
    lower_name = device_name.lower()
    for forbidden_term in _NEVER_MIC:
        if forbidden_term.lower() in lower_name:
            return True
    return False

def choose_device(device_names: List[str], allowed: Tuple[str, ...] = _ALLOWED_SUBSTRINGS_DEFAULT) -> Optional[str]:
    """
    Selects the first device name that matches the allowed substrings and is not forbidden.
    
    Args:
        device_names: A list of device names provided by the OS enumeration.
        allowed: A tuple of substrings that define the allowed device criteria.
        
    Returns:
        The first matching device name, or None if no device qualifies.
    """
    if not device_names:
        return None

    for name in device_names:
        if not isinstance(name, str):
            continue

        if is_forbidden(name):
            continue

        lower_name = name.lower()
        if any(substring.lower() in lower_name for substring in allowed):
            return name

    return None
```

```python
# tests/test_devicelaw.py
import unittest
from app.devicelaw import choose_device, is_forbidden, _NEVER_MIC, _ALLOWED_SUBSTRINGS_DEFAULT

class TestDeviceLaw(unittest.TestCase):
    def test_is_forbidden(self):
        self.assertTrue(is_forbidden("WH-1000XM4 Hands-Free AG Audio"))
        self.assertTrue(is_forbidden("Headset Pro"))
        self.assertTrue(is_forbidden("Bluetooth Audio"))
        self.assertFalse(is_forbidden("Scarlett 2i2"))

    def test_choose_device_brio_passes(self):
        devices = ["Microphone (BRIO)", "Internal Mic"]
        result = choose_device(devices)
        self.assertEqual(result, "Microphone (BRIO)")

    def test_choose_device_empty_list(self):
        self.assertIsNone(choose_device([]))

    def test_choose_device_no_match(self):
        devices = ["Unknown Device", "Generic Audio"]
        self.assertIsNone(choose_device(devices))

    def test_choose_device_malicious_allowed_override(self):
        devices = ["WH-1000XM4 Hands-Free AG Audio"]
        result = choose_device(devices, allowed=("WH-1000",))
        self.assertIsNone(result)

    def test_choose_device_case_insensitive(self):
        devices = ["microphone (brio)", "Microphone (BRIO)"]
        result = choose_term = choose_device(devices)
        self.assertEqual(result, "Microphone (BRIO)")

    def test_choose_device_multiple_allowed(self):
        devices = ["Scarlett 2i2", "BRIO", "USBAudio"]
        result = choose_device(devices)
        self.assertEqual(result, "Scarlett 2i2")

    def test_choose_device_non_string_entry(self):
        devices = ["Valid Device", 12345, None]
        result = choose_device(devices)
        self.assertEqual(result, "Valid Device")

if __name__ == '__main__':
    unittest.main()
```