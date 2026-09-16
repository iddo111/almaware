```python
# app/presence.py
import os
import time
from datetime import datetime, timezone
from pathlib import Path

APP_DIR = Path(r"D:\CLAUDE\keshev-4d")
LOG_DIR = APP_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
JOURNAL_PATH = LOG_DIR / "journal.log"

IDLE_NO_ENTER_S = 120
IDLE_NO_TYPE_S = 600
ARM_TTL_S = 900

_last_enter_time = None
_last_type_time = None
_arm_time = None

def _now() -> float:
    return time.time()

def _log_event(event_type: str, details: str):
    timestamp = datetime.now(timezone.utc).isoformat()
    line = f"{timestamp} | {event_type} | {details}\n"
    with open(JOURNAL_PATH, "a", encoding="utf-8") as f:
        f.write(line)

def init():
    global _last_enter_time, _last_type_time, _arm_time
    _last_enter_time = _now()
    _last_type_time = _now()
    _arm_time = None

def on_enter():
    global _last_enter_time
    _last_enter_time = _now()

def on_type():
    global _last_type_time
    _last_type_time = _now()

def is_idle() -> bool:
    now = _now()
    idle_enter = (now - _last_enter_time) >= IDLE_NO_ENTER_S
    idle_type = (now - _last_type_time) >= IDLE_NO_TYPE_S
    return idle_enter or idle_type

def is_armed(now: float = None) -> bool:
    global _arm_time
    if _arm_time is None:
        return False
    if now is None:
        now = _now()
    return now < _arm_time + ARM_TTL_S

def arm():
    global _arm_time
    _arm_time = _now()
    _log_event("ARMED", f"arm_time={_arm_time}")

def disarm():
    global _arm_time
    if _arm_time is not None:
        _log_event("DISARMED", f"disarm_time={_now()}")
    _arm_time = None

def check_and_refuse(reason: str):
    if is_idle() or is_armed():
        _log_event("REFUSED", reason)
        return True
    return False

def check_and_drop(reason: str):
    if not is_armed():
        _log_event("DROPPED", reason)
        return True
    return False
```

```python
# tests/test_presence.py
import unittest
import os
import sys
import time
from pathlib import Path

# Ensure module path is correct
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.presence import (
    init, on_enter, on_type, is_idle, is_armed, arm, disarm,
    check_and_refuse, check_and_drop, JOURNAL_PATH,
    IDLE_NO_ENTER_S, IDLE_NO_TYPE_S, ARM_TTL_S
)

class TestPresence(unittest.TestCase):
    def setUp(self):
        # Clean journal before each test
        if JOURNAL_PATH.exists():
            JOURNAL_PATH.unlink()
        init()

    def tearDown(self):
        # Clean journal after each test
        if JOURNAL_PATH.exists():
            JOURNAL_PATH.unlink()

    def test_init_sets_times(self):
        init()
        now = time.time()
        # Times should be set to now (within 1 sec tolerance)
        from app.presence import _last_enter_time, _last_type_time
        self.assertLessEqual(now - _last_enter_time, 1.0)
        self.assertLessEqual(now - _last_type_time, 1.0)

    def test_on_enter_updates_enter_time(self):
        t0 = time.time()
        time.sleep(0.01)
        on_enter()
        from app.presence import _last_enter_time
        self.assertGreaterEqual(_last_enter_time, t0 + 0.01)

    def test_on_type_updates_type_time(self):
        t0 = time.time()
        time.sleep(0.01)
        on_type()
        from app.presence import _last_type_time
        self.assertGreaterEqual(_last_type_time, t0 + 0.01)

    def test_is_idle_no_enter_boundary(self):
        # Reachability: idle triggers when no_enter >= 120s
        init()
        from app.presence import _last_enter_time
        _last_enter_time = time.time() - 120.0  # exactly at boundary
        self.assertTrue(is_idle())  # idle >= 120

    def test_is_idle_no_type_boundary(self):
        # Reachability: idle triggers when no_type >= 600s
        init()
        from app.presence import _last_type_time
        _last_type_time = time.time() - 600.0  # exactly at boundary
        self.assertTrue(is_idle())  # idle >= 600

    def test_is_idle_not_idle_under_boundaries(self):
        init()
        from app.presence import _last_enter_time, _last_type_time
        _last_enter_time = time.time() - 119.9
        _last_type_time = time.time() - 599.9
        self.assertFalse(is_idle())

    def test_arm_sets_arm_time(self):
        arm()
        from app.presence import _arm_time
        self.assertIsNotNone(_arm_time)
        self.assertGreater(_arm_time, 0)

    def test_is_armed_before_ttl(self):
        arm()
        # Before TTL: armed
        self.assertTrue(is_armed(time.time() + ARM_TTL_S - 1))

    def test_is_armed_at_ttl(self):
        arm()
        # At TTL: NOT armed (strictly before TTL)
        self.assertFalse(is_armed(time.time() + ARM_TTL_S))

    def test_is_armed_past_ttl(self):
        arm()
        # Past TTL: NOT armed
        self.assertFalse(is_armed(time.time() + ARM_TTL_S + 1))

    def test_disarm_clears_arm_time(self):
        arm()
        disarm()
        from app.presence import _arm_time
        self.assertIsNone(_arm_time)

    def test_check_and_refuse_refuses_idle(self):
        # Simulate idle by setting last_enter_time far in past
        init()
        from app.presence import _last_enter_time
        _last_enter_time = time.time() - 121
        result = check_and_refuse("idle_no_enter")
        self.assertTrue(result)
        self.assertIn("REFUSED", JOURNAL_PATH.read_text())

    def test_check_and_refuse_refuses_armed(self):
        arm()
        result = check_and_refuse("already_armed")
        self.assertTrue(result)
        self.assertIn("REFUSED", JOURNAL_PATH.read_text())

    def test_check_and_refuse_does_not_refuse_active(self):
        init()
        result = check_and_refuse("active_session")
        self.assertFalse(result)
        self.assertNotIn("REFUSED", JOURNAL_PATH.read_text())

    def test_check_and_drop_drops_not_armed(self):
        result = check_and_drop("not_armed")
        self.assertTrue(result)
        self.assertIn("DROPPED", JOURNAL_PATH.read_text())

    def test_check_and_drop_does_not_drop_armed(self):
        arm()
        result = check_and_drop("armed_session")
        self.assertFalse(result)
        self.assertNotIn("DROPPED", JOURNAL_PATH.read_text())

    def test_arm_writes_journal(self):
        arm()
        self.assertIn("ARMED", JOURNAL_PATH.read_text())

    def test_disarm_writes_journal(self):
        arm()
        disarm()
        self.assertIn("DISARMED", JOURNAL_PATH.read_text())

    def test_journal_writes_on_refusal(self):
        init()
        from app.presence import _last_enter_time
        _last_enter_time = time.time() - 121
        check_and_refuse("test_refusal")
        text = JOURNAL_PATH.read_text()
        self.assertIn("REFUSED", text)
        self.assertIn("test_refusal", text)

    def test_journal_writes_on_drop(self):
        check_and_drop("test_drop")
        text = JOURNAL_PATH.read_text()
        self.assertIn("DROPPED", text)
        self.assertIn("test_drop", text)

    def test_arm_boundary_exact_ttl(self):
        # Wiring test: arm() sets _arm_time, then is_armed(now) uses it
        arm()
        from app.presence import _arm_time
        # At exactly _arm_time + ARM_TTL_S, is_armed must be False
        self.assertFalse(is_armed(_arm_time + ARM_TTL_S))

    def test_arm_boundary_before_ttl(self):
        # Wiring test: verify armed strictly before TTL
        arm()
        from app.presence import _arm_time
        # At _arm_time + ARM_TTL_S - 1, is_armed must be True
        self.assertTrue(is_armed(_arm_time + ARM_TTL_S - 1))

if __name__ == '__main__':
    unittest.main()
```