# Proves the whole browser path: HTTP /cmd -> sim stdin -> his firmware -> panel.
import urllib.request, urllib.parse, json, time, hashlib
B = "http://127.0.0.1:8864"
def cmd(c): urllib.request.urlopen(B + "/cmd?c=" + urllib.parse.quote(c), timeout=5).read()
def frame(): return urllib.request.urlopen(B + "/frame.bmp?t=%f" % time.time(), timeout=5).read()
def status(): return json.loads(urllib.request.urlopen(B + "/status?t=%f" % time.time(), timeout=5).read())
def wait_status(pred, secs=3.0):
    t = time.time()
    while time.time() - t < secs:
        s = status()
        if pred(s): return s
        time.sleep(0.15)
    return status()

t0=time.time(); u0=status()["uptime_ms"]; time.sleep(2.0)
print("clock: wall %.2fs vs firmware millis() %.2fs" % (time.time()-t0, (status()["uptime_ms"]-u0)/1000.0))

cmd("K 32"); time.sleep(0.5); cmd("K 8"); time.sleep(0.5)      # wake + clear
before = hashlib.md5(frame()).hexdigest()
for ch in "akuo": cmd("K %d" % ord(ch)); time.sleep(0.10)
time.sleep(0.5); mid = hashlib.md5(frame()).hexdigest()
tx0 = status()["tx_count"]
cmd("K 13"); time.sleep(0.9); after = hashlib.md5(frame()).hexdigest()
s = wait_status(lambda x: x["tx_count"] > tx0)
print("frame changed while typing שלום :", before != mid)
print("frame changed on Enter          :", mid != after)
print("tx_count %d -> %d" % (tx0, s["tx_count"]))
print("last_tx_text                    :", s["last_tx_text"])
print("last_tx_hex                     :", s["last_tx_hex"])

cmd("RADIO 0"); s = wait_status(lambda x: x["radio_present"] is False)
print("RADIO 0 -> radio_present =", s["radio_present"])
cmd("RADIO 1"); s = wait_status(lambda x: x["radio_present"] is True)
print("RADIO 1 -> radio_present =", s["radio_present"])

cmd("RX " + "בדיקה מהדפדפן"); time.sleep(1.2)
print("serial tail                     :", status()["serial"].strip().splitlines()[-1])
