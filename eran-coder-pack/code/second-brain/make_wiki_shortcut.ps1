$ws = New-Object -ComObject WScript.Shell
$desktop = [Environment]::GetFolderPath('Desktop')
$lnk = $ws.CreateShortcut((Join-Path $desktop 'מוח שני - הויקי.lnk'))
$lnk.TargetPath = 'D:\CLAUDE\second-brain\RUN-WIKI.cmd'
$lnk.WorkingDirectory = 'D:\CLAUDE\second-brain'
$lnk.IconLocation = 'D:\CLAUDE\second-brain\todo.ico'
$lnk.Description = 'Open the second brain wiki'
$lnk.WindowStyle = 7
$lnk.Save()
'shortcut done'
