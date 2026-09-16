"""
LoRa Mesh ⇄ MQTT bridge over USB serial.

Usage:
    .venv\\Scripts\\python.exe usb_bridge.py [COM_PORT] [MQTT_HOST] [MQTT_PORT]

Default: COM5, localhost, 1883.

MQTT topic conventions (custom — easy to read, easy to publish to):

  RECEIVE FROM MESH (we publish to MQTT):
    lora/rx/<from-id>/<to-id>           JSON body for every received text packet
    lora/event/<from-id>                JSON for every NodeInfo / Position / etc.
    lora/status                         retained: bridge connection state

  SEND TO MESH (you publish, we forward to LoRa):
    lora/tx/broadcast                   payload = text, sent to ^all
    lora/tx/<dest-node-id>              payload = text, sent direct to that node
                                        e.g. lora/tx/!f6708e90 = DM to node 8e90

The bridge is bidirectional: text sent into MQTT goes out the LoRa radio,
and every text/event coming off the LoRa radio appears on MQTT.
"""
from __future__ import annotations
import io
import json
import sys
import time
import signal
from typing import Any

# Force UTF-8 on Windows console so unicode arrows / Hebrew don't crash print()
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)

import meshtastic.serial_interface
from pubsub import pub
import paho.mqtt.client as mqtt


PORT      = sys.argv[1] if len(sys.argv) > 1 else "COM5"
MQTT_HOST = sys.argv[2] if len(sys.argv) > 2 else "localhost"
MQTT_PORT = int(sys.argv[3]) if len(sys.argv) > 3 else 1883

interface: Any = None
mq = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"lora-bridge-{PORT}")


def log(*a):
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}]", *a, flush=True)


# ── MQTT → Mesh ─────────────────────────────────────────────────────────────
def on_mqtt_connect(client, userdata, flags, rc, props=None):
    log(f"MQTT connected → {MQTT_HOST}:{MQTT_PORT}  rc={rc}")
    client.subscribe("lora/tx/+")
    client.publish("lora/status",
                   json.dumps({"bridge": True, "port": PORT, "ts": int(time.time())}),
                   retain=True)


def on_mqtt_message(client, userdata, msg):
    global interface
    parts = msg.topic.split("/")
    if len(parts) < 3 or parts[0] != "lora" or parts[1] != "tx":
        return
    dest = parts[2]
    text = msg.payload.decode("utf-8", errors="replace")
    if interface is None:
        log(f"[TX-DROP] mesh not ready: {dest} ← {text!r}")
        return
    try:
        if dest in ("broadcast", "all", "^all"):
            interface.sendText(text)
            log(f"[TX] broadcast: {text!r}")
        else:
            interface.sendText(text, destinationId=dest)
            log(f"[TX] → {dest}: {text!r}")
    except Exception as e:
        log(f"[TX-ERR] {dest}: {e}")


# ── Mesh → MQTT ─────────────────────────────────────────────────────────────
def _safe(v):
    """Make any value JSON-serialisable."""
    try:
        json.dumps(v)
        return v
    except Exception:
        return repr(v)


def on_mesh_receive(packet, interface):
    try:
        decoded = packet.get("decoded", {}) or {}
        portnum = decoded.get("portnum", "")
        from_id = packet.get("fromId", "?")
        to_id   = packet.get("toId",   "?")

        body = {
            "from":     from_id,
            "to":       to_id,
            "portnum":  portnum,
            "rssi":     packet.get("rxRssi", 0),
            "snr":      packet.get("rxSnr", 0),
            "hop":      packet.get("hopLimit", 0),
            "ts":       packet.get("rxTime", int(time.time())),
            "channel":  packet.get("channel", 0),
        }

        # Add payload-specific fields
        if portnum in ("TEXT_MESSAGE_APP", "RANGE_TEST_APP"):
            body["text"] = decoded.get("text", "")
            body["kind"] = "text" if portnum == "TEXT_MESSAGE_APP" else "rangetest"
            topic = f"lora/rx/{from_id}/{to_id}"
            log(f"[RX:{body['kind']}] {from_id} → {to_id}: {body['text']!r}")
        else:
            body["data"] = {k: _safe(v) for k, v in decoded.items() if k != "payload"}
            topic = f"lora/event/{from_id}"
            log(f"[EVT] {from_id} {portnum}")

        mq.publish(topic, json.dumps(body, ensure_ascii=False), retain=False)
    except Exception as e:
        log(f"on_mesh_receive error: {e}")


def on_mesh_connect(interface, topic=pub.AUTO_TOPIC):
    info = interface.getMyNodeInfo() or {}
    user = info.get("user", {})
    log(f"MESH connected: {user.get('longName','?')} ({user.get('id','?')})  "
        f"hw={user.get('hwModel','?')}")
    mq.publish("lora/status",
               json.dumps({"bridge": True, "port": PORT,
                           "node": user.get("id"),
                           "name": user.get("longName"),
                           "ts": int(time.time())}),
               retain=True)


def on_mesh_lost(interface, topic=pub.AUTO_TOPIC):
    log("MESH connection lost")
    mq.publish("lora/status",
               json.dumps({"bridge": False, "port": PORT, "ts": int(time.time())}),
               retain=True)


# ── Wire it up ──────────────────────────────────────────────────────────────
pub.subscribe(on_mesh_receive, "meshtastic.receive")
pub.subscribe(on_mesh_connect, "meshtastic.connection.established")
pub.subscribe(on_mesh_lost,    "meshtastic.connection.lost")

mq.on_connect = on_mqtt_connect
mq.on_message = on_mqtt_message

log(f"Connecting to MQTT broker at {MQTT_HOST}:{MQTT_PORT} …")
mq.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
mq.loop_start()

log(f"Opening mesh on {PORT} …")
interface = meshtastic.serial_interface.SerialInterface(devPath=PORT)


def shutdown(*_):
    log("Shutting down…")
    try:
        mq.publish("lora/status",
                   json.dumps({"bridge": False, "port": PORT, "ts": int(time.time())}),
                   retain=True)
        mq.loop_stop()
        mq.disconnect()
    except Exception:
        pass
    try:
        if interface:
            interface.close()
    except Exception:
        pass
    sys.exit(0)


signal.signal(signal.SIGINT, shutdown)
signal.signal(signal.SIGTERM, shutdown)

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    shutdown()
