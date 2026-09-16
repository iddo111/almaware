POSITION: Ship (a) + (c) as the primary interlock, with (b) as a fallback; this ensures A is never blocked while preventing K2 from starting if A is truly alive.

REASONS:
- (a) is the only safe probe; it reads A's lock without creating one, guaranteeing A can always reacquire its mutex.
- (c) provides a lightweight, low-overhead heartbeat check that confirms A is not just holding the mutex but actively running.
- (b) is a necessary safety net to catch A if it crashes without releasing the mutex, though it is heavier and slower.

RISKS:
- (b) may falsely flag A if a similar Python script is running, requiring a command-line string match.
- (c) may falsely reject K2 if A's heartbeat lags due to system load, requiring a generous timeout window.