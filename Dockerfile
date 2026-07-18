# Clean Assistant — imagen Docker independiente (fuera de Home Assistant).
# Sirve la interfaz web en :8000 y el servidor del robot (TLS+WS) en :9090.
#
#   docker build -t clean-assistant .
#   docker run -d --name clean-assistant -p 8000:8000 -p 9090:9090 \
#       --env-file .env -v "$PWD/data:/data" clean-assistant
#
# (o usa docker-compose.yml). CONGA_MODE=real + los IDs del robot van en el .env.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /app

# openssl: genera los certificados TLS autofirmados si no existen
RUN apt-get update && apt-get install -y --no-install-recommends openssl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY conga_core ./conga_core
COPY backend ./backend

# /data: certificados, mapa, zonas, horarios y vista (persistente)
ENV CERT_PATH=/data/cert.pem KEY_PATH=/data/key.pem
VOLUME ["/data"]
WORKDIR /data

EXPOSE 8000 9090
CMD ["python", "-m", "uvicorn", "backend.app:app", "--app-dir", "/app", \
     "--host", "0.0.0.0", "--port", "8000"]
