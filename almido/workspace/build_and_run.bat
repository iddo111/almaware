@echo off
call "C:\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul
cd /d D:\CLAUDE\almido\workspace
cl compile_test.c /Fe:compile_test.exe
compile_test.exe
