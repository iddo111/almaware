1. FINDING: The `TERMINAL_EXES` guard is structurally unable to fire.
WHY IT CANNOT FIRE / WHEN IT LIES: The `TERMINAL_EXES` check is inside `_deliver()` (line 98), which is only reached if the primary paste path (`_paste_verified`) fails. However, `_paste_verified` (line 103) calls `self._os.send_paste()` *before* checking the target's executable name. The `send_paste()` call (line 102) is the only way to actually move the text to the clipboard. If the target is a terminal that discards Unicode, `send_paste()` fails immediately, and `_deliver()` returns `False` without ever evaluating `t1.exe in TERMINAL_EXES`.
FIX: Move the `TERMINAL_EXES` check to the beginning of `_deliver()` before `send_paste()`.

2. FINDING: The `FOCUS_BLOCK` emission is a dead guard.
WHY IT CANNOT FIRE / WHEN IT LIES: The code emits `"FOCUS_BLOCK"` (line 118) and `"PRESENCE_REJ"` (line 135) only when `d.may_enter` is False. However, the logic flow at lines 129-130 explicitly returns `TypeOutcome(True, False, ...)` *before* the emission, ensuring the function exits successfully without sending the Enter key. The emission is unreachable code.
FIX: Remove the emission lines; the function already returns the correct outcome.

3. FINDING: The `FOCUS_BLOCK` emission is a dead guard.
WHY IT CANNOT FIRE / WHEN IT LIES: The code emits `"FOCUS_BLOCK"` (line 118) when `t1.pid == self._os.own_pid()`. However, the logic at lines 115-117 explicitly returns `TypeOutcome(False, False, ...)` *before* the emission, ensuring the function exits successfully without sending the text. The emission is unreachable code.
FIX: Remove the emission lines; the function already returns the correct outcome.