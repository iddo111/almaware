@echo off
rem ALMA-RECALL MCP server (streamable HTTP for the DGX fleet, port 8795)
rem Manual start / debug. Silent autostart lives in the Startup folder:
rem   ALMA-Recall-MCP.vbs
cd /d D:\CLAUDE\alma-recall
python recall_mcp.py http --port 8795
