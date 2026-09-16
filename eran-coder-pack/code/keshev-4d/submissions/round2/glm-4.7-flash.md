```python
# app/presence.py
import time
from typing import Callable, Optional, Tuple

IDLE_NO_ENTER_S = 120
IDLE_NO_TYPE_S = 600
ARM_TTL_S = 900

class Presence:
    def __init__(self, idle_fn: Callable[[], Optional[int]], armed_mode: bool = False):
        self.idle_fn = idle_fn
        self._armed_mode = armed_mode
        self._last_arm_time: Optional[float] = None

    def _get_idle_seconds(self, now: Optional[float]) -> Tuple[bool, str]:
        if now is None:
            return True, 'clock_unreadable'
        idle = self.idle_fn()
        if idle is None:
            return True, 'clock_unreadable'
        return False, ''

    def _check_arm_expiry(self, now: Optional[float]) -> bool:
        if self._armed_mode and self._last_arm_time is not None:
            if now is None:
                return True
            elapsed = now - self._last_arm_time
            if elapsed > ARM_TTL_S:
                return False
        return True

    def verdict(self, now: Optional[float] = None) -> Tuple[bool, bool, str]:
        may_type, reason = self._get_idle_seconds(now)
        if reason:
            return True, False, reason

        if self._armed_mode:
            if not self._check_arm_expiry(now):
                return False, False, 'armed'
            return True, True, 'armed'

        idle = self.idle_fn()
        if idle is None:
            return True, False, 'clock_unreadable'

        if idle >= IDLE_NO_TYPE_S:
            return False, False, 'idle_no_type'
        if idle >= IDLE_NO_ENTER_S:
            return False, True, 'idle_no_enter'
        return True, True, 'ok'

    def arm(self, now: Optional[float] = None) -> None:
        if self._armed_mode:
            self._last_arm_time = now if now is not None else time.time()

    def disarm(self, now: Optional[float] = None) -> None:
        if self._armed_mode:
            self._last_arm_time = None

    def is_armed(self, now: Optional[float] = None) -> bool:
        if not self._armed_mode:
            return False
        return self._check_arm_expiry(now)
```

```python
# tests/test_presence.py
import unittest
import time
from app.presence import Presence, IDLE_NO_ENTER_S, IDLE_NO_TYPE_S, ARM_TTL_S

class TestPresence(unittest.TestCase):
    def test_verdict_ok(self):
        p = Presence(lambda: 0)
        self.assertEqual(p.verdict(), (True, True, 'ok'))

    def test_verdict_idle_no_enter(self):
        p = Presence(lambda: IDLE_NO_ENTER_S)
        self.assertEqual(p.verdict(), (False, True, 'idle_no_enter'))

    def test_verdict_idle_no_type(self):
        p = Presence(lambda: IDLE_NO_TYPE_S)
        self.assertEqual(p.verdict(), (False, False, 'idle_no_type'))

    def test_verdict_clock_unreadable(self):
        p = Presence(lambda: None)
        self.assertEqual(p.verdict(), (True, False, 'clock_unreadable'))

    def test_verdict_arm_required(self):
        p = Presence(lambda: 0, armed_mode=True)
        self.assertEqual(p.verdict(), (True, True, 'armed'))

    def test_verdict_arm_expired(self):
        p = Presence(lambda: 0, armed_mode=True)
        p.arm()
        time.sleep(ARM_TTL_S + 0.1)
        self.assertEqual(p.verdict(), (False, False, 'armed'))

    def test_verdict_arm_expiry_boundary(self):
        p = Presence(lambda: 0, armed_mode=True)
        p.arm()
        self.assertEqual(p.verdict(), (True, True, 'armed'))
        time.sleep(ARM_TTL_S)
        self.assertEqual(p.verdict(), (False, False, 'armed'))

    def test_verdict_idle_no_enter_boundary(self):
        p = Presence(lambda: IDLE_NO_ENTER_S)
        self.assertEqual(p.verdict(), (False, True, 'idle_no_enter'))
        p.idle_fn = lambda: IDLE_NO_ENTER_S - 1
        self.assertEqual(p.verdict(), (True, True, 'ok'))

    def test_verdict_idle_no_type_boundary(self):
        p = Presence(lambda: IDLE_NO_TYPE_S)
        self.assertEqual(p.verdict(), (False, False, 'idle_no_type'))
        p.idle_fn = lambda: IDLE_NO_TYPE_S - 1
        self.assertEqual(p.verdict(), (True, True, 'ok'))

    def test_arm_disarm(self):
        p = Presence(lambda: 0, armed_mode=True)
        p.arm()
        self.assertTrue(p.is_armed())
        p.disarm()
        self.assertFalse(p.is_armed())

    def test_reachability_idle_no_enter(self):
        p = Presence(lambda: IDLE_NO_ENTER_S)
        self.assertEqual(p.verdict(), (False, True, 'idle_no_enter'))

    def test_reachability_idle_no_type(self):
        p = Presence(lambda: IDLE_NO_TYPE_S)
        self.assertEqual(p.verdict(), (False, False, 'idle_no_type'))

    def test_reachability_clock_unreadable(self):
        p = Presence(lambda: None)
        self.assertEqual(p.verdict(), (True, False, 'clock_unreadable'))

    def test_reachability_arm_required(self):
        p = Presence(lambda: 0, armed_mode=True)
        self.assertEqual(p.verdict(), (True, True, 'armed'))

    def test_reachability_arm_expiry(self):
        p = Presence(lambda: 0, armed_mode=True)
        p.arm()
        time.sleep(ARM_TTL_S + 0.1)
        self.assertEqual(p.verdict(), (False, False, 'armed'))

    def test_reachability_arm_expiry_boundary(self):
        p = Presence(lambda: 0, armed_mode=True)
        p.arm()
        self.assertEqual(p.verdict(), (True, True, 'armed'))
        time.sleep(ARM_TTL_S)
        self.assertEqual(p.verdict(), (False, False, 'armed'))

    def test_wiring_idle_no_enter(self):
        p = Presence(lambda: IDLE_NO_ENTER_S)
        may_type, may_enter, reason = p.verdict()
        self.assertFalse(may_type)
        self.assertTrue(may_enter)
        self.assertEqual(reason, 'idle_no_enter')

    def test_wiring_idle_no_type(self):
        p = Presence(lambda: IDLE_NO_TYPE_S)
        may_type, may_enter, reason = p.verdict()
        self.assertFalse(may_type)
        self.assertFalse(may_enter)
        self.assertEqual(reason, 'idle_no_type')

    def test_wiring_clock_unreadable(self):
        p = Presence(lambda: None)
        may_type, may_enter, reason = p.verdict()
        self.assertTrue(may_type)
        self.assertFalse(may_enter)
        self.assertEqual(reason, 'clock_unreadable')

    def test_wiring_arm_required(self):
        p = Presence(lambda: 0, armed_mode=True)
        may_type, may_enter, reason = p.verdict()
        self.assertTrue(may_type)
        self.assertTrue(may_enter)
        self.assertEqual(reason, 'armed')

    def test_wiring_arm_expired(self):
        p = Presence(lambda: 0, armed_mode=True)
        p.arm()
        time.sleep(ARM_TTL_S + 0.1)
        may_type, may_enter, reason = p.verdict()
        self.assertFalse(may_type)
        self.assertFalse(may_enter)
        self.assertEqual(reason, 'armed')

    def test_wiring_arm_expiry_boundary(self):
        p = Presence(lambda: 0, armed_mode=True)
        p.arm()
        self.assertTrue(p.is_armed())
        time.sleep(ARM_TTL_S)
        may_type, may_enter, reason = p.verdict()
        self.assertFalse(may_type)
        self.assertFalse(may_enter)
        self.assertEqual(reason, 'armed')

    def test_wiring_arm_disarm(self):
        p = Presence(lambda: 0, armed_mode=True)
        p.arm()
        self.assertTrue(p.is_armed())
        p.disarm()
        self.assertFalse(p.is_armed())
```