$env:OMP_NUM_THREADS = "4"
Set-Location "D:\CLAUDE\colibri-pc\release"

# "כתוב פונקציית פייתון שקוראת קובץ JSON ומחזירה את המפתחות שלו" built from code points
# to avoid any file-encoding ambiguity.
$codes = 0x05DB,0x05EA,0x05D5,0x05D1,0x0020,0x05E4,0x05D5,0x05E0,0x05E7,0x05E6,0x05D9,0x05D9,0x05EA,0x0020,`
         0x05E4,0x05D9,0x05D9,0x05EA,0x05D5,0x05DF,0x0020,0x05E9,0x05E7,0x05D5,0x05E8,0x05D0,0x05EA,0x0020,`
         0x05E7,0x05D5,0x05D1,0x05E5,0x0020,0x004A,0x0053,0x004F,0x004E,0x0020,0x05D5,0x05DE,0x05D7,0x05D6,`
         0x05D9,0x05E8,0x05D4,0x0020,0x05D0,0x05EA,0x0020,0x05D4,0x05DE,0x05E4,0x05EA,0x05D7,0x05D5,0x05EA,`
         0x0020,0x05E9,0x05DC,0x05D5
$prompt = -join ($codes | ForEach-Object { [char]$_ })

"[$(Get-Date -Format o)] prompt=$prompt (len=$($prompt.Length))" | Out-File "D:\CLAUDE\colibri-pc\test_hebrew.log" -Encoding utf8

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = "python"
$psi.Arguments = 'coli run "' + $prompt + '" --model "C:\models\colibri\DeepSeek-V4-Flash-reap-150b" --ram 10 --cap 0 --ctx 1024 --ngen 24'
$psi.UseShellExecute = $false
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true
$psi.WorkingDirectory = "D:\CLAUDE\colibri-pc\release"
$psi.EnvironmentVariables["OMP_NUM_THREADS"] = "4"
$psi.StandardOutputEncoding = [System.Text.Encoding]::UTF8
$psi.StandardErrorEncoding = [System.Text.Encoding]::UTF8

try {
    $proc = [System.Diagnostics.Process]::Start($psi)
} catch {
    "[$(Get-Date -Format o)] START_FAILED: $_" | Out-File "D:\CLAUDE\colibri-pc\test_hebrew.log" -Append -Encoding utf8
    "[$(Get-Date -Format o)] EXIT code=-999" | Out-File "D:\CLAUDE\colibri-pc\test_hebrew.log" -Append -Encoding utf8
    exit 1
}
try { $proc.PriorityClass = 'BelowNormal' } catch {}
"[$(Get-Date -Format o)] PID=$($proc.Id) started" | Out-File "D:\CLAUDE\colibri-pc\test_hebrew.log" -Append -Encoding utf8
$proc.Id | Out-File "D:\CLAUDE\colibri-pc\test_hebrew.pid" -Encoding ascii
while (-not $proc.StandardOutput.EndOfStream) {
    $line = $proc.StandardOutput.ReadLine()
    "[$(Get-Date -Format o)] OUT: $line" | Out-File "D:\CLAUDE\colibri-pc\test_hebrew.log" -Append -Encoding utf8
}
$errText = $proc.StandardError.ReadToEnd()
if ($errText) { "[$(Get-Date -Format o)] ERR: $errText" | Out-File "D:\CLAUDE\colibri-pc\test_hebrew.log" -Append -Encoding utf8 }
$proc.WaitForExit()
"[$(Get-Date -Format o)] EXIT code=$($proc.ExitCode)" | Out-File "D:\CLAUDE\colibri-pc\test_hebrew.log" -Append -Encoding utf8
