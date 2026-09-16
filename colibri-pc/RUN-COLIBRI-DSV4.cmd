@echo off
rem Colibri / DeepSeek-V4-Flash-REAP-150b, OpenAI-compatible server on 127.0.0.1:8901.
rem CPU-only on this box (RTX 3070 Ti VRAM is permanently held by the KESHEV mic decoder --
rem treated as unavailable, never touched). BelowNormal priority + 4-thread cap so the mic
rem and other live sessions are never starved. Mic pids (1436/6980/7580/12904/10712 and
rem friends) are NEVER touched by this script.
rem
rem --ram/--cap are set from REAL MEASUREMENT on this box (2026-09-09), not guessed:
rem   coli doctor at --ram 8 FAILED outright (needs dense 8.8GB + runtime 5.9GB = 14.7GB
rem   minimum just to hold the model with ZERO expert cache).
rem   A live run at --ram 15 (dense held RESIDENT) CRASHED (exit -1, Windows WER
rem   RADAR_PRE_LEAK on deepseek_v4.exe) after free RAM hit ~3.6GB -- too tight on a
rem   box whose free RAM floats 11-18GB with the mic + other live sessions competing.
rem   A live run at --ram 10 --cap 0 (dense STREAMED, not resident) SUCCEEDED clean:
rem   real answer, hit_rate 43.7%%, RAM stayed near 8-8.5GB available throughout.
rem   --ram 10 --cap 0 is therefore the validated-safe config on THIS box. Do not raise
rem   --ram past (free_RAM_GB - 8) without a fresh `Get-CimInstance Win32_OperatingSystem`
rem   check -- this machine's free RAM is volatile (11-18 GB observed in one evening).

setlocal
set MODEL=C:\models\colibri\DeepSeek-V4-Flash-reap-150b
set PORT=8901
set RAM_GB=10
set CAP=0
set CTX=1024
set OMP_NUM_THREADS=4
set COLI_NO_OMP_TUNE=

cd /d D:\CLAUDE\colibri-pc\release

echo Starting Colibri DeepSeek-V4-Flash-REAP-150b server on 127.0.0.1:%PORT% (BelowNormal, %OMP_NUM_THREADS% threads, --ram %RAM_GB% --cap %CAP%)...
echo WARNING: measured decode speed on this box is ~0.06-0.08 tok/s (minutes per token).
echo This is NOT usable as an interactive coding assistant -- see D:\CLAUDE\colibri-pc\ logs.
start "colibri-dsv4-serve" /belownormal /min coli.cmd serve --model "%MODEL%" --host 127.0.0.1 --port %PORT% --ram %RAM_GB% --cap %CAP% --ctx %CTX%

echo Launched. Check with:
echo   Invoke-RestMethod http://127.0.0.1:%PORT%/v1/models
echo Stop with:
echo   coli.cmd stop --port %PORT%
endlocal
