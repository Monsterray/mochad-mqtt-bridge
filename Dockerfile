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

RUN apk add --no-cache \
    su-exec \
    tini \
    tzdata \
    && mkdir -p /config

COPY requirements.txt .
RUN pip install --no-cache-dir --no-compile -r requirements.txt

COPY . .
RUN chown -R root:root /app \
    && chmod -R go-w /app \
    && rm -f /sbin/apk /usr/bin/wget /bin/wget

ENV PUID=911
ENV PGID=911
ENV TZ=UTC
ENV UMASK=022
ENV MOCHAD_HOST=mochad
ENV MOCHAD_PORT=1099
ENV MQTT_HOST=mosquitto
ENV MQTT_PORT=1883
ENV MQTT_PASSWORD_FILE=
ENV MQTT_TLS_ENABLED=false
ENV MQTT_TLS_CA_FILE=
ENV MQTT_TLS_CERT_FILE=
ENV MQTT_TLS_KEY_FILE=
ENV MQTT_TLS_KEY_PASSWORD=
ENV MQTT_TLS_KEY_PASSWORD_FILE=
ENV MQTT_BASE_TOPIC=x10
ENV DISCOVERY_CLEANUP=false
ENV DISCOVERY_REGISTRY_PATH=/config/discovery_registry.json
ENV BRIDGE_CONFIG_FILE=/config/bridge.json
ENV ENABLE_MAINTENANCE_BUTTONS=false
ENV BRIDGE_HEALTH_FILE=/config/mqtt-mochad-bridge.health
ENV BRIDGE_HEALTH_MAX_AGE_SECONDS=30
ENV BRIDGE_DEBUG_WIRE=false

VOLUME ["/config"]

COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chown root:root /app/docker-entrypoint.sh \
    && chmod 755 /app/docker-entrypoint.sh

HEALTHCHECK --interval=30s \
            --timeout=5s \
            --start-period=20s \
            --retries=3 \
CMD python /app/healthcheck.py || exit 1

ENTRYPOINT ["/sbin/tini","--","/app/docker-entrypoint.sh"]
CMD ["python", "mqtt_mochad_bridge.py"]
