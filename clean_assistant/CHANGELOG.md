# Changelog

## 0.16.8
- Estado del robot durante el mapa nuevo: antes salía «Inactivo» al mapear y en la
  primera limpieza automática. El robot usa el mismo modo (workMode 45) para ambas fases;
  ahora Clean Assistant muestra «Mapeando» mientras recorre la casa y «Limpiando» cuando
  ya está limpiando habitaciones (se distingue por si está asignado a una habitación).

## 0.16.7
- Al borrar un mapa se borran también SUS zonas y SUS horarios en Clean Assistant.
- Borrar el mapa ACTIVO ahora es fiable: se cambia primero a otro mapa desactivado, se
  borra, y se activa ese otro cargando su mapa completo. Antes el robot podía quedarse
  sin mapa y salía el mapa de ejemplo.
- Un mapa borrado ya no reaparece en la lista: durante la transición el robot podía
  reportarlo un instante y Clean Assistant lo re-adoptaba; ahora se recuerda como borrado.

## 0.16.6
- Cabecera del mapa (esquina superior izquierda): muestra el nombre del MAPA ACTIVO (o
  «Sin mapa»), el estado del robot, y los m² y el tiempo de la última limpieza (se
  mantienen hasta la siguiente limpieza).
- Zonas por mapa: en la pestaña Zonas y dibujadas sobre el mapa aparecen SOLO las zonas
  del mapa activo. Cada zona queda asociada a su mapa (las que había antes se re-adoptan
  del robot, que guarda las paredes virtuales por mapa).
- «Horarios guardados en el robot»: ahora muestra solo los del mapa activo (el robot
  guarda los de todos los mapas, pero solo ejecuta los del activo).
- Cambio de mapa instantáneo en la interfaz: al cambiar de mapa, el selector, los
  horarios y las zonas se actualizan al momento (antes había que esperar y refrescar).
  Además se re-pide el mapa completo del nuevo mapa para traer sus zonas.
- Diagnóstico: se registra el workMode del robot para identificar el estado durante el
  mapeo/primera limpieza (que salía como «inactivo»).

## 0.16.5
- Ahora SÍ se puede borrar el último mapa y dejar el robot sin ninguno, para empezar de
  cero (el robot admite quedarse sin mapa; la 0.16.4 lo bloqueaba por error).
- Arreglado el mapa «fantasma»: al borrar todos los mapas, el robot devuelve un mapa
  vacío y Clean Assistant ya no sigue mostrando el mapa anterior. El área del mapa pasa a
  «sin mapa · crea uno nuevo» y se borra la caché para que no reaparezca al reiniciar.
- Al borrar el último mapa, el aviso deja claro que el robot se quedará sin mapa.

## 0.16.4
- Borrado de mapas más coherente con el robot: el robot SIEMPRE conserva un mapa activo
  (no admite quedarse con cero). Al intentar borrar el último, en vez de dejar la lista
  vacía y descuadrada, se avisa y se guía a «Crear mapa nuevo» (remapea y reemplaza).
- Arreglado el descuadre en el que, tras borrar mapas, la lista quedaba vacía pero el
  robot seguía teniendo un mapa (y se veía en el área del mapa): Clean Assistant re-adopta
  el mapa activo del robot para que lista y vista coincidan siempre con el robot.

## 0.16.3
- Ahora se puede borrar CUALQUIER mapa, también el activo. Al borrar el mapa activo,
  Clean Assistant cambia primero a otro mapa (el robot siempre necesita uno activo),
  espera a que el robot confirme el cambio y luego lo borra. Si es el único mapa, se
  intenta el borrado directo. La papelera (✕) aparece ya en todos los mapas y, si un
  borrado falla, se muestra el aviso en vez de ignorarlo en silencio.

## 0.16.2
- El nombre del mapa activo aparece ahora en la cabecera (arriba a la izquierda), junto
  a "Conga 8090 Ultra".
- Arreglado el parpadeo al cambiar de mapa: la lista de mapas solo se reenvía a la
  interfaz cuando cambia de verdad el mapa activo o la lista, no en cada fotograma del
  mapa. Antes el indicador "Activo" hacía cosas raras durante la transición.

## 0.16.1
- Arreglada la sincronización de horarios por mapa (la anterior hacía cosas raras).
  El robot devuelve TODOS los horarios con su mapid; ahora Clean Assistant los casa por
  nombre+hora y filtra por el mapa activo. Sincronización bidireccional: importa del
  robot los que falten (incluidos los de la app) y sube los de Clean Assistant que
  falten. Ids de horario únicos por mapa (un mismo nombre en dos mapas no colisiona).

## 0.16.0
- Sincronización de horarios al cambiar de mapa: antes de cambiar, Clean Assistant
  guarda los horarios que el robot tiene del mapa actual (si no los tiene ya), los
  borra del robot, cambia de mapa y carga los del mapa nuevo. Así el robot solo tiene
  los horarios del mapa activo. Incluye conversor de horario del robot (getOrder6090)
  a plan de Clean Assistant.

## 0.15.0
- Unir y separar habitaciones (pestaña Zonas → "Editar habitaciones"): "Unir" (toca
  dos habitaciones en el mapa) y "Separar" (dibuja una línea de corte cruzando una
  habitación). Usa mergeRoom / splitRoom; el mapa se actualiza al aplicarlo.

## 0.14.1
- Crear mapa: ahora se GUARDA. Al terminar el mapeo (el robot vuelve solo a la base),
  Clean Assistant envía `setSaveMap` para conservar el mapa nuevo. Antes faltaba ese
  paso y el mapa se descartaba. Importante: deja que el mapeo termine (no mandes el
  robot a la base a mano antes de tiempo).

## 0.14.0
- Crear mapa nuevo: botón en "Mapas de la casa" para poner nombre de mapa + casa y
  que el robot empiece a mapear (recorre la casa). Con esto la gestión de mapas queda
  completa: listar, cambiar, renombrar, borrar y crear.
- La lista de mapas muestra el nombre de la casa junto al del mapa ("Interior · Casa").

## 0.13.0
- Borrar mapas: botón para eliminar del robot un mapa que no sea el activo
  (selectMapPlan type=2).
- Horarios por mapa: cada horario pertenece a su mapa y solo se ven/ejecutan los del
  mapa activo; los de otros mapas aparecen al cambiar a ese mapa. Los horarios antiguos
  se asignan al mapa activo la primera vez.
- Arreglado el botón "Activar" de mapa: la lista se actualiza al instante al cambiar.
- La lista de mapas muestra solo el nombre del mapa (sin la casa) y con nombre fiable.

## 0.12.0
- Gestión de mapas de la casa (Ajustes → "Mapas de la casa"): Clean Assistant recuerda
  los mapas que va viendo (nombre + casa) y permite cambiar entre ellos (selectMapPlan)
  y renombrarlos. La lista se forma según los mapas que visitas: el robot no expone la
  lista completa en local (vive en la nube de Cecotec). Al cambiar de mapa, las zonas y
  horarios pueden no coincidir (son por mapa).

## 0.11.2
- Rediseño del selector de tipo de habitación (pestaña Zonas): desplegable propio con
  el estilo de la app (icono + nombre, acento teal) en vez del desplegable del sistema.
- Emojis más grandes y alineados (ancho fijo y centrado) en el nombre de la habitación
  y en el selector de tipo.

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
