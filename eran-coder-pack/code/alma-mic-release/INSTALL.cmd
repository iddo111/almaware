@echo off
rem Almaware Voice Typer — one-time install (creates a private Python env here).
rem התקנה חד-פעמית: יוצר סביבת פייתון פרטית בתיקייה הזו ומתקין את התלויות.
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo === Almaware Voice Typer - install / התקנה ===
echo.

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (where python >nul 2>nul && set "PY=python")
if not defined PY (
  echo Python 3 was not found. Install it from https://www.python.org/downloads/
  echo ^(check "Add python.exe to PATH" in the installer^) and run me again.
  echo פייתון לא נמצא. התקינו מ-python.org ^(סמנו "Add python.exe to PATH"^) והריצו שוב.
  pause
  exit /b 1
)

echo Creating private environment ^(venv^)...
%PY% -m venv venv
if errorlevel 1 (
  echo Failed to create venv. / יצירת הסביבה נכשלה.
  pause
  exit /b 1
)

echo Installing dependencies ^(a few minutes^)... / מתקין תלויות ^(כמה דקות^)...
venv\Scripts\python -m pip install --upgrade pip --quiet
venv\Scripts\python -m pip install -r requirements.txt
if errorlevel 1 (
  echo Install failed - check your internet connection and run me again.
  echo ההתקנה נכשלה - בדקו חיבור לאינטרנט והריצו שוב.
  pause
  exit /b 1
)

echo.
echo Done! Double-click RUN.cmd to start.
echo סיימנו! לחיצה כפולה על RUN.cmd מפעילה את האפליקציה.
echo NOTE: the FIRST run downloads the recognition model ^(~1.5 GB, once^).
echo שימו לב: ההרצה הראשונה מורידה את מודל הזיהוי ^(~1.5GB, פעם אחת^).
echo.
pause
