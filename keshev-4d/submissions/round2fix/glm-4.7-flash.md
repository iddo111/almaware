```python
# app/presence.py
import time
import sys
import os
from typing import Callable, Optional, Tuple

# Hard path constraint
APP_DIR = r"D:\CLAUDE\keshev-4d"
if not os.path.exists(APP_DIR):
    sys.exit(1)

# Constants
IDLE_NO_ENTER_S = 120
IDLE_NO_TYPE_S = 600
ARM_TTL_S = 900

class Presence:
    def __init__(self, idle_fn: Callable[[], Optional[float]], armed_mode: bool = False):
        self.idle_fn = idle_fn
        self._armed_mode = armed_mode
        self._last_arm_time: Optional[float] = None

    def _is_armed(self, now: float) -> bool:
        if not self._armed_mode:
            return False
        if self._last_arm_time is None:
            return False
        return (now - self._last_arm_time) < ARM_TTL_S

    def arm(self, now: float) -> None:
        self._last_arm_time = now

    def disarm(self) -> None:
        self._last_arm_time = None

    def is_armed(self, now: float) -> bool:
        return self._is_armed(now)

    def verdict(self, now: Optional[float] = None) -> Tuple[bool, bool, str]:
        if now is None:
            now = time.time()
        
        idle_time = self.idle_fn()
        if idle_time is None:
            return (True, False, "clock_unreadable")

        may_type = True
        may_enter = True
        reason = "ok"

        if idle_time >= IDLE_NO_TYPE_S:
            may_type = False
            may_enter = False
            reason = "idle_no_type"
        elif idle_time >= IDLE_NO_ENTER_S:
            may_enter = False
            reason = "idle_no_enter"

        if self._is_armed(now):
            reason = "armed"
            may_type = True
            may_enter = True

        return (may_type, may_enter, reason)
```


```python
# tests/test_presence.py
import unittest
from unittest.mock import patch
import sys
import os

# Add parent directory to path to import module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.presence import Presence, ARM_TTL_S, IDLE_NO_ENTER_S, IDLE_NO_TYPE_S

class TestPresence(unittest.TestCase):
    def setUp(self):
        self.idle_fn = lambda: 0.0

    def test_verdict_idle_no_type(self):
        p = Presence(self.idle_fn)
        # Guard: idle >= 600
        self.idle_fn = lambda: IDLE_NO_TYPE_S
        # Wiring: verdict calls idle_fn
        result = p.verdict(now=1000.0)
        self.assertEqual(result, (False, False, "idle_no_type"))

    def test_verdict_idle_no_enter(self):
        p = Presence(self.idle_fn)
        # Guard: idle >= 120
        self.idle_fn = lambda: IDLE_NO_ENTER_S
        # Wiring: verdict calls idle_fn
        result = p.verdict(now=1000.0)
        self.assertEqual(result, (True, False, "idle_no_enter"))

    def test_verdict_clock_unreadable(self):
        p = Presence(self.idle_fn)
        # Guard: idle_fn returns None
        self.idle_fn = lambda: None
        # Wiring: verdict calls idle_fn
        result = p.verdict(now=1000.0)
        self.assertEqual(result, (True, False, "clock_unreadable"))

    def test_verdict_ok(self):
        p = Presence(self.idle_fn)
        # Guard: idle < 120
        self.idle_fn = lambda: 10.0
        # Wiring: verdict calls idle_fn
        result = p.verdict(now=1000.0)
        self.assertEqual(result, (True, True, "ok"))

    def test_arm_expiry(self):
        p = Presence(self.idle_fn, armed_mode=True)
        # Guard: (now - last_arm) < ARM_TTL_S
        p.arm(now=1000.0)
        # Wiring: is_armed calls _is_armed
        self.assertTrue(p.is_armed(now=1000.0))
        # Wiring: verdict calls is_armed
        self.assertEqual(p.verdict(now=1000.0), (True, True, "armed"))
        
        # Guard: (now - last_arm) >= ARM_TTL_S
        p.arm(now=1000.0)
        self.assertFalse(p.is_armed(now=1000.0 + ARM_TTL_S))
        # Wiring: verdict calls is_armed
        self.assertEqual(p.verdict(now=1000.0 + ARM_TTL_S), (True, True, "ok"))

    def test_disarm(self):
        p = Presence(self.idle_fn, armed_mode=True)
        p.arm(now=1000.0)
        # Wiring: disarm calls _last_arm_time = None
        p.disarm()
        # Wiring: is_armed calls _is_armed
        self.assertFalse(p.is_armed(now=1000.0))
        # Wiring: verdict calls is_armed
        self.assertEqual(p.verdict(now=LastInputInfoMock.time()), (True, True, "ok"))

    def test_verdict_no_arm_required(self):
        p = Presence(self.idle_fn, armed_mode=False)
        # Guard: armed_mode is False
        self.idle_fn = lambda: IDLE_NO_TYPE_S
        # Wiring: verdict calls _is_armed
        self.assertEqual(p.verdict(now=1000.0), (False, False, "idle_no_type"))

class LastInputInfoMock:
    @staticmethod
    def time():
        return 1000.0

if __name__ == '__main__':
    unittest.main()
```