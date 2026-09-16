# Kill the G.Skill Trident Z RGB DRAM LEDs. Iddo's order 2026-08-23: "יאללה, חסל את הלדים".
#
# WHY THIS EXISTS: ASUS Aura's LightingService drives the two sticks over SMBus and
# re-applies C:\Program Files (x86)\LightingService\LastProfile.xml at every boot.
# Clicking OFF in the Aura GUI turned them dark but did NOT change that profile
# (verified 2026-08-23 08:57 - mode 5 / lightness 0.5 / color 255 unchanged), so the
# LEDs would light again at the next restart. This re-asserts black through ASUS's own
# SDK (COM aura.sdk.1), which is the vendor path, not a hack.
#
# NOTE: do NOT uninstall Aura or disable LightingService. The ENE controllers on these
# sticks fall back to a rainbow cycle when nothing drives them - killing the service
# makes the RAM MORE colourful, not dark.
#
# Runs from Task Scheduler at logon. Retries because LightingService repaints for a
# while after boot and the last writer wins.

$ErrorActionPreference = 'SilentlyContinue'
$log = 'D:\CLAUDE\tools\logs\dram-leds-off.log'
New-Item -ItemType Directory -Force -Path (Split-Path $log) | Out-Null
function Say($m) { "$([DateTime]::Now.ToString('yyyy-MM-dd HH:mm:ss')) $m" | Add-Content -Path $log -Encoding utf8 }

$DRAM = 458752   # 0x00070000 - the Aura device-type id for DRAM

Say "start (attempts over ~3 min)"
for ($i = 1; $i -le 10; $i++) {
    try {
        $sdk = New-Object -ComObject 'aura.sdk.1'
        $sdk.SwitchMode()                      # take control away from the Aura service
        $devices = $sdk.Enumerate($DRAM)
        $lights = 0
        foreach ($d in $devices) {
            foreach ($l in $d.Lights) { $l.Color = 0; $lights++ }
            $d.Apply()
        }
        Say "attempt $i : $($devices.Count) stick(s), $lights light(s) -> black"
        if ($devices.Count -eq 0) { Say "attempt $i : WARNING no DRAM devices enumerated" }
    } catch {
        Say "attempt $i FAILED: $($_.Exception.Message)"
    }
    if ($i -lt 10) { Start-Sleep -Seconds 20 }
}
Say "done"
