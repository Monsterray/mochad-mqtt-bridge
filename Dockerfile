FROM python:3.12-alpine

ARG BUILD_DATE
ARG VCS_REF
ARG IMAGE_VERSION=0.1.0

LABEL org.opencontainers.image.title="mochad-mqtt-bridge"
LABEL org.opencontainers.image.description="MQTT bridge for a running mochad X10 TCP service"
LABEL org.opencontainers.image.version="${IMAGE_VERSION}"
LABEL org.opencontainers.image.created="${BUILD_DATE}"
LABEL org.opencontainers.image.revision="${VCS_REF}"
LABEL org.opencontainers.image.vendor="MQTT Mochad Bridge contributors"
LABEL org.opencontainers.image.source="https://github.com/Monsterray/mochad-mqtt-bridge"
LABEL org.opencontainers.image.documentation="https://github.com/Monsterray/mochad-mqtt-bridge"
LABEL org.opencontainers.image.licenses="MIT"

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN addgroup -S bridge \
    && adduser -S -G bridge bridge \
    && mkdir -p /config \
    && chown -R bridge:bridge /config

COPY requirements.txt .
RUN pip install --no-cache-dir --no-compile -r requirements.txt

COPY --chown=bridge:bridge . .

ENV MOCHAD_HOST=mochad
ENV MOCHAD_PORT=1099
ENV MQTT_HOST=mosquitto
ENV MQTT_PORT=1883
ENV MQTT_BASE_TOPIC=x10
ENV DISCOVERY_CLEANUP=false
ENV DISCOVERY_REGISTRY_PATH=/config/discovery_registry.json
ENV ENABLE_MAINTENANCE_BUTTONS=false
ENV BRIDGE_HEALTH_FILE=/tmp/mqtt-mochad-bridge.health
ENV BRIDGE_HEALTH_MAX_AGE_SECONDS=30
ENV BRIDGE_DEBUG_WIRE=false

VOLUME ["/config"]

USER bridge

HEALTHCHECK --interval=30s \
            --timeout=5s \
            --start-period=20s \
            --retries=3 \
CMD python /app/healthcheck.py || exit 1

CMD ["python", "mqtt_mochad_bridge.py"]
