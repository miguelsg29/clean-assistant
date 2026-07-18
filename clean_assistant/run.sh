#!/bin/sh
# Lee la configuración del formulario de Home Assistant y lanza Clean Assistant.
CONFIG="/data/options.json"

export CONGA_MODE=real
export ROBOT_DID=$(jq -r '.ROBOT_DID // 0' $CONFIG)
export ROBOT_USERID=$(jq -r '.ROBOT_USERID // 0' $CONFIG)
export ROBOT_SN=$(jq -r '.ROBOT_SN // ""' $CONFIG)
export ROBOT_MAC=$(jq -r '.ROBOT_MAC // ""' $CONFIG)
export FACTORY_ID=$(jq -r '.FACTORY_ID // "1003"' $CONFIG)
export PROJECT_TYPE=$(jq -r '.PROJECT_TYPE // "CECOTECCRL350-1001"' $CONFIG)
export AUTH_JWT=$(jq -r '.AUTH_JWT // ""' $CONFIG)
export MQTT_HOST=$(jq -r '.MQTT_HOST // ""' $CONFIG)
export MQTT_PORT=$(jq -r '.MQTT_PORT // 1883' $CONFIG)
export MQTT_USER=$(jq -r '.MQTT_USER // ""' $CONFIG)
export MQTT_PASS=$(jq -r '.MQTT_PASS // ""' $CONFIG)

# Autoconfiguración de MQTT desde Home Assistant: si no has puesto el broker a mano,
# el Supervisor nos da host/puerto/usuario/contraseña del add-on de Mosquitto (u otro
# broker configurado en HA) sin tener que escribir nada. Requiere "services: mqtt:want".
if [ -z "$MQTT_HOST" ] && [ -n "$SUPERVISOR_TOKEN" ]; then
    MQTT_SVC=$(curl -s -w "\n%{http_code}" -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" http://supervisor/services/mqtt)
    HTTP_CODE=$(echo "$MQTT_SVC" | tail -n1)
    BODY=$(echo "$MQTT_SVC" | sed '$d')
    if [ "$(echo "$BODY" | jq -r '.result // ""')" = "ok" ]; then
        export MQTT_HOST=$(echo "$BODY" | jq -r '.data.host // ""')
        export MQTT_PORT=$(echo "$BODY" | jq -r '.data.port // 1883')
        export MQTT_USER=$(echo "$BODY" | jq -r '.data.username // ""')
        export MQTT_PASS=$(echo "$BODY" | jq -r '.data.password // ""')
        echo "[INFO] MQTT autoconfigurado desde Home Assistant: ${MQTT_HOST}:${MQTT_PORT}"
    else
        echo "[INFO] MQTT: Home Assistant no devolvió broker (http ${HTTP_CODE}). ¿Tienes el"
        echo "       add-on 'Mosquitto broker' instalado? Respuesta: $(echo "$BODY" | head -c 200)"
        echo "       (o rellena MQTT_HOST/USER/PASS a mano para un broker externo)."
    fi
fi

export DEFAULT_FAN=$(jq -r '.DEFAULT_FAN // "Normal"' $CONFIG)
export DEFAULT_WATER=$(jq -r '.DEFAULT_WATER // "Medio"' $CONFIG)
export DEFAULT_MOP=$(jq -r '.DEFAULT_MOP // "Estándar"' $CONFIG)

# Datos persistentes en /data (mapa, zonas, horarios, vista, enlace e identidad).
# Con esto la identidad capturada se recuerda y NO se vuelve a la nube en cada arranque.
export DATA_DIR=/data

# Certificados TLS persistentes en /data (se generan una vez)
export CERT_PATH=/data/cert.pem
export KEY_PATH=/data/key.pem
if [ ! -f "$CERT_PATH" ] || [ ! -f "$KEY_PATH" ]; then
    echo "[INFO] Generando certificados TLS autofirmados..."
    openssl req -x509 -newkey rsa:2048 -keyout "$KEY_PATH" -out "$CERT_PATH" \
        -days 3650 -nodes -subj "/CN=tcp-cecotec.3irobotix.net"
fi

# El mapa, zonas, horarios y vista se guardan en /data (persistente entre reinicios)
cd /data
echo "[INFO] Clean Assistant: web por ingress (:8099), robot en :9090"
exec python3 -m uvicorn backend.app:app --app-dir /app --host 0.0.0.0 --port 8099
