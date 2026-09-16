# DISPATCH_FIX_REPORT.md

## What was broken
The dispatch path from PC to A70 was failing primarily due to stale connection endpoints:
1. **Stale ADB Endpoint**: `state/a70-adb-endpoint.txt` contained `<lan-ip>:38425`, but the A70 was connected via a different wireless ADB name (`adb-R58MC0KVS0X-QEqIr1._adb-tls-connect._tcp`).
2. **Brittle Logic**: `bin/dispatch-cli.ps1` relied on hardcoded state files and did not attempt to rediscover the device or refresh IPs when a connection failed.

## Changes made
### `bin/dispatch-cli.ps1`
- **Dynamic Discovery**: Added a `Refresh-Endpoints` function that:
    - Scans `adb devices` to find a device matching the A70 model (`SM-A705FN`).
    - Updates `state/a70-adb-endpoint.txt` automatically if the endpoint changed.
    - Queries the device (via `adb shell ip addr show tun0`) to get the current Tailscale IP.
    - Updates `state/a70-tailscale-ip.txt` automatically.
- **Improved Workflow**: The script now attempts Layer 2 (Tailscale) first, then triggers a refresh if it fails, retries Layer 2, and finally falls back to Layer 3 (ADB).
- **Corrected Pathing**: Fixed root pathing to ensure logs and state files are accessed correctly relative to the project root.

## How to test it
1. Ensure the A70 has Wireless Debugging enabled and is visible in `adb devices`.
2. Run the dispatch CLI from the project root:
   ```powershell
   powershell.exe -NoProfile -File bin/dispatch-cli.ps1 -Msg "Test message"
   ```
3. Verify the output:
    - It should say `ok via tailscale` if the Termux bridge is up.
    - It should say `ok via adb` (after a refresh) if the bridge is down but ADB is reachable.
4. Check `state/a70-adb-endpoint.txt` to confirm it now contains the correct ADB identifier.
5. Check `dispatch-fix.log` for the "refresh: new ADB endpoint found" audit trail.
