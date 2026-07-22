# Beta Status

MQTT Mochad Bridge 0.4.0 is a local MQTT beta for a running mochad main listener
on port 1099. It can publish address-based X10 state/events and optional Home
Assistant MQTT Discovery.

Use a tagged beta image or exact full Git SHA. Do not report results from
develop, master, or another moving branch.

| Area | Status | Notes |
| --- | --- | --- |
| Python compilation, version contract, and deterministic pytest suite | PASS | Pull-request CI runs the supported Python matrix; use the check attached to the tested SHA for the exact test count. |
| Shell safety | PASS | Pull-request CI checks every tracked shell script at warning severity. |
| Docker runtime, Mosquitto, fake-mochad, reconnect, and Home Assistant discovery integration | NOT RUN | Not established by source-only checks; consult the dedicated integration and container checks attached to the tested SHA. |
| Physical CM19A/CM15A delivery and SC546A chime result | HARDWARE REQUIRED | A software transmission is not physical confirmation; human observation is required. |

Do not use the bridge against a public MQTT broker or expose Home Assistant
discovery unintentionally. Disable discovery and use a unique test base topic
for isolated testing.
