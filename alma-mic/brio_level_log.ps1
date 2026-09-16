# brio_level_log.ps1 — infra-rebuild Stage 1.6 (2026-08-12): BRIO capture-level READ-AND-LOG.
# READ ONLY — never sets volume, never changes default devices, never touches the running mic.
# Run by task ALMA-MIC-BrioLevelLog (logon +PT6M). Plan: D:\CLAUDE\infra-rebuild\PHASE1-INFRA-INQUIRY.md 1.6
$log = 'D:\CLAUDE\alma-mic\brio_level.log'
$stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
try {
    Import-Module AudioDeviceCmdlets -ErrorAction Stop
    $dev = Get-AudioDevice -Recording
    if ($dev.Name -match 'BRIO') {
        $vol = Get-AudioDevice -RecordingVolume
        Add-Content -LiteralPath $log -Value "$stamp BRIO capture level = $vol"
    } else {
        Add-Content -LiteralPath $log -Value "$stamp default recording device is '$($dev.Name)' (not BRIO) - level not read"
    }
} catch {
    Add-Content -LiteralPath $log -Value "$stamp READ FAILED: $($_.Exception.Message)"
}
