# Clean Assistant — Roadmap

Ideas y trabajo pendiente para seguir mejorando Clean Assistant. Estado de referencia:
**v0.22.0**. (¿Sugerencias? Abre un [issue](https://github.com/miguelsg29/clean-assistant/issues).)

---

## ✅ Ya hecho (para no repetir)

- **Mapa real** en vivo (zlib+Protobuf) con habitaciones, posición del robot, zoom/pan,
  girar/espejo por mapa.
- **Limpieza**: iniciar/pausar/reanudar, a base, localizar, por habitaciones y completa;
  succión/agua/mopa/modo, doble pasada, turbo alfombras, tipo de base, **frecuencia de
  vaciado**, voz+volumen, no molestar, OTA.
- **Habitaciones**: nombre, tipo, tipo de suelo, unir/separar, m² por habitación.
- **Zonas** por mapa: prohibida, sin fregona, x2 — crear/mover/redimensionar/rotar/borrar;
  adopta las de la app oficial.
- **Horarios** por mapa con modo por habitación, sincronizados en ambos sentidos; reloj del
  robot en hora (`set_time`). **Ejecutar un plan bajo demanda** (botón «Ejecutar…» en HA +
  `POST /api/schedules/run`). *(v0.19.0)*
- **Historial / actividad** de limpiezas (+ informes que sube el robot).
- **Independencia de la nube**: suplanta control+OTA+historial; **auto-provisión** de la
  identidad; copia de seguridad (config + «llave de recuperación»).
- **Home Assistant (MQTT)**: entidad `vacuum` + sensores + controles + horarios; **modelo
  real** del robot (**8090 / 4690 / 9090** Ultra); **posición del robot** (x/y/ángulo) para
  floorplans externos *(v0.18.1)*; sensor **«Habitación actual»** *(v0.19.0)*.
- **Traza del recorrido** en el mapa: dibuja por dónde ha limpiado el robot; va también en
  `GET /api/map` (`trail`). *(v0.21.0)*
- **Mapa por MQTT** (sensor «Conga Mapa»): geometría + traza como atributos, para tarjetas de HA
  sin pasar por el ingress (con throttle para no cargar el recorder). *(v0.22.0)*
- **Consumibles**: se piden de forma persistente para que salgan sin abrir la app de Cecotec.
  *(v0.21.1)*
- **BD de HA mucho más ligera**: debounce de disponibilidad (evita cientos de miles de filas
  en el recorder). *(v0.18.0)*
- **Diagnóstico de errores**: cada `faultCode` nuevo se registra en el log (base del futuro
  diccionario de errores). *(v0.19.1)*
- **Multiidioma**: **9 idiomas** (ES/EN/DE/IT/FR/PT/NL/CA/PL) *(v0.20.0)* e **imagen
  precompilada** en GHCR (updates rápidos).
- Asistente de primer arranque (DNS + crear mapa).

---

## 🚧 En progreso

- **Diccionario de errores + notificaciones**: el log ya registra los `faultCode` (v0.19.1).
  Falta: mapear cada código a un mensaje entendible («atascado», «cepillo enredado»,
  «depósito lleno»…) y **avisar en HA/UI** ante error/atasco/consumible bajo o fin de
  limpieza. Solo conocemos 2 códigos (525, 512): se están **recopilando de la comunidad**.

---

## 🧭 Pendiente / próximas mejoras

### Rápidas (poco esfuerzo, buen valor)
- **Más modelos Conga** en el mapa de `project_type` (según los confirmen usuarios).
- **Revisión de traducciones** DE/IT/NL/CA por hablantes nativos (issues/PR de la comunidad).

### Medianas
- **Control manual (mando/flechas)**: `set_direct` ya existe; falta la UI para
  desatascar/recolocar el robot.
- **Lanzar limpieza de una zona dibujada**: limpiar un rectángulo concreto a demanda
  (`set_area`), no solo habitaciones.
- **Modos por habitación en la limpieza inmediata de habitaciones** (los planes bajo demanda
  ya aplican los de la 1ª habitación; los botones de habitación sueltos usan el modo global).
- **Nombre de dispositivo manual en HA**: el nombre puesto en la app de Cecotec **no llega
  por el protocolo local** (verificado; vive solo en la nube). Workaround actual: renombrar
  el dispositivo a mano en HA. Pendiente (opcional): un campo para escribirlo en CA.

### Grandes (más trabajo, muy visibles)
- **Estadísticas**: totales por semana/mes, m² y desgaste de consumibles en el tiempo;
  miniatura del mapa por limpieza.

### Robustez / adopción
- **Página de diagnóstico**: log en vivo, últimos comandos, estado de conexión, firmware.
- **Reconexión tolerante a fallos** con estado «reconectando» visible.
- **Pruebas automáticas** de la lógica delicada (horarios/zonas por mapa, coordenadas, mapa).
- **DNS integrado en el add-on** (mini-DNS) para no depender de AdGuard/Pi-hole.
- **Documentación/ayuda en la app** (tooltips, FAQ).
- **awesome-home-assistant**: enviar el PR a partir del **18-ene-2027** (regla de 6 meses).

### A futuro (nice-to-have)
- Multi-robot, autenticación opcional en la web, exportar mapa como PNG, más temas.

---

## Prioridad sugerida

| Prioridad | Ítems |
|---|---|
| **Alta** | Diccionario de errores + notificaciones · Estadísticas |
| **Media** | Control manual · Lanzar zona dibujada · Nombre de dispositivo manual |
| **Baja** | Diagnóstico · DNS integrado · pruebas · revisión de traducciones · nice-to-have |
