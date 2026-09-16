@echo off
title Claude - Grok Relay
cd /d D:\CLAUDE\tools\grok-relay
echo Grok-Relay watcher starting
echo Watches: D:\grok\OUTBOX D:\grok\INBOX  C:\Users\<user>\.grok\logs\unified.jsonl
echo Writes:  D:\CLAUDE\tools\clod-bridge\state\grok-recent.jsonl
echo Writes:  C:\Users\<user>\.claude\projects\D--CLAUDE\memory\grok-recent.md
python grok-relay.py
