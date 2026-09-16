@echo off
REM Pull ERAN's snapshots off eran1 to the healthy E: drive, every 30 min.
REM eran1 dying must not take the child with it. Hidden via run_hidden.vbs.
REM (no trailing backslash before the closing quote - it escapes the quote for scp)
scp -q -o ConnectTimeout=10 -o BatchMode=yes -r "eran1:~/eran-brain-saves/." "E:/ALMA-Backups/eran-saves/" >> "E:/ALMA-Backups/eran-saves/pull.log" 2>&1
