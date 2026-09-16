@echo off
REM Closes Chrome, relaunches it with the CDP debug port on YOUR normal profile
REM (so your Amazon login is used). Then tell Claude "ready" and it pushes the BOM.
taskkill /F /IM chrome.exe >/dev/null 2>&1
timeout /t 2 >/dev/null
start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --restore-last-session
echo Chrome relaunched with CDP on :9222. Make sure you're logged into Amazon, then tell Claude.
