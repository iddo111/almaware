# Manual Termux daemon start

Termux's `RUN_COMMAND` service requires `com.termux.permission.RUN_COMMAND` which adb shell cannot grant. So bridge start is a 10-second manual step.

## One-time

1. Open **Termux** on the A70.
2. Paste:
   ```
   nohup python ~/a70-bridge.py >/tmp/a70-bridge.log 2>&1 &
   disown
   ```
3. Tell PC-Claude "bridge started".

## Verify

PC side:
```
adb -s <lan-ip>:43947 reverse tcp:18181 tcp:18181
curl -sS http://localhost:18181/ping
# expect: pong
```

## Survives Termux app close?

Yes — `nohup` + `disown` makes it independent of the Termux session. Survives until the phone reboots OR Android kills it for memory pressure (Doze mode).

## Survives reboot?

No. Re-do the one-time step after each reboot. To make it persistent: install **Termux:Boot** from F-Droid (Play Store version cannot autostart), then drop a script at `~/.termux/boot/00-bridge.sh`.
