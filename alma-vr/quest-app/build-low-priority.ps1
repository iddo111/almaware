$env:JAVA_HOME = "C:\Program Files\Eclipse Adoptium\jdk-21.0.11.10-hotspot"
$projDir = "D:\CLAUDE\alma-vr\quest-app"
Set-Location $projDir
$gradleBat = "D:\CLAUDE\_toolchain\gradle\gradle-8.7\bin\gradle.bat"
$logFile = "D:\CLAUDE\alma-vr\quest-app\build.log"
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = "cmd.exe"
$psi.Arguments = "/c $gradleBat --no-daemon assembleDebug --stacktrace --console=plain > $logFile 2>&1"
$psi.WorkingDirectory = $projDir
$psi.UseShellExecute = $false
$proc = [System.Diagnostics.Process]::Start($psi)
$proc.PriorityClass = [System.Diagnostics.ProcessPriorityClass]::BelowNormal
Write-Host "started pid $($proc.Id) at BelowNormal priority, cwd=$projDir, no-daemon mode"
$proc.WaitForExit()
Write-Host "exit code: $($proc.ExitCode)"
