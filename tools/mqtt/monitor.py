"""Quick MQTT subscriber for verifying the bridge.

Usage:
    .venv\\Scripts\\python.exe monitor.py [HOST]
"""
import sys
import time
import json
import paho.mqtt.client as mqtt

HOST = sys.argv[1] if len(sys.argv) > 1 else "localhost"


def on_connect(client, userdata, flags, rc, props=None):
    print(f"[{time.strftime('%H:%M:%S')}] connected to {HOST}:1883  rc={rc}")
    client.subscribe("lora/#")
    client.subscribe("$SYS/broker/clients/connected")


def on_message(c, u, m):
    ts = time.strftime("%H:%M:%S")
    try:
        body = json.loads(m.payload.decode("utf-8", errors="replace"))
        text = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
    except Exception:
        text = m.payload.decode("utf-8", errors="replace")
    print(f"[{ts}] {m.topic}  {text}")


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"monitor-{int(time.time())}")
client.on_connect = on_connect
client.on_message = on_message
client.connect(HOST, 1883, 60)
client.loop_forever()
