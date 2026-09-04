# Clean Assistant — Roadmap

Ideas y trabajo pendiente para seguir mejorando Clean Assistant. Estado de referencia:
**v0.17.11**. (¿Sugerencias? Abre un [issue](https://github.com/miguelsg29/clean-assistant/issues).)

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
  robot en hora (`set_time`).
- **Historial / actividad** de limpiezas (+ informes que sube el robot).
- **Independencia de la nube**: suplanta control+OTA+historial; **auto-provisión** de la
  identidad; copia de seguridad (config + «llave de recuperación»).
- **Home Assistant (MQTT)**: entidad `vacuum` + sensores + controles + horarios; **modelo
  real** del robot (8090/4690…).
- **Multiidioma** (ES/EN/PT/FR/PL) e **imagen precompilada** (updates rápidos).
- Asistente de primer arranque (DNS + crear mapa).

---

## 🧭 Pendiente / próximas mejoras

### Rápidas (poco esfuerzo, buen valor)
- **Consumibles sin abrir la app oficial**: forzar `get_consumables` de forma más agresiva
  para que aparezcan al conectar (issue #1).
- **Más modelos Conga** en el mapa de `project_type` (según los confirmen usuarios).
- **Nombre de dispositivo** en HA: idealmente el que el usuario puso en la app de Cecotec.
  Ese nombre **no parece llegar por el protocolo local** (probablemente solo en la nube);
  a investigar con captura. Alternativa: opción manual para escribirlo.

### Medianas
- **Errores claros + notificaciones**: diccionario de `faultCode` → mensajes («atascado»,
  «cepillo enredado», «depósito lleno»…) y avisos en HA/UI ante error/atasco/consumible
  bajo o fin de limpieza.
- **Control manual (mando/flechas)**: `set_direct` ya existe; falta la UI para
  desatascar/recolocar el robot.
- **Lanzar limpieza de una zona dibujada**: limpiar un rectángulo concreto a demanda
  (`set_area`), no solo habitaciones.
- **Modos por habitación en la limpieza inmediata** (hoy la directa usa un modo global).

### Grandes (más trabajo, muy visibles)
- **Traza del recorrido en el mapa**: dibujar por dónde ha limpiado el robot (acumular su
  posición). Es el mayor salto visual frente a Valetudo.
- **Estadísticas**: totales por semana/mes, m² y desgaste de consumibles en el tiempo;
  miniatura del mapa por limpieza.

### Robustez / adopción
- **Página de diagnóstico**: log en vivo, últimos comandos, estado de conexión, firmware.
- **Reconexión tolerante a fallos** con estado «reconectando» visible.
- **Pruebas automáticas** de la lógica delicada (horarios/zonas por mapa, coordenadas, mapa).
- **DNS integrado en el add-on** (mini-DNS) para no depender de AdGuard/Pi-hole.
- **Documentación/ayuda en la app** (tooltips, FAQ).

### A futuro (nice-to-have)
- Multi-robot, autenticación opcional en la web, exportar mapa como PNG, más temas.

---

## Prioridad sugerida

| Prioridad | Ítems |
|---|---|
| **Alta** | Consumibles · Errores+notificaciones · Traza del recorrido |
| **Media** | Control manual · Lanzar zona · Estadísticas · Nombre de dispositivo |
| **Baja** | Diagnóstico · DNS integrado · pruebas · nice-to-have |
