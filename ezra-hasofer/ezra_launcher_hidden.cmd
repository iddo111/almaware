@echo off
powershell.exe -NoProfile -WindowStyle Hidden -Command "Start-Process -FilePath 'C:\Program Files\Python312\pythonw.exe' -ArgumentList '\"D:\CLAUDE\ezra-hasofer\ezra_hasofer.py\"' -WorkingDirectory 'D:\CLAUDE\ezra-hasofer' -WindowStyle Hidden -Wait"
