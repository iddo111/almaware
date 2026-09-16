import subprocess, time, os, sys
ROOT = r"D:\CLAUDE\alma-os-tdeck"
env = dict(os.environ)
env["PATH"] = r"C:\msys64\usr\bin;" + env.get("PATH", "")
p = subprocess.Popen([ROOT + r"\sim\alma_sim.exe", ROOT + r"\sim"],
                     stdin=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env, cwd=ROOT)
def send(s):
    p.stdin.write((s + "\n").encode("utf-8")); p.stdin.flush()
def keys(txt):
    for ch in txt:
        send("K %d" % ord(ch)); time.sleep(0.06)

time.sleep(2.7)                       # his setup(): 500 ms rail + 1500 ms splash
keys("akuo"); time.sleep(0.3); send("K 13"); time.sleep(0.5)      # שלום + Enter
keys("?gzrv"); time.sleep(0.3); send("K 13"); time.sleep(0.6)     # ?עזרה + Enter
send("RX " + "שלום מהצד השני"); time.sleep(1.0)                    # another node
send("SHOT " + ROOT + r"\sim\shot_chat.bmp"); time.sleep(0.6)
send("TB R"); time.sleep(1.0)                                      # trackball -> מערכת
send("SHOT " + ROOT + r"\sim\shot_about.bmp"); time.sleep(0.6)
send("QUIT"); time.sleep(0.4)
try: p.kill()
except Exception: pass
