@echo off
rem ERAN articulatory avatar -- desktop demo window.
rem --xr-mode off: with SteamVR's OpenXR runtime installed and no headset, Godot's OpenXR
rem module blocks at startup for minutes (measured 2026-09-09). Off = a plain desktop window.
rem Keys: 1=ba 2=ma 3=sha  Space=replay  B=A/B ba<->ma  Esc=quit
set GODOT=C:\Tools\Godot\4.6.3-stable\Godot_v4.6.3-stable_win64.exe
start "" "%GODOT%" --path "%~dp0." --xr-mode off --resolution 1280x720
