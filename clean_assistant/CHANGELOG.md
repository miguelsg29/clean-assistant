# Changelog

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
