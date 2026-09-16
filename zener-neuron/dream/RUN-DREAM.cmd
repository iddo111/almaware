@echo off
rem DREAM BOARD - הלוח החולם - 127.0.0.1:8864 (port claimed in RAMCHAT 2026-09-10)
rem BELOW_NORMAL so KESHEV's mic is never starved. No training here: weights are prescribed.
set PYTHONIOENCODING=utf-8
set OMP_NUM_THREADS=2
cd /d %~dp0
start "DREAM BOARD :8864" /belownormal python dream_board.py %*
timeout /t 2 >nul
start http://127.0.0.1:8864/
