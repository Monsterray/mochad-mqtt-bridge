FROM python:3.12-alpine

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --no-compile -r requirements.txt

COPY . .

ENV MOCHAD_HOST=mochad
ENV MOCHAD_PORT=1099
ENV MQTT_HOST=mosquitto
ENV MQTT_PORT=1883
ENV MQTT_BASE_TOPIC=x10
ENV BRIDGE_HEALTH_FILE=/tmp/mqtt-mochad-bridge.health
ENV BRIDGE_HEALTH_MAX_AGE_SECONDS=30
ENV BRIDGE_DEBUG_WIRE=false

HEALTHCHECK --interval=30s \
            --timeout=5s \
            --start-period=20s \
            --retries=3 \
CMD python /app/healthcheck.py || exit 1

CMD ["python", "mqtt_mochad_bridge.py"]
