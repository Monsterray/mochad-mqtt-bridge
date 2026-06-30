#!/usr/bin/env python3

import os
import re
import time
import signal
import socket
import logging
import threading
from typing import Dict, Optional

import paho.mqtt.client as mqtt

# =========================
# ENV CONFIG
# =========================

MOCHAD_HOST = os.getenv("MOCHAD_HOST", "mochad")
MOCHAD_PORT = int(os.getenv("MOCHAD_PORT", "1099"))

MQTT_HOST = os.getenv("MQTT_HOST", "mosquitto")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USERNAME")
MQTT_PASS = os.getenv("MQTT_PASSWORD")

MQTT_BASE = os.getenv("MQTT_BASE_TOPIC", "x10")

DEVICE_MAP_RAW = os.getenv("X10_DEVICES", "")

STATUS_TOPIC = f"{MQTT_BASE}/bridge/status"

# =========================
# LOGGING
# =========================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("mochad-bridge")

# =========================
# GLOBALS
# =========================

running = True
mqttc: mqtt.Client = None
sock: Optional[socket.socket] = None
sock_lock = threading.Lock()

device_map: Dict[str, str] = {}  # A1 -> friendly name

# =========================
# DEVICE NAME PARSING
# =========================

def parse_device_map():
    global device_map

    if not DEVICE_MAP_RAW:
        return

    for entry in DEVICE_MAP_RAW.split(","):
        entry = entry.strip()
        if ":" in entry:
            dev, name = entry.split(":", 1)
            device_map[dev.strip().upper()] = name.strip()


def device_name(dev: str) -> str:
    return device_map.get(dev, dev.lower())

# =========================
# MQTT TOPICS
# =========================

# Deprecated legacy topic. Active bridge code uses x10/<device>/command.
def topic_set(dev): return f"{MQTT_BASE}/{dev}/set"
def topic_state(dev): return f"{MQTT_BASE}/{dev}/state"
def topic_event(dev): return f"{MQTT_BASE}/{dev}/event"
def topic_discovery(dev): return f"homeassistant/switch/x10_{dev}/config"

# =========================
# MOCHAD PARSING
# =========================

RX_TX_RE = re.compile(
    r"(Tx|Rx)\s+RF\s+(HouseUnit|House):\s*([A-P])(\d*)\s*Func:\s*(On|Off|Dim|Bright)",
    re.IGNORECASE,
)

def parse_line(line: str):
    m = RX_TX_RE.search(line)
    if not m:
        return None

    direction = m.group(1).lower()
    kind = m.group(2).lower()
    house = m.group(3).upper()
    unit = m.group(4)
    func = m.group(5).upper()

    dev = f"{house}{unit}" if unit else house

    return direction, kind, dev, func


# =========================
# MOCHAD CONNECTION
# =========================

def connect_mochad():
    global sock

    s = socket.create_connection((MOCHAD_HOST, MOCHAD_PORT))
    s.settimeout(None)

    with sock_lock:
        sock = s

    log.info("Connected to mochad")

def send_mochad(cmd: str):
    with sock_lock:
        if not sock:
            return
        sock.sendall((cmd + "\n").encode())

# =========================
# MQTT
# =========================

def mqtt_on_connect(client, userdata, flags, rc, props):
    log.info("MQTT connected")

    # Deprecated legacy subscription. Active bridge code subscribes to
    # x10/+/command.
    client.subscribe(f"{MQTT_BASE}/+/set")

    client.publish(STATUS_TOPIC, "online", retain=True)

def mqtt_on_message(client, userdata, msg):
    dev = msg.topic.split("/")[1].upper()
    payload = msg.payload.decode().upper().strip()

    if payload == "ON":
        cmd = f"rf {dev} on"
    elif payload == "OFF":
        cmd = f"rf {dev} off"
    elif payload == "DIM":
        cmd = f"rf {dev} dim"
    elif payload == "BRIGHT":
        cmd = f"rf {dev} bright"
    else:
        return

    send_mochad(cmd)

# =========================
# HOME ASSISTANT DISCOVERY
# =========================

def publish_discovery(dev: str):
    name = device_name(dev)

    payload = {
        "name": name,
        "unique_id": f"x10_{dev}",
        "command_topic": topic_set(dev),
        "state_topic": topic_state(dev),
        "availability_topic": STATUS_TOPIC,
        "payload_on": "ON",
        "payload_off": "OFF",
    }

    mqttc.publish(topic_discovery(dev), str(payload), retain=True)

# =========================
# STATE HANDLING
# =========================

def publish_state(dev: str, state: str):
    mqttc.publish(topic_state(dev), state, retain=True)

def publish_event(dev: str, direction: str, func: str):
    mqttc.publish(
        topic_event(dev),
        f"{direction}:{func}",
        retain=False,
    )

# =========================
# ST STATUS PARSER
# =========================

def parse_status(line: str):
    # House A: 1=1,2=0,3=1
    if "House" not in line or "=" not in line:
        return None

    m = re.search(r"House\s+([A-P]):\s*(.*)", line)
    if not m:
        return None

    house = m.group(1).upper()
    entries = m.group(2)

    for item in entries.split(","):
        if "=" not in item:
            continue
        unit, state = item.split("=")
        dev = f"{house}{unit}"
        yield dev, "ON" if state == "1" else "OFF"

# =========================
# READER THREAD
# =========================

def mochad_loop():
    while running:
        try:
            connect_mochad()
            buffer = ""

            with sock_lock:
                s = sock

            while running:
                data = s.recv(4096).decode(errors="ignore")
                if not data:
                    break

                buffer += data

                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)

                    parsed = parse_line(line)
                    if parsed:
                        direction, kind, dev, func = parsed

                        if dev not in device_map:
                            publish_discovery(dev)

                        publish_event(dev, direction, func)

                        if direction == "tx":
                            publish_state(dev, func)

                    # STATUS parsing (st output)
                    for result in parse_status(line) or []:
                        dev, state = result
                        publish_state(dev, state)

        except Exception as e:
            log.error("mochad error: %s", e)
            time.sleep(5)

# =========================
# SHUTDOWN
# =========================

def shutdown(sig, frame):
    global running
    running = False
    log.info("Shutting down...")

# =========================
# MAIN
# =========================

def main():
    global mqttc

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    parse_device_map()

    mqttc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

    if MQTT_USER:
        mqttc.username_pw_set(MQTT_USER, MQTT_PASS)

    mqttc.will_set(STATUS_TOPIC, "offline", retain=True)

    mqttc.on_connect = mqtt_on_connect
    mqttc.on_message = mqtt_on_message

    mqttc.connect(MQTT_HOST, MQTT_PORT, 60)
    mqttc.loop_start()

    t = threading.Thread(target=mochad_loop, daemon=True)
    t.start()

    while running:
        time.sleep(1)

    mqttc.publish(STATUS_TOPIC, "offline", retain=True)
    mqttc.loop_stop()

if __name__ == "__main__":
    main()
