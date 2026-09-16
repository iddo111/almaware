@echo off
chcp 65001 >nul
title ERAN Dictionary  /  המילון של ערן
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
echo.
echo   ERAN DICTIONARY  /  המילון של ערן
echo   ---------------------------------------------------------------
echo   USB microphone only. Bluetooth headsets are refused.
echo   מיקרופון USB בלבד. אוזניות בלוטות' - אסור.
echo   If KESHEV is running, close it first.  /  אם קשב פתוח - תסגור אותו.
echo.
python dictionary.py --list "lists\dict-alef.txt" --id-prefix a --person iddo %*
echo.
echo   ---------------------------------------------------------------
echo   Done. Everything is saved.  /  נגמר. הכל שמור.
pause
