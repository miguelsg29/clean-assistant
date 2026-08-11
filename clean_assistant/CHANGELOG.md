# Changelog

## 0.16.34
- Historial: arreglado que cada limpieza aparecía DUPLICADA — una vez con su horario real y
  otra como «Manual · Toda la casa». Eran dos registros de la MISMA limpieza: el seguimiento
  local y el informe que el robot sube (historial de la nube local). Ahora se deduplican: se
  conserva el registro local (más completo, con habitaciones y nombre del horario) y el
  informe solo rellena limpiezas que Clean Assistant no vio (p. ej. hechas sin él conectado).
- Instrucciones de DNS (Ajustes y asistente de primer arranque): ahora dejan claro que con
  `tcp-cecotec` basta para CONTROLAR el robot, y que para el 100 % local (que siga funcionando
  aunque Cecotec apague sus servidores) hay que redirigir TAMBIÉN los dominios de OTA e
  historial. Se listan todos con su función y todos apuntan a la misma IP.

## 0.16.33
- INDEPENDENCIA TOTAL: Clean Assistant ahora puede APRENDER la identidad del robot del PROPIO
  robot, sin nube y sin tenerla guardada. En una instalación nueva, en cuanto rediriges los
  DNS del robot a Clean Assistant, el robot revela en sus peticiones (OTA/historial) su DID,
  número de serie y modelo; la MAC se obtiene de la red (ARP) y el identificador de cuenta se
  genera a partir del DID (en local, Clean Assistant hace de «nube» y empareja el robot). Así
  ya no hace falta pasar por la nube de Cecotec ni siquiera la PRIMERA vez. (Si ya tienes
  identidad guardada o configurada, no se toca nada; la «llave de recuperación» sigue siendo
  útil para clonar/mover a otro servidor.)

## 0.16.32
- ARREGLO IMPORTANTE (independencia de la nube): el robot se quedaba en bucle consultando OTA
  sin parar (spam de `cecotec-ota` en el DNS) y no arrancaba el control tras un reinicio si
  todos los dominios apuntaban a Clean Assistant. Causa: el robot VALIDA el nombre del
  certificado en cada conexión, y el cert de Clean Assistant solo cubría `tcp-cecotec` (el
  control), no los dominios de OTA/historial. Ahora el certificado incluye TODOS los dominios
  de Cecotec (con comodines), así que el robot completa OTA e historial y arranca 100% local.
  Los certificados antiguos se regeneran solos al actualizar.
- LLAVE DE RECUPERACIÓN DEL ROBOT: en «Copia de seguridad» puedes exportar/importar los DATOS
  DE IDENTIDAD del robot (DID, número de serie, MAC…) aparte de los mapas/zonas/horarios. Con
  ella puedes restaurar el robot en un servidor nuevo SIN pasar por la nube de Cecotec (en
  local, Clean Assistant responde al robot con estos datos; no los aprende solo). Guárdala en
  lugar seguro: son credenciales del robot.

## 0.16.31
- ACTUALIZACIONES AUTOMÁTICAS (OTA) OFF POR DEFECTO EN AMBOS MODOS: en una instalación nueva
  se desactivan tanto en modo local como en modo cloud (antes solo se aplicaba en local). El
  usuario las puede activar a mano cuando quiera (acción «ota»); nunca se activan solas.
  Además, cuando los dominios OTA de Cecotec se redirigen a Clean Assistant, el servidor OTA
  local siempre responde «sin actualización», así que el robot tampoco descarga firmware por
  su cuenta. (Instalaciones existentes: no se toca tu ajuste actual.)

## 0.16.30
- INDEPENDENCIA DE LA NUBE: Clean Assistant ahora suplanta también los servicios auxiliares
  de Cecotec, así que el robot sigue funcionando aunque Cecotec apague sus servidores.
  - OTA (puerto 8001): al arrancar, el robot pregunta «¿hay firmware nuevo y dónde están los
    servicios?». Respondemos «sin actualización» + un directorio que apunta al control LOCAL.
    Es la pieza clave: sin esta respuesta el robot no sabía a dónde conectar y se quedaba en
    bucle de reconexión. Descubierto por ingeniería inversa del propio Conga 8090.
  - Historial (puertos 8002/8006): el robot sube un informe por cada limpieza. Ahora los
    aceptamos y los volcamos al HISTORIAL de Clean Assistant (fecha, hora, m², duración, mapa),
    para tener el histórico de limpiezas SIN nube.
  - Para activarlo, redirige por DNS (AdGuard/Pi-hole) los dominios de Cecotec a Home Assistant
    (los mismos del control). Los puertos 8001/8002/8006 se abren automáticamente en el add-on.

## 0.16.29
- Zonas por mapa: al CREAR o activar un mapa ya no se ven un rato las zonas del mapa
  anterior. El backend ahora reemite las zonas (y los horarios guardados en el robot)
  cuando cambia el mapa activo, no solo cuando cambias de mapa a mano. (Los horarios de
  Clean Assistant ya se refrescaban; faltaba hacerlo con las zonas.)

## 0.16.28
- HORARIOS: arreglado de raíz que se disparaban a destiempo (o no se disparaban). El robot
  compara la hora contra SU RELOJ, y Clean Assistant se lo pone en hora LOCAL al conectar
  (set_time), así que la hora del horario va en LOCAL y NO se convierte. Antes se convertía
  a UTC y quedaba desfasada. Verificado en vivo: un horario a las 20:56 disparó a las 20:56.
- Home Assistant (add-on): ahora lee del Supervisor la ZONA HORARIA de Home Assistant y la
  aplica (el contenedor suele estar en UTC, lo que rompía la hora del reloj del robot), y la
  IP LAN del HOST para las instrucciones de DNS (no la IP interna de Docker 172.30.x.x).
  Requiere el permiso `hassio_api` (añadido).
- Asistente de primer arranque: pide el nombre de la CASA y el nombre del MAPA por separado.
- El asistente vuelve a aparecer si borras TODOS los mapas (antes, tras saltarlo una vez, no
  reaparecía).
- Mapa: el ESPEJO (invertido) viene activado por defecto — el mapa del Conga sale en espejo
  respecto a la casa, así no hay que darle al botón cada vez. (El giro sigue a tu gusto.)
- Batería: el ⚡ de carga se muestra al lado del porcentaje (no dentro del icono).
- Mapas: nuevo botón «Borrar todos» (borra todos los mapas del robot y de Clean Assistant)
  para empezar de cero o limpiar mapas fantasma al cambiar de servidor de un tirón.

## 0.16.27
- Al cambiar de mapa se muestra un indicador de carga («Cambiando de mapa…») sobre el mapa
  mientras el robot carga el mapa nuevo (tarda unos segundos), en lugar de enseñar un
  instante el mapa anterior. Se quita en cuanto llega el mapa nuevo (o a los 9 s como
  máximo, por si acaso).

## 0.16.26
- Quitada la detección automática de «mapa fantasma» que añadió la 0.16.25: daba FALSOS
  POSITIVOS (el robot tarda en cargar el mapa al cambiar, y se interpretaba como que el
  mapa no existía) y llegaba a ofrecer borrar un mapa BUENO. Los mapas que ya no existan se
  quitan a mano con la ✕; el borrado previo al crear el primer mapa sigue evitando que se
  acumulen.
- El asistente de primer arranque ya NO aparece mientras el robot está mapeando o en la
  primera limpieza automática (antes podía salir al no haber aún ningún mapa guardado).
- Batería: aparece un ⚡ sobre el icono cuando el robot está cargando.
- Copia de seguridad (exportar/importar) ahora incluye también las HABITACIONES de cada
  mapa (nombre, tipo de estancia y tipo de suelo). Al importar en el MISMO robot que las
  hubiera perdido, se le vuelven a aplicar (si coinciden los ids de habitación).
- Zonas por mapa: al cambiar de mapa ya no se «cuelan» copias de las paredes de un mapa en
  otro. Al adoptar las zonas del robot se deduplica contra TODOS los mapas (el robot puede
  devolver un instante las paredes del mapa anterior por el retardo de carga).

## 0.16.25
- Mapas fantasma: al activar un mapa que el robot ya no tiene, Clean Assistant lo detecta
  (el mapa cargado no cambia), vuelve al mapa anterior y avisa ofreciendo quitarlo de la
  lista. Antes lo marcaba como activo aunque el robot siguiera en otro mapa.
- Configuración de red (DNS) también en Ajustes: sección desplegable con el dominio a
  reescribir, la IP de este servidor y si el robot conecta (la misma info del asistente,
  como referencia por si cambias de red).
- Mapa: doble toque/doble clic para acercar (hacia el punto tocado) y volver a ajustar.
- Los «Horarios guardados en el robot» pasan a ser una sección de diagnóstico plegable:
  Clean Assistant ya los mantiene sincronizados con los de arriba, así que normalmente
  coinciden; la lista queda solo para comprobar lo que el robot tiene guardado.
- Zonas y varios servidores: las paredes virtuales solo se reenvían al robot si este las
  ha PERDIDO (reinicio), no en cada reconexión. Así, si controlas el robot desde dos
  servidores (p. ej. este equipo y el add-on de Home Assistant), las zonas no se acumulan.

## 0.16.24
- Asistente de primer arranque ampliado: ahora explica cómo redirigir el DNS del robot a
  este servidor (AdGuard Home, Pi-hole o el router), mostrando el dominio a reescribir y la
  IP de este servidor (detectada automáticamente), con un indicador en vivo de si el robot
  ya conecta. Después ofrece crear el primer mapa. Nuevo endpoint `/api/setup`.
- Mapa: ZOOM y DESPLAZAMIENTO. Rueda del ratón (hacia el cursor), pellizco (pinch) y
  arrastre con dos dedos en el móvil, arrastre con un dedo cuando hay zoom, y botones
  +/−/ajustar. Al girar el mapa se vuelve a encajar.
- Táctil: el mapa ya no hace scroll de la página al interactuar (touch-action), así se
  pueden dibujar zonas, dividir/unir habitaciones y seleccionar habitaciones a dedo en el
  móvil.

## 0.16.23
- Horarios: arreglado el desfase de 2 horas. El robot (como la nube de Cecotec) guarda la
  hora de los horarios en UTC y la app oficial la muestra en local; Clean Assistant hacía
  la conversión al revés y mostraba 2 h menos (p. ej. las 13:00 salían como 11:00). Ahora
  CA convierte UTC↔local en ambos sentidos (con horario de verano/invierno), así la hora
  coincide con la app y el robot dispara a la hora correcta. Maneja también el cambio de
  día si el horario cae de madrugada.
- El robot pone su reloj en hora al conectar (set_time con la zona horaria local), para
  que los horarios se disparen a tiempo aunque el robot lleve tiempo sin nube.
- La sincronización de horarios CA↔robot ahora casa por NOMBRE (antes por nombre+hora):
  así un horario que existe en ambos lados ya no se re-importa/re-empuja en bucle si su
  hora difiere (lo que podía reescribir la hora del robot).
- Primer arranque (solo instalación nueva): las actualizaciones automáticas (OTA) quedan
  DESACTIVADAS y el vaciado del colector en «después de cada limpieza». En una instalación
  existente NO se tocan tus ajustes.
- Asistente de bienvenida: si Clean Assistant no tiene ningún mapa, ofrece crear uno
  (avisando de que se borrarán los mapas/zonas/horarios que el robot tenga). Se puede
  saltar («Ahora no»).
- Al crear el PRIMER mapa se borran antes todos los mapas del robot, para que quede solo
  el nuevo. Esto evita el problema de los MAPAS DUPLICADOS: el Conga admite varios mapas y
  guardaba cada mapeo como uno nuevo sin borrar los anteriores; si un mapeo se quedaba a
  medias (p. ej. el robot no llegaba a la base por una silla) y se repetía, se acumulaban
  mapas («Interior», «Planta», «Mapa1»…). (Crear un mapa ADICIONAL teniendo ya otros sigue
  sin borrarlos.)

## 0.16.22
- Detalle de la cabecera del mapa: al ir el estado en su propia línea, se quita el «·»
  que llevaba delante (p. ej. «EN LA BASE» en vez de «· EN LA BASE»).

## 0.16.21
- Actividad: una limpieza larga con cortes (p. ej. si el robot no llega a la base y sale
  y vuelve) ya NO genera muchas entradas; se registra como UNA sola. También usa el nombre
  del mapa de Clean Assistant (no el poco fiable del robot).
- Nombre de la casa: al editarlo ya no se revierte al cambiar de mapa (antes el robot lo
  pisaba); se guarda como alias local.
- «Horarios guardados en el robot»: muestra los NOMBRES de las habitaciones en vez de sus
  IDs.
- Error 512 reconocido como «Error al volver a la base».
- Vista móvil: en la cabecera del mapa, el nombre va en su línea y el estado/m²/tiempo
  debajo (antes se cortaban y los tapaban los botones de girar).

## 0.16.20
- Arreglado que el robot no respetaba las zonas prohibidas: al reiniciar el robot pierde
  las paredes virtuales (set_virwall) y Clean Assistant no las reponía. Ahora, cuando el
  robot (re)conecta, CA vuelve a enviarle las zonas del mapa activo automáticamente (tras
  adoptar las que ya tuviera, para no perder ninguna).

## 0.16.19
- Los días de la semana en «Horarios guardados en el robot» empiezan por L (lunes) y
  acaban en D (domingo).
- Símbolo de la base en el mapa más bonito (icono de casa con rayo de carga).
- El registro de Actividad guarda también los avisos/errores del robot: el de agua con su
  mensaje, y el resto con el código de error (para investigarlos cuando pasen). Se ignoran
  los avisos normales de estación (21xx).
- Home Assistant: nuevo sensor binario «Falta agua» (device_class problem) que se activa
  con el aviso de depósito de agua bajo (faultCode 525).

## 0.16.18
- Frecuencia de vaciado del colector (Ajustes → Base): Nunca, Después de cada limpieza,
  Cada 30/60/90 minutos, Cada 2 horas. Capturado de la app oficial (set_preference
  ctrltype 16; -1=Nunca, 0=tras cada limpieza, N=minutos). El selector refleja el valor
  actual del robot.

## 0.16.17
- Aviso de «Depósito de agua bajo» (faultCode 525) en la cabecera del mapa. Se irán
  añadiendo más avisos/errores a medida que se capturen.
- Nueva pestaña «Actividad»: registro de cada limpieza (tipo manual/programada, con el
  nombre del horario si aplica; habitaciones; m²; duración; día y hora). Se guarda en
  Clean Assistant (history.json). Botón para vaciar el registro.

## 0.16.16
- Arreglada la ESCALA de los m² limpiados: el robot manda el área en centésimas de m²
  (cleanSize 1506 = 15,06 m²); antes se mostraba tal cual (números absurdos como 158 o 222
  que subían al limpiar). Ahora se divide entre 100 y se ve el valor real.

## 0.16.15
- La cabecera del mapa conserva los m² y el tiempo de la ÚLTIMA LIMPIEZA (hasta la
  siguiente). Solo cuenta limpiezas normales: durante el mapeo o la 1ª limpieza automática
  el robot da un área absurda (p. ej. 158 m² en 1 min) que ya no se muestra.
- Zonas: se quita la ROTACIÓN. Las zonas prohibidas/sin fregona del robot son rectángulos
  alineados; una zona girada no la puede dibujar la app oficial (parecía desaparecer). Se
  mantienen mover y redimensionar. (Si tenías una zona girada, se re-alinea al editarla.)

## 0.16.14
- Muestra los metros cuadrados: de cada habitación (en las fichas de Limpieza y en la
  lista de suelos), el total de la casa (suma de habitaciones), y los m² limpiados en la
  última limpieza (ya en la cabecera del mapa). El área se calcula desde la rejilla del
  mapa con la escala verificada (res 0.05 m/celda).

## 0.16.13
- La casa del mapa se muestra sin el prefijo "Casa:" (solo el nombre).
- La zona de limpieza pasa a ser de DOBLE PASADA: el botón «+ Limpieza x2» crea una zona
  que el robot limpia dos veces (set_area Type 201). Verificado: el robot acepta el
  comando; el protocolo lo documenta como 2 pasadas.

## 0.16.12
- Editar mapa: ahora también puedes cambiar el nombre de la CASA (toca el nombre de la
  casa en la lista de mapas).
- Zonas: selecciona una zona (botón de editar en la lista) y edítala directamente sobre
  el mapa: arrástrala para MOVERLA, tira de las esquinas para cambiar el TAMAÑO, y usa el
  círculo de arriba para ROTARLA. Toca fuera para terminar.
- Separar habitación: la línea de corte ya puede empezar o acabar FUERA de la habitación;
  se corta la habitación que la línea cruza (el robot recorta lo que sobra).

## 0.16.11
- Ventanas de confirmación/aviso propias de la app (mismo diseño), en vez de las del
  navegador ("192.168… dice"). Se cierran con Aceptar/Cancelar, Enter/Esc o tocando fuera.
- Arreglado el selector Local / Cloud + Local: al cancelar la confirmación ya no se queda
  marcado el botón (antes un manejador genérico lo marcaba igualmente).
- El nombre del mapa activo ya no se repite arriba junto al logo (solo aparece en la
  esquina del mapa).
- Arreglado un fallo por el que, al borrar un mapa recién tras crear otro, se podía copiar
  el nombre del mapa nuevo a otro mapa.

## 0.16.10
- Al crear un mapa, se conserva el NOMBRE (y la casa) que eliges: antes el mapa nuevo
  podía quedarse con el nombre que reportaba el robot (no fiable) y salir con el nombre
  de otro mapa. Ahora, al guardarse el mapa nuevo, se le pone el nombre que pusiste.

## 0.16.9
- Durante la primera limpieza automática tras crear un mapa, el estado se muestra ahora
  como «Primera limpieza automática» (en vez de «Limpiando»), para dejar claro que es la
  pasada que hace el robot justo después de mapear. Mientras mapea sigue mostrando
  «Mapeando».

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
