```python
import time
from typing import Callable, Optional, Tuple

IDLE_NO_ENTER_S = 120
IDLE_NO_TYPE_S = 600
ARM_TTL_S = 900

class Presence:
    def __init__(self, idle_fn: Callable[[], Optional[int]], armed_mode: bool = False):
        self._idle_fn = idle_fn
        self._armed_mode = armed_mode
        self._arm_time: Optional[float] = None
        self._is_armed = False

    def arm(self, now: Optional[float] = None) -> None:
        self._arm_time = now if now is not None else time.time()
        self._is_armed = True

    def disarm(self) -> None:
        self._is_armed = False
        self._arm_time = None

    def is_armed(self, now: Optional[float] = None) -> bool:
        if not self._is_armed or self._arm_time is None:
            return False
        current_time = now if now is not None else time.time()
        return current_time - self._arm_time <= ARM_TTL_S

    def verdict(self, now: Optional[float] = None) -> Tuple[bool, bool, str]:
        current_time = now if now is not None else time.time()
        
        # Handle armed mode first
        if self._armed_mode:
            if not self.is_armed(current_time):
                return (False, False, 'arm_required')
            return (True, True, 'armed')
        
        # Get idle time
        idle_time = self._idle_fn()
        if idle_time is None:
            return (True, False, 'clock_unreadable')
        
        # Apply rules in order of specificity (most restrictive first)
        if idle_time >= IDLE_NO_TYPE_S:
            return (False, False, 'idle_no_type')
        if idle_time >= IDLE_NO_ENTER_S:
            return (True, False, 'idle_no_enter')
        
        return (True, True, 'ok')
```

```python
import unittest
import time
from app.presence import Presence, IDLE_NO_ENTER_S, IDLE_NO_TYPE_S, ARM_TTL_S

class TestPresence(unittest.TestCase):
    def test_idle_no_enter_reachability(self):
        # Reachability: idle_time = 120 (boundary inclusive)
        idle_fn = lambda: 120
        p = Presence(idle_fn)
        may_type, may_enter, reason = p.verdict()
        self.assertEqual(reason, 'idle_no_enter')
        self.assertTrue(may_type)
        self.assertFalse(may_enter)

    def test_idle_no_enter_wiring(self):
        # Wiring: inject mutable holder to avoid rebinding issues
        idle_holder = [120]
        idle_fn = lambda: idle_holder[0]
        p = Presence(idle_fn)
        may_type, may_enter, reason = p.verdict()
        self.assertEqual(reason, 'idle_no_enter')
        idle_holder[0] = 121  # Just above boundary
        may_type, may_enter, reason = p.verdict()
        self.assertEqual(reason, 'idle_no_enter')

    def test_idle_no_type_reachability(self):
        # Reachability: idle_time = 600 (boundary inclusive)
        idle_fn = lambda: 600
        p = Presence(idle_fn)
        may_type, may_enter, reason = p.verdict()
        self.assertEqual(reason, 'idle_no_type')
        self.assertFalse(may_type)
        self.assertFalse(may_enter)

    def test_idle_no_type_wiring(self):
        idle_holder = [600]
        idle_fn = lambda: idle_holder[0]
        p = Presence(idle_fn)
        may_type, may_enter, reason = p.verdict()
        self.assertEqual(reason, 'idle_no_type')
        idle_holder[0] = 601
        may_type, may_enter, reason = p.verdict()
        self.assertEqual(reason, 'idle_no_type')

    def test_ok_reachability(self):
        # Reachability: idle_time = 119 (just below idle_no_enter)
        idle_fn = lambda: 119
        p = Presence(idle_fn)
        may_type, may_enter, reason = p.verdict()
        self.assertEqual(reason, 'ok')
        self.assertTrue(may_type)
        self.assertTrue(may_enter)

    def test_ok_wiring(self):
        idle_holder = [119]
        idle_fn = lambda: idle_holder[0]
        p = Presence(idle_fn)
        may_type, may_enter, reason = p.verdict()
        self.assertEqual(reason, 'ok')
        idle_holder[0] = 0
        may_type, may_enter, reason = p.verdict()
        self.assertEqual(reason, 'ok')

    def test_clock_unreadable_reachability(self):
        # Reachability: idle_fn returns None
        idle_fn = lambda: None
        p = Presence(idle_fn)
        may_type, may_enter, reason = p.verdict()
        self.assertEqual(reason, 'clock_unreadable')
        self.assertTrue(may_type)
        self.assertFalse(may_enter)

    def test_clock_unreadable_wiring(self):
        idle_holder = [None]
        idle_fn = lambda: idle_holder[0]
        p = Presence(idle_fn)
        may_type, may_enter, reason = p.verdict()
        self.assertEqual(reason, 'clock_unreadable')
        idle_holder[0] = 0
        may_type, may_enter, reason = p.verdict()
        self.assertEqual(reason, 'ok')

    def test_arm_required_reachability(self):
        # Reachability: armed_mode=True, but not armed
        p = Presence(lambda: 0, armed_mode=True)
        may_type, may_enter, reason = p.verdict()
        self.assertEqual(reason, 'arm_required')
        self.assertFalse(may_type)
        self.assertFalse(may_enter)

    def test_arm_required_wiring(self):
        p = Presence(lambda: 0, armed_mode=True)
        may_type, may_enter, reason = p.verdict()
        self.assertEqual(reason, 'arm_required')
        p.arm()
        may_type, may_enter, reason = p.verdict()
        self.assertEqual(reason, 'armed')

    def test_armed_reachability(self):
        # Reachability: armed_mode=True and armed
        p = Presence(lambda: 0, armed_mode=True)
        p.arm()
        may_type, may_enter, reason = p.verdict()
        self.assertEqual(reason, 'armed')
        self.assertTrue(may_type)
        self.assertTrue(may_enter)

    def test_armed_wiring(self):
        p = Presence(lambda: 0, armed_mode=True)
        p.arm()
        may_type, may_enter, reason = p.verdict()
        self.assertEqual(reason, 'armed')
        p.disarm()
        may_type, may_enter, reason = p.verdict()
        self.assertEqual(reason, 'arm_required')

    def test_arm_expiry_reachability(self):
        # Reachability: arm expires at now=arm_time+ARM_TTL_S+1
        base_time = time.time()
        p = Presence(lambda: 0, armed_mode=True)
        p.arm(base_time)
        # At exactly TTL, still armed
        may_type, may_enter, reason = p.verdict(base_time + ARM_TTL_S)
        self.assertEqual(reason, 'armed')
        # At TTL+1, expired
        may_type, may_enter, reason = p.verdict(base_time + ARM_TTL_S + 1)
        self.assertEqual(reason, 'arm_required')

    def test_arm_expiry_wiring(self):
        base_time = time.time()
        p = Presence(lambda: 0, armed_mode=True)
        p.arm(base_time)
        # Verify armed at TTL
        may_type, may_enter, reason = p.verdict(base_time + ARM_TTL_S)
        self.assertEqual(reason, 'armed')
        # Verify expired at TTL+1
        may_type, may_enter, reason = p.verdict(base_time + ARM_TTL_S + 1)
        self.assertEqual(reason, 'arm_required')

    def test_arm_expiry_boundary(self):
        # Test exact boundary: TTL+0.5 should still be armed (since TTL is inclusive)
        base_time = time.time()
        p = Presence(lambda: 0, armed_mode=True)
        p.arm(base_time)
        may_type, may_enter, reason = p.verdict(base_time + ARM_TTL_S + 0.5)
        self.assertEqual(reason, 'armed')

    def test_arm_expiry_exact_boundary(self):
        # Test exact boundary: TTL+1.0 should be expired
        base_time = time.time()
        p = Presence(lambda: 0, armed_mode=True)
        p.arm(base_time)
        may_type, may_enter, reason = p.verdict(base_time + ARM_TTL_S + 1.0)
        self.assertEqual(reason, 'arm_required')

    def test_arm_expiry_with_disarm(self):
        base_time = time.time()
        p = Presence(lambda: 0, armed_mode=True)
        p.arm(base_time)
        p.disarm()
        may_type, may_enter, reason = p.verdict(base_time + ARM_TTL_S + 1)
        self.assertEqual(reason, 'arm_required')

    def test_arm_expiry_with_rearm(self):
        base_time = time.time()
        p = Presence(lambda: 0, armed_mode=True)
        p.arm(base_time)
        p.disarm()
        p.arm(base_time + 100)  # New arm time
        may_type, may_enter, reason = p.verdict(base_time + ARM_TTL_S + 1)
        self.assertEqual(reason, 'arm_required')
        may_type, may_enter, reason = p.verdict(base_time + 100 + ARM_TTL_S)
        self.assertEqual(reason, 'armed')
```