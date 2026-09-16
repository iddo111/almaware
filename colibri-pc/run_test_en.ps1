$env:OMP_NUM_THREADS = "4"
$env:COLI_NO_OMP_TUNE = ""
Set-Location "D:\CLAUDE\colibri-pc\release"
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = "python"
$psi.Arguments = 'coli run "Explain what a mixture-of-experts router does in three sentences." --model "C:\models\colibri\DeepSeek-V4-Flash-reap-150b" --ram 15 --ctx 2048 --ngen 48'
$psi.UseShellExecute = $false
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true
$psi.WorkingDirectory = "D:\CLAUDE\colibri-pc\release"
$psi.EnvironmentVariables["OMP_NUM_THREADS"] = "4"
$proc = [System.Diagnostics.Process]::Start($psi)
try { $proc.PriorityClass = 'BelowNormal' } catch {}
"[$(Get-Date -Format o)] PID=$($proc.Id) started" | Out-File "D:\CLAUDE\colibri-pc\test_english.log" -Encoding utf8
$proc.Id | Out-File "D:\CLAUDE\colibri-pc\test_english.pid" -Encoding ascii
while (-not $proc.StandardOutput.EndOfStream) {
    $line = $proc.StandardOutput.ReadLine()
    "[$(Get-Date -Format o)] OUT: $line" | Out-File "D:\CLAUDE\colibri-pc\test_english.log" -Append -Encoding utf8
}
$errText = $proc.StandardError.ReadToEnd()
if ($errText) { "[$(Get-Date -Format o)] ERR: $errText" | Out-File "D:\CLAUDE\colibri-pc\test_english.log" -Append -Encoding utf8 }
$proc.WaitForExit()
"[$(Get-Date -Format o)] EXIT code=$($proc.ExitCode)" | Out-File "D:\CLAUDE\colibri-pc\test_english.log" -Append -Encoding utf8
