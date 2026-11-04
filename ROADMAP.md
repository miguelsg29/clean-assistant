# Clean Assistant — Roadmap

Ideas y trabajo pendiente para seguir mejorando Clean Assistant. Estado de referencia:
**v0.36.0**. (¿Sugerencias? Abre un [issue](https://github.com/miguelsg29/clean-assistant/issues).)

---

## ✅ Ya hecho (para no repetir)

### Robots compatibles (4 backends)
- **Gen. nueva Cecotec** (`new`): 8090 / 4690 / 9090 Ultra / 6090 / 7090 / 3890, reconocidos por
  su `project_type`.
- **Conga antiguos 3090 / 3490 / 4090** (`legacy`, experimental): protocolo TCP portado de
  `@agnoc/core`; habitaciones, mapas, horarios, «Ir aquí», mapa nuevo pendiente. *(v0.25–v0.31)*
- **Rowenta X-plorer Serie 80** (`robeye`, experimental): API local del robot; mapa, habitaciones,
  limpieza completa y por habitaciones, estado «Volviendo a la base». *(v0.32–v0.34)*
- **Conga sobre Tuya — 8290** (`tuya`, experimental): protocolo Tuya 3.3/3.4 en local con la
  local key; confirmado con un robot real. Sin mapa. *(v0.35)*

### Funciones
- **Mapa real** en vivo con habitaciones, posición, **traza del recorrido**, zoom/pan, girar/espejo
  por mapa; nombres que no se mueven ni se pisan.
- **Limpieza**: iniciar/pausar/reanudar, a base, localizar, por habitaciones y completa;
  succión/agua/mopa/modo, doble pasada, turbo alfombras, tipo de base, frecuencia de vaciado,
  voz+volumen, no molestar, OTA (off por defecto). Se recuerdan los últimos ajustes. *(v0.31.7)*
- **Control manual**: mando de 4 flechas + joystick en el mapa.
- **Habitaciones**: nombre, tipo, suelo, unir/separar, m² por habitación.
- **Zonas** por mapa: prohibida, sin fregona, x2; adopta las de la app oficial.
- **Horarios** por mapa con modo por habitación, sincronizados en ambos sentidos; planes
  sugeridos; ejecutar un plan bajo demanda.
- **Actividad**: historial paginado, habitaciones en orden de limpieza y **estadísticas totales**.
  *(v0.27.0)*
- **Salud de la batería** y **aviso de limpiar los sensores** cada 35 h. *(v0.28–v0.29)*
- **Diccionario de avisos** (códigos oficiales en 9 idiomas) + sensor «Conga Aviso».
- **Independencia de la nube**: suplanta control+OTA+historial; auto-provisión; copia de
  seguridad + «llave de recuperación».
- **Home Assistant (MQTT)**: `vacuum` + sensores + controles + horarios + consumibles; modelo
  real; posición (x/y/ángulo y **x_pct/y_pct** sobre la imagen); habitación actual; mapa como
  geometría y como **imagen PNG** con calibración; **mapa en vivo con intervalo de 5–30 s**;
  botón «Limpiar toda la casa»; **idioma de las entidades**; aviso si se pierde MQTT.
  *(v0.28–v0.36)*
- **Multiidioma**: 9 idiomas (ES/EN/DE/IT/FR/PT/NL/CA/PL); imagen precompilada en GHCR.
- Asistente de primer arranque (DNS + crear mapa).
- **Extras para Home Assistant** ([guía](docs/home-assistant.es.md)): 3 blueprints (limpiar al
  salir todos, avisar cuando necesita ayuda, recordatorio de consumibles), tarjetas de mapa con
  marcador del robot y botones de habitación, y «limpia la cocina» por voz con Assist.
- **Pruebas automáticas en el repositorio** (`tests/`, robots simulados y datos inventados) que se
  ejecutan en la CI en cada push y PR.

---

## 🧭 Pendiente / próximas mejoras

### Rápidas (poco esfuerzo, buen valor)
- **Más modelos** en el mapa de `project_type` y más Conga sobre Tuya (según los confirmen
  usuarios).
- **Revisión de traducciones** por hablantes nativos.
- **Más blueprints** según lo que pida la comunidad (p. ej. limpiar después de comer).

### Medianas
- **Limpiar una zona dibujada a demanda** (`set_area`), no solo habitaciones.
- **Ir a un punto en la gen. nueva** (hoy «Ir aquí» solo existe en `legacy`).
- **Modos por habitación en la limpieza inmediata** (los botones sueltos usan el modo general).
- **Orden de limpieza de las habitaciones** elegido por el usuario.
- **«Limpiar lo que toca»**: limpiar solo las habitaciones que llevan más de N días sin limpiar,
  usando el historial por habitación que ya guarda Clean Assistant (también como botón en HA).
- **Fecha estimada de cambio de cada consumible** según el uso real.
- **Nombre del robot escrito a mano para HA** (el de la app de Cecotec no llega en local).
- **Exportar el historial** (CSV) y **el mapa como PNG** desde la web.

### Grandes (más trabajo, muy visibles)
- **DNS integrado en el add-on** (mini-DNS) para no depender de AdGuard/Pi-hole: la mayor
  barrera de instalación.
- **Estadísticas en el tiempo**: m² y tiempo por semana/mes, desgaste de consumibles, miniatura
  del mapa por limpieza.
- **Gestión de mapas avanzada**: guardar, forzar que se rehaga, varios pisos (comandos del
  firmware aún sin exponer).
- **Alta 100% local (SoftAP)**: dar de alta un robot reseteado sin la nube de Cecotec. Falta
  capturar el protocolo de emparejamiento de la app oficial.
- **Más backends**: Ecovacs (#24), ROMY (API HTTP local); mapa en el backend `tuya`.

### Robustez / adopción
- **Página de diagnóstico**: log en vivo, últimas órdenes, estado de conexión, firmware.
- **Estado «reconectando»** visible cuando el robot se cae.
- **Más pruebas**: un mapa de RobEye inventado (la prueba actual usa una casa real y no se sube) y
  pruebas de la app completa (zonas, horarios, borrado de mapas).
- **Documentación/ayuda en la app** (tooltips, FAQ).
- **awesome-home-assistant**: enviar el PR a partir del **18-ene-2027** (regla de 6 meses).

### A futuro (nice-to-have)
- Multi-robot, contraseña opcional en la web, más temas.

---

## Prioridad sugerida

| Prioridad | Ítems |
|---|---|
| **Alta** | DNS integrado · Zona dibujada |
| **Media** | «Limpiar lo que toca» · Ir a un punto · Estadísticas en el tiempo · Fecha de consumibles |
| **Baja** | Diagnóstico · más pruebas · orden de habitaciones · exportar · nice-to-have |
