# Changelog

## 0.11.1
- Las zonas creadas en la app de Cecotec aparecen ahora automáticamente en la lista de
  Clean Assistant (se adoptan del mapa del robot, sin duplicar las que ya tienes).
- El mapa web se actualiza también cuando cambian solo las zonas (antes solo se
  refrescaba al cambiar la rejilla del mapa).

## 0.11.0
- Zonas: una sola lista. Se quita la sección duplicada "zonas guardadas en el robot";
  las zonas se dibujan sobre el mapa con su nombre y ahora se pueden **mover**
  (redibujar el rectángulo) desde la lista, además de renombrar y borrar.
- Texto del mapa nítido en pantallas de alta densidad (retina): se acabó el pixelado.

## 0.10.0
- Botón para restablecer cada consumible (cepillo central/lateral, filtro, mopa) al
  cambiar la pieza; pone el contador a 0. También como botones en Home Assistant (MQTT).
- Tipo de habitación como desplegable con icono + nombre.
- Zonas guardadas en el robot dibujadas sobre el mapa (rectángulo punteado con su nombre).

## 0.9.0
- Arreglado el modo "Cloud + Local": ya no se vuelve solo a local. La auto-provisión
  (captura de identidad) solo actúa en el primer arranque sin configurar.
- Zonas guardadas en el robot: ahora se pueden renombrar, mover (redibujando el
  rectángulo en el mapa) y borrar (reescribe las paredes virtuales del robot).
- Tipo de habitación por estancia con icono (Dormitorio, Comedor, Baño, Pasillo,
  Cocina, Salón, Terraza, Otros) en la pestaña Zonas.

## 0.8.0
- Zonas guardadas en el robot: se leen del mapa (prohibidas / sin fregona, incluidas
  las creadas en la app de Cecotec) y se listan en la pestaña Zonas con un botón
  «Consultar».
- Planes sugeridos afinados a la lógica de la app: succión por tipo de habitación
  (dormitorio Eco, salón Normal, resto Turbo) y agua/mopa según el tipo de suelo.

## 0.7.0
- Planes sugeridos según tu mapa (Solo dormitorios / Solo baños / Limpieza profunda):
  aparecen en Horarios y los añades con un toque; luego los editas o desactivas.
- Config automática por tipo de suelo al añadir una habitación a un horario: alfombra
  solo aspira, madera suave con poca agua, azulejos fregado fuerte.
- Detección de categoría de habitación por familia de tipo (2001/2101 = dormitorio…)
  y saneo de materiales de suelo fuera de rango.

## 0.6.0
- Identidad persistente: una vez capturada (auto-provisión), se guarda en `/data` y
  ya **no se vuelve a la nube** en cada arranque. Todos los datos (mapa, zonas,
  horarios, vista, enlace, identidad) se guardan de forma explícita en `/data`.
- Icono y logo del add-on para Home Assistant.
- README con instrucciones fáciles de instalación en Home Assistant y captura de la app.

## 0.5.2
- Arreglado el "Conga duplicado" en MQTT: el dispositivo se identificaba por el
  ROBOT_DID del entorno (0 en el add-on), no por el DID real capturado. Ahora usa
  el DID real, así que el add-on y cualquier prueba convergen en UN solo dispositivo,
  y al cambiar el DID se retira automáticamente el descubrimiento del duplicado viejo.

## 0.5.1
- Arreglado el mapa real: faltaba "tomar el control" del robot (`lock_device`) antes
  de pedir el mapa. Sin eso el robot ignoraba `get_map` estando en base y salía el
  mapa de ejemplo. Verificado en vivo con el robot (mapa Interior, 7 habitaciones).
- Diagnóstico de MQTT más claro cuando Home Assistant no expone un broker (indica si
  falta el add-on de Mosquitto).

## 0.5.0
- El mapa real se carga al arrancar: se pide al robot (get_map + getMapAll) en cuanto
  está en la base, sin tener que ponerlo a limpiar. Antes salía el mapa de ejemplo
  hasta la primera limpieza.
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
