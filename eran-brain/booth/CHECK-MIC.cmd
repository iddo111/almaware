@echo off
chcp 65001 >nul
title Check the microphone  /  בדיקת מיקרופון
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
echo.
echo   Opens the mic, measures the room, RECORDS NOTHING.
echo   פותח את המיקרופון, מודד את החדר, לא מקליט כלום.
echo.
python dictionary.py --dryrun %*
echo.
pause
