"""federation_boot.py — start the ALMA/Eran Federation (coordinator + worker) detached.
Launched at login by the 'ALMA-Federation' scheduled task (non-elevated, windowless).
Iddo's PC is node #0 (tester-0). לע"נ עלמה ז"ל.
"""
import os, sys, subprocess, time

HERE = os.path.dirname(os.path.abspath(__file__))
NOWIN = 0x08000000  # CREATE_NO_WINDOW

tokf = os.path.join(HERE, ".alma_token")
if not os.path.exists(tokf):
    import secrets
    open(tokf, "w").write(secrets.token_hex(16))
tok = open(tokf).read().strip()

py = sys.executable  # pythonw.exe when launched windowless

# coordinator (localhost only, real token)
cenv = dict(os.environ, ALMA_TOKEN=tok, ALMA_BIND="127.0.0.1", ALMA_PORT="8950")
subprocess.Popen([py, "coordinator.py"], cwd=HERE, env=cenv, creationflags=NOWIN)

time.sleep(3)  # let the coordinator bind before the worker registers

# worker — this PC as node "iddo-pc" (tester-0)
wenv = dict(cenv, ALMA_COORD="http://127.0.0.1:8950", ALMA_WORKER="iddo-pc", ALMA_POLL="2")
subprocess.Popen([py, "worker.py"], cwd=HERE, env=wenv, creationflags=NOWIN)
