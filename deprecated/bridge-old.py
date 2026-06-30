import os
import socket
import time
import json
import paho.mqtt.client as mqtt

MOCHAD_HOST = os.getenv("MOCHAD_HOST", "mochad")
MOCHAD_PORT = int(os.getenv("MOCHAD_PORT", "1099"))

MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "mochad/rf")

DEDUPE_WINDOW_SEC = 0.5

last_event = {}


def parse_mochad_line(line: str):
    """
    Example mochad output:
    RF HouseUnit: A1 Func: On
    or raw RF decode lines depending on mode.
    """
    line = line.strip()

    if not line:
        return None

    # Try structured format first
    if "HouseUnit" in line:
        parts = line.split()
        try:
            house = parts[1]
            func = parts[3]
            return {
                "type": "command",
                "house": house,
                "command": func,
                "raw": line
            }
        except Exception:
            return {"type": "unknown", "raw": line}

    # fallback raw
    return {"type": "raw", "raw": line}


def should_dedupe(event_key):
    now = time.time()
    last = last_event.get(event_key, 0)

    if now - last < DEDUPE_WINDOW_SEC:
        return True

    last_event[event_key] = now
    return False


def mqtt_connect():
    client = mqtt.Client()
    client.connect(MQTT_HOST, MQTT_PORT, 60)
    client.loop_start()
    return client


def connect_mochad():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((MOCHAD_HOST, MOCHAD_PORT))
    s.settimeout(None)
    return s


def main():
    print(f"[INFO] Connecting to mochad at {MOCHAD_HOST}:{MOCHAD_PORT}")
    print(f"[INFO] Connecting to MQTT at {MQTT_HOST}:{MQTT_PORT}")

    mqtt_client = mqtt_connect()

    while True:
        try:
            sock = connect_mochad()
            print("[INFO] Connected to mochad")

            buffer = ""

            while True:
                data = sock.recv(1024).decode(errors="ignore")
                if not data:
                    break

                buffer += data

                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)

                    event = parse_mochad_line(line)
                    if not event:
                        continue

                    # create dedupe key
                    key = json.dumps(event, sort_keys=True)
                    if should_dedupe(key):
                        continue

                    topic = MQTT_TOPIC + "/" + event["type"]

                    mqtt_client.publish(topic, json.dumps(event))

                    print(f"[MQTT] {topic} -> {event}")

        except Exception as e:
            print(f"[ERROR] {e}")
            time.sleep(3)


if __name__ == "__main__":
    main()
