@echo off
REM ============================================================
REM  start_opengrok.cmd — Launch Tomcat + open OpenGrok browser
REM  Part of Iddo Perez's local code-search stack
REM  iddoperez.ai
REM ============================================================

setlocal

REM --- Paths (adjust JAVA_HOME if you used a portable JDK install) ---
set "OPENGROK_HOME=D:\CLAUDE\tools\opengrok"
set "TOMCAT_HOME=%OPENGROK_HOME%\tomcat"
set "OPENGROK_URL=http://localhost:8088/source/"

REM --- Auto-detect JAVA_HOME if not set ---
if "%JAVA_HOME%"=="" (
    REM Try the default Oracle JDK 21 install location
    if exist "C:\Program Files\Java\jdk-21" (
        set "JAVA_HOME=C:\Program Files\Java\jdk-21"
    ) else if exist "D:\CLAUDE\tools\jdk21\jdk-21" (
        set "JAVA_HOME=D:\CLAUDE\tools\jdk21\jdk-21"
    ) else (
        echo ERROR: JAVA_HOME is not set and Java was not found at default locations.
        echo Please install JDK 21 (see INSTALL.md Step 1) and re-run.
        pause
        exit /b 1
    )
)

set "PATH=%JAVA_HOME%\bin;%PATH%"

REM --- Verify java is reachable ---
java -version >nul 2>&1
if errorlevel 1 (
    echo ERROR: java.exe not found. Check JAVA_HOME or PATH.
    pause
    exit /b 1
)

REM --- Check if Tomcat is already running ---
for /f "tokens=5" %%a in ('netstat -an ^| findstr ":8088 "') do (
    if "%%a"=="LISTENING" (
        echo Tomcat already running on port 8088.
        goto open_browser
    )
)

REM --- Start Tomcat ---
echo Starting Tomcat on port 8088...
set "CATALINA_HOME=%TOMCAT_HOME%"
call "%TOMCAT_HOME%\bin\startup.bat"

REM --- Wait for Tomcat to be ready (up to 30 seconds) ---
echo Waiting for Tomcat to initialize...
set /a attempts=0
:wait_loop
    timeout /t 2 /nobreak >nul
    set /a attempts+=1
    for /f "tokens=5" %%a in ('netstat -an 2^>nul ^| findstr ":8088 "') do (
        if "%%a"=="LISTENING" goto tomcat_ready
    )
    if %attempts% lss 15 goto wait_loop
    echo WARNING: Tomcat did not respond in 30 seconds. Opening browser anyway...
    goto open_browser

:tomcat_ready
echo Tomcat is ready.

:open_browser
echo Opening %OPENGROK_URL% ...
start "" "%OPENGROK_URL%"

echo.
echo OpenGrok is running at: %OPENGROK_URL%
echo To stop Tomcat, run: %TOMCAT_HOME%\bin\shutdown.bat
echo To reindex, run: powershell -File "%OPENGROK_HOME%\reindex.ps1"
echo.

endlocal
