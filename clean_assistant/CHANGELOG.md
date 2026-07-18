# Changelog

## 0.4.1
- MQTT automático: si no rellenas los campos MQTT_*, el add-on coge el broker
  (Mosquitto) directamente de Home Assistant (servicio `mqtt`), sin escribir nada.
  Puedes seguir poniendo un broker externo a mano si lo prefieres.

## 0.4.0
- Autoconfiguración en el primer arranque: capta la identidad del robot (DID,
  userid, SN, MAC…) de la nube y pasa solo a modo local (no hay que meter los IDs).
- Modo "Cloud + Local": pasarela a la nube real de Cecotec — la app oficial
  funciona y se capturan sus comandos (para depurar). Selector en Ajustes.
- Lee los horarios reales guardados en el robot (incluidos los de la app Cecotec).
- Consumibles en horas con la vida real de cada pieza.

## 0.3.0
- Tipo de suelo por habitación: elegirlo y verlo en el mapa con una textura
  (madera, azulejos, alfombra, suave).
- Renombrar habitaciones y zonas en línea (sin ventanas emergentes).
- Consumibles: vida restante estimada (se corrige el % sin sentido).
- Pulido de interfaz: nombres del mapa más legibles (halo), barra de batería,
  más espacio para el dock, orden de limpieza numerado y resaltado de la
  habitación en curso.

## 0.2.0
- Primera versión del add-on de Clean Assistant para Home Assistant.
- Interfaz web integrada en la barra lateral de HA (ingress).
- Servidor del robot en el puerto 9090 (TLS + WebSocket).
- Configuración del robot y MQTT desde el formulario del add-on.
- Datos persistentes (mapa, zonas, horarios, vista) en /data.
