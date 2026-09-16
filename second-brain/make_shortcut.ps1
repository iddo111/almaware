# Creates a Desktop shortcut for the to-do widget, with the icon. UTF-8 so Hebrew survives.
$ws = New-Object -ComObject WScript.Shell
$desktop = [Environment]::GetFolderPath('Desktop')
$path = Join-Path $desktop 'מוח שני - מטלות.lnk'
$lnk = $ws.CreateShortcut($path)
$lnk.TargetPath = 'C:\Program Files\Python312\pythonw.exe'
$lnk.Arguments = '-X utf8 "D:\CLAUDE\second-brain\todo_widget.py"'
$lnk.WorkingDirectory = 'D:\CLAUDE\second-brain'
$lnk.IconLocation = 'D:\CLAUDE\second-brain\todo.ico'
$lnk.Description = 'Second brain to-do widget'
$lnk.Save()
if (Test-Path $path) { "OK: $path" } else { "FAILED" }
