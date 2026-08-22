# Add-on de Clean Assistant para Home Assistant.
# Instala la app desde el repo publicado (no se duplica el código aquí).
# Para producción, fija CA_REF a un tag de release (p. ej. v0.2.0).
FROM alpine:3.20

ENV PYTHONUNBUFFERED=1
# tzdata es imprescindible: sin la base de zonas horarias, poner TZ + time.tzset() no surte
# efecto en Alpine y el contenedor se queda en UTC -> el reloj del robot se pone en UTC y los
# horarios se disparan con desfase (p. ej. 2 h en verano). Ver backend/app.py _apply_host_timezone.
RUN apk add --no-cache python3 py3-pip openssl jq git curl tzdata

ARG CA_REF=v0.17.2
RUN git clone --depth 1 --branch ${CA_REF} https://github.com/miguelsg29/clean-assistant /app \
    && pip3 install --no-cache-dir --break-system-packages -r /app/requirements.txt

COPY run.sh /run.sh
RUN chmod a+x /run.sh
CMD [ "/run.sh" ]
