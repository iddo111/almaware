@echo off
REM לזכרה של עלמה ז״ל
REM Qwen Code CLI driven by OUR Qwen3-Coder-480B across eran1+eran2+eran3.
REM
REM This is the path that actually has hands. The web chat at :8080 sends no
REM tools, so the model can only ever hand you code to paste. The CLI passes a
REM real tool surface — read, write, shell — and executes what the model calls.
title QWEN 480B CLI
cd /d D:\CLAUDE
echo.
echo   Qwen3-Coder-480B  ^|  eran1 + eran2 + eran3  ^|  ~8 tok/s
echo   cwd: %CD%
echo.
echo   It is slow on purpose: 480B split over three boxes. Ask it hard things,
echo   not quick ones. gpt-oss on eran4 is 6x faster for small questions.
echo.
qwen -m qwen3-coder-480b %*
