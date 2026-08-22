# App (add-on) de Clean Assistant para Home Assistant.
# La imagen se PRECOMPILA en GitHub Actions (multi-arquitectura) y se publica en GHCR
# (ver .github/workflows/build.yml). Home Assistant la DESCARGA en vez de compilarla en el
# dispositivo -> actualizaciones rápidas y con barra de progreso real.
#
# BUILD_FROM y BUILD_VERSION los inyecta home-assistant/builder:
#   - BUILD_FROM: imagen base por arquitectura (definida en build.yaml).
#   - BUILD_VERSION: la versión de config.yaml -> se clona el tag vX.Y.Z del repo.
ARG BUILD_FROM
FROM ${BUILD_FROM}

ENV PYTHONUNBUFFERED=1
# tzdata es imprescindible: sin la base de zonas horarias, poner TZ + time.tzset() no surte
# efecto en Alpine y los horarios se disparan con desfase. Ver backend/app.py _apply_host_timezone.
RUN apk add --no-cache python3 py3-pip openssl jq git curl tzdata

ARG BUILD_VERSION
RUN git clone --depth 1 --branch "v${BUILD_VERSION}" https://github.com/miguelsg29/clean-assistant /app \
    && pip3 install --no-cache-dir --break-system-packages -r /app/requirements.txt

COPY run.sh /run.sh
RUN chmod a+x /run.sh
CMD [ "/run.sh" ]
