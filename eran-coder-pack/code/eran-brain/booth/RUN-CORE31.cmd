@echo off
chcp 65001 >nul
title ERAN core31  /  31 היחידות של ערן
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
echo.
echo   ERAN's own curriculum: 22 syllables + 4 vowels + 5 family words.
echo   התוכנית של ערן: 22 הברות + 4 תנועות + 5 מילים של המשפחה.
echo   3 takes of each.  /  שלוש פעמים כל אחת.
echo.
python dictionary.py --list "lists\core31.txt" --takes 3 --person iddo %*
echo.
pause
