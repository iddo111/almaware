@echo off
REM Rebuild the ALMA-OS host simulator (his real firmware + virtual T-Deck).
REM לזכרה של עלמה ז"ל - ALMAWARE
setlocal
set PATH=C:\msys64\usr\bin;%PATH%
cd /d "%~dp0\.."
echo Building alma_sim.exe ...
g++ -std=c++17 -O1 -Wall -I sim/host -o sim/alma_sim.exe ^
  sim/host/alma_sim.cpp sim/host/sim_hw.cpp ^
  src/main.cpp src/display_st7789.cpp src/radio_sx1262.cpp -pthread
if errorlevel 1 (echo BUILD FAILED & pause & exit /b 1)
echo OK - sim\alma_sim.exe
endlocal
