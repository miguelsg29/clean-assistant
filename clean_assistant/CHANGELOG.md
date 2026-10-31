# Changelog

## 0.32.5
- **Rowenta (backend `robeye`): «Limpieza completa de la casa» usa el mapa guardado.** Antes mandaba
  la orden de limpiar sin mapa: el robot creaba un mapa temporal y al terminar no encontraba la base.
  Ahora limpia todas las habitaciones del mapa guardado, como la app de Rowenta.
- El mapa y la posición del robot se leen del mapa guardado aunque, al empezar a limpiar, el robot
  trabaje unos segundos en uno temporal mientras se sitúa.

## 0.32.4
- **Rowenta (backend `robeye`): la pausa desde Home Assistant ya no se pierde.** Justo después de
  parar, el robot sigue diciendo «limpiando» unos segundos y Clean Assistant olvidaba la pausa; así
  el «iniciar» de HA lanzaba una limpieza completa en vez de continuar.

## 0.32.3
- **Arreglo general: entidades «no disponibles» en Home Assistant tras reiniciar o actualizar el
  add-on.** Si el robot respondía antes de que Clean Assistant se conectara a MQTT, la disponibilidad
  «online» se perdía y se quedaba el «offline» de la instancia anterior. Ahora se republica al conectar.
- **Rowenta (backend `robeye`):**
  - mantenimiento: Clean Assistant cuenta las horas de limpieza de cada pieza (cepillo central,
    cepillo lateral, filtro, mopa) desde que la cambias, con su botón ↺ (también en Home Assistant);
  - totales del robot en Home Assistant: distancia, tiempo y área totales y número de limpiezas;
  - los horarios guardados en el robot se pueden importar a Clean Assistant (se importan
    desactivados, para no limpiar dos veces);
  - la habitación en curso ya no cuenta las que el robot solo atraviesa;
  - el mapa ya no se republica en Home Assistant cada minuto si no ha cambiado;
  - avisos nuevos traducidos a todos los idiomas.

## 0.32.2
- **Rowenta (backend `robeye`):**
  - paredes del mapa bien marcadas (salían casi del color del suelo);
  - historial con los m², los minutos y las habitaciones de cada limpieza (del propio robot), y la
    habitación en curso en el mapa y en Home Assistant;
  - se muestran los horarios guardados en el robot (los de la app de Rowenta);
  - Ajustes sin lo que este robot no tiene: configuración de red/DNS, no molestar, sonido, turbo en
    alfombras, actualizaciones, base de autovaciado y consumibles.

## 0.32.1
- **Rowenta (backend `robeye`), tras la primera prueba con el robot real:**
  - el mapa ya no sale en espejo por defecto (en el Rowenta sale como la casa);
  - la pausa se muestra como «En pausa» (el robot no tiene pausa propia y se quedaba en «Parado»);
  - en Home Assistant: fabricante Rowenta, nombres sin «Conga» y sin las entidades que este robot
    no tiene (agua, mopa, consumibles, autovaciado, volumen, no molestar…).

## 0.32.0
- **Nuevo backend experimental `robeye`: Rowenta X-plorer Serie 80** (y otros robots con plataforma
  RobArt «RobEye»). Habla con la API HTTP local del robot (puerto 8080), sin nube ni DNS: mapa con
  sus habitaciones y zonas de bloqueo, posición en vivo, limpiar todo o por habitaciones, pausa,
  volver a la base, succión, modo bordes y doble pasada («a fondo»), avisos del robot, horarios y
  MQTT/Home Assistant. Los nombres de las habitaciones se guardan en Clean Assistant.
- Opciones nuevas: `BACKEND: robeye` y `ROBOT_IP` (opcional). Si el robot cambia de IP, Clean
  Assistant lo vuelve a encontrar solo en la red y lo reconoce por su identificador.

## 0.31.10
- **Los horarios llevan la categoría y el suelo reales de cada habitación.** Antes se mandaban siempre
  sin categoría (`room_type: 0`) y con suelo por defecto; la app oficial del 3890 manda la categoría
  (p. ej. 2006 = Salón). Puede ser la causa del aviso 522 («falta la mopa») en el 3890 (#14). Hay que
  volver a crear los horarios para que se manden con los datos nuevos.

## 0.31.9
- **Gen. legacy (3xxx/4xxx): succión y agua ya no están intercambiadas.** Al cambiar el agua cambiaba
  la turbina, y la succión no hacía nada. Ahora succión 0–3 y agua 10–13, comprobado de oído por
  @mactron254 en un 4090 (#12).

## 0.31.8
- **3890: horarios sin el aviso 522 («falta la mopa»).** Los horarios (y la limpieza de habitaciones,
  que en este modelo va como horario de un solo uso) se mandan ahora exactamente con la forma de su app
  oficial. Antes llevaban campos que esa app no manda, entre ellos la intensidad de la mopa, y el robot
  esperaba la mopa aunque estuviera en «Off» (#14). Hay que volver a crear los horarios del 3890.

## 0.31.7
- **Se recuerdan Modo, Succión, Agua y Mopa** (y doble pasada / turbo en alfombras) tras reiniciar el
  add-on, y la web muestra los que están activos. Nueva opción `DEFAULT_MODE`. Gracias a @m-l (PR #22).
- **Gen. legacy (3xxx/4xxx): la limpieza completa ya no repite la última habitación.** Tras limpiar
  habitaciones, el robot se quedaba con un plan de solo esas; ahora se reactivan todas antes de
  arrancar (#12, gracias a @mactron254).
- **3890: limpiar habitaciones** programa el horario de un solo uso para el minuto siguiente; puesto
  para el minuto en curso, el robot no llegaba a ejecutarlo (#14).

## 0.31.6
- **Los nombres del mapa ya no se pisan.** Si dos etiquetas se solapan (p. ej. una habitación pequeña
  junto a otra), la de la habitación más pequeña se desplaza al hueco libre más cercano.
- **Actividad:** cambiar de página ya no desplaza el contenido cuando una página es más corta que otra.
- Los avisos antiguos del historial que se guardaron sin texto (p. ej. «Aviso (código 560)») muestran
  ahora su descripción.

## 0.31.5
Gracias a @m-l (PRs #20 y #23):
- **Aviso en Home Assistant si Clean Assistant pierde su conexión MQTT.** Crea una notificación en HA en
  cuanto se cae la conexión con el broker y la quita al restablecerse (no avisa al arrancar ni al parar
  el add-on). El add-on pide ahora acceso a la API de Home Assistant (`homeassistant_api`).
- Los nombres de los planes sugeridos (Solo dormitorios, Solo baños, Limpieza profunda) salen en el
  idioma de la interfaz, y un plan ya añadido no se vuelve a sugerir aunque se cambie de idioma.

## 0.31.4
Gracias a @m-l (#21, PRs #18 y #19):
- **Potencia «Máx» arreglada en la gen. nueva (8090, 6090, 7090, 9090…).** Ese botón enviaba en
  realidad `0`, que en estos robots es **apagar la succión**. Ahora el botón es «Off» de verdad; en la
  gen. legacy (3xxx/4xxx), donde `0` sí es el máximo, sigue diciendo «Máx».
- **Idioma de las entidades de Home Assistant** (Ajustes → Zona de peligro): nombres, opciones de los
  selectores y avisos del robot en los 9 idiomas. Por defecto, español (sin cambios). Al cambiarlo, las
  entidades se recrean con el nombre nuevo; puede afectar a tarjetas y automatizaciones que usen el
  nombre o el texto exacto de una opción.
- Los nombres por defecto de las zonas nuevas salen en el idioma de la interfaz.
- Cambiar el idioma de la interfaz ya no borra la selección de habitaciones y modo de la pestaña
  Limpieza.

## 0.31.3
- **Textos del mapa nítidos.** Los nombres de habitaciones y zonas se pintaban dentro de la imagen del
  mapa, que se escala en modo pixelado (y con el zoom), y se veían pixelados. Ahora van en una capa
  vectorial encima: se ven como texto normal a cualquier zoom.
- **Actividad:** cambiar de página ya no mueve el scroll.

## 0.31.2
- **Los nombres de las habitaciones ya no se mueven al limpiar.** Mientras limpia, el robot marca lo ya
  limpiado de cada habitación como un segmento aparte (id + 50: Dormitorio 10 → 60). Ahora esas celdas
  siguen contando como de su habitación: la etiqueta queda centrada y fija, los m² de cada habitación
  no bajan durante la limpieza y tocar una zona ya limpiada selecciona su habitación.
- **Cabecera del mapa:** los m² y el tiempo son los de la limpieza en curso o, si no hay, los de la
  última del registro de actividad. Antes se guardaban en cada navegador y podían no coincidir.
- **Actividad paginada** (10 por página) y **habitaciones en el orden en que el robot las limpió**
  (las limpiezas ya registradas conservan el orden antiguo).

## 0.31.1
- **Conga 7090: limpiar habitaciones como lo hace su app** (#15, @zjuanma). En el 7090, `setRoomClean`
  funciona solo a veces; la app oficial limpia habitaciones *ejecutando un plan* (`setRoomCleanPlan`),
  que sí es fiable. Clean Assistant hace ahora lo mismo en ese modelo, con la potencia, el agua, la mopa
  y la doble pasada elegidas.
- **Log con fecha y hora** en cada línea.

## 0.31.0
Gracias a la ingeniería inversa de las apps oficiales de @mactron254 (#12):
- **Conga 3890: limpiar habitaciones** (#14). Su app no tiene orden directa: lanza un horario de un
  solo uso que empieza ya (`setOrder6090` con la hora y el día actuales). Clean Assistant hace lo
  mismo en el 3890 y borra ese horario cuando la limpieza termina (o si no arranca en 5 min).
- **Avisos oficiales nuevos** (apps 7090/8090/9090): 529, 533, 534, 550, 551, 559-567 (560 = cepillo
  lateral anormal), 590-596 (estación de autovaciado), 605, 2000 y 2114, en los 9 idiomas.
- **Legacy (3xxx/4xxx): horarios del robot.** Se leen al conectar (`0x10CD` → `0x10CE`) y se muestran en
  «Horarios guardados en el robot» (p. ej. los creados con la app oficial). Solo lectura: no se importan,
  porque el robot ya los ejecuta y Clean Assistant los lanzaría otra vez.
- README: en Cloud + Local, la reescritura DNS debe aplicarse solo al robot (o usar la app con datos
  móviles), porque la app oficial también se conecta a `tcp-cecotec.3irobotix.net`.

## 0.30.1
- **Conga 3890: los horarios ya no piden la mopa** (issue #14, @Here87). La app oficial del 3890 manda
  `cleanmode`/`sweep_mode` = 3 para "Auto"; Clean Assistant mandaba 0 (el "Auto" del 8090) y el 3890
  lo tomaba como un modo con mopa (fault 522). Ahora se usa el valor de cada modelo.
- **Cloud + Local: la lista de horarios ya no parpadea.** La *petición* `getOrder6090` de la nube se
  tomaba como una respuesta vacía del robot ("horarios guardados: 0" / "1"). Ahora las consultas solo
  se leen cuando las contesta el robot.

## 0.30.0
- **Conga 6090: el estado ya no se queda en "desconocido"** (PR #16, gracias @SitoSt). En reposo el
  6090 manda su estado cada ~5 s como `to_bind` con `control: status` en vez de `report_data`, y se
  descartaba: sin batería, sin carga y sin mapa activo durante horas.
- **Mapa nuevo sin guardar en todos los modelos** (issue #17, @SitoSt). Cuando el robot crea un mapa
  temporal (p. ej. tras perderse en una limpieza corta) repite `noticeSaveMap` hasta que se le
  responde, y mientras tanto los nombres de las habitaciones se desordenan. Ahora Clean Assistant lo
  muestra sobre el mapa con **Guardar** (como mapa aparte; no sustituye al actual) o **Descartar**,
  igual que ya hacía en los legacy. Se registra en el log y el aviso desaparece solo si el robot deja
  de pedirlo.

## 0.29.1
- Modo **Cloud + Local**: el log de los comandos de la app oficial (`[cloud]`) ya no se corta a
  220 caracteres (ahora hasta 4000). Así las capturas incluyen los horarios y habitaciones
  completos, necesarios para dar soporte al 3890 (#14) y al 7090 (#15).

## 0.29.0
- **Aviso de limpiar los sensores cada 35 h** (todos los modelos; idea de @mactron254, issue #12):
  CA cuenta las horas limpiando/mapeando desde el último reset (`sensor_care.json`). Fila
  **«Sensores»** en Ajustes → Consumibles con su botón ↺, y en Home Assistant el binary sensor
  **Conga Limpiar sensores** (se enciende a las 35 h), el sensor **Conga Horas desde limpiar
  sensores** y el botón **Conga Sensores limpiados**.
- **Legacy (3xxx/4xxx), corregido con la 2.ª captura de la app oficial** (gracias, @mactron254):
  - **Bordes** usa su propia orden (`0x107F`, modo 25) y **Espiral** la suya (`0x1081`, modo 20);
    antes Bordes enviaba la de Espiral.
  - **Parar** una limpieza de bordes manda además la orden con la que la app la cierra.
  - Pausar/reanudar respeta el modo en curso (fregado, bordes, espiral o automático).
  - Modo **9** (segunda pasada de "ir a un punto") se muestra como limpiando.
  - "Cancelar vuelta a la base" usa la misma parada que el resto.

## 0.28.1
- **Conga 7090** reconocido por su nombre (`project_type` `CECOTECCRL30V-7003`; gracias a @zjuanma,
  issue #13).
- README: id correcto de la entidad del mapa (`image.conga_conga_mapa_imagen`) y ejemplo para
  [vacuum-card](https://github.com/denysdovhan/vacuum-card), probado por @zjuanma.

## 0.28.0
- **El mapa como imagen en Home Assistant** (issue #13, @zjuanma): nueva entidad MQTT `image`
  **«Conga Mapa imagen»** (PNG), lista para tarjetas de imagen o de aspiradora. Mismos colores y
  **misma orientación** que en Clean Assistant (respeta el giro/volteo de la vista). Todos los modelos.
  - El **mapa base** (habitaciones, base, paredes virtuales) solo se publica **cuando cambia** el
    mapa o la vista: ~10 KB, carga prácticamente nula.
  - **Mapa en vivo** opcional, **desactivado por defecto** (Ajustes → Mapas de la casa): añade el
    robot y el recorrido, como mucho cada 30 s y solo mientras limpia. Al terminar vuelve al base.
  - Atributos con la **calibración** píxel ↔ metros (`calibration_points`, 3 puntos), tamaño,
    escala y vista, para tarjetas de mapa interactivas.
  - Sin dependencias nuevas (el PNG se genera a mano); se dibuja en segundo plano.
- **Salud de la batería** (todos los modelos; idea de @mactron254, al estilo de Vacuum_Agent): en
  Ajustes → Consumibles y como sensores de HA (**Ciclos de batería**, **Salud de batería**,
  **Consumo de batería**, **Velocidad de carga**). Lo calcula Clean Assistant con lo que ya reporta
  el robot, sin nada nuevo de protocolo:
  - **Ciclos**: suma de las descargas (100 % = 1 ciclo).
  - **Consumo** por m² y por minuto de cada limpieza (solo las que sirven para medir: sin recargas a
    mitad, ≥5 %, ≥3 m² y ≥5 min).
  - **Velocidad de carga** por debajo del 80 % (rápida) y por encima (lenta).
  - **Salud estimada**: consumo por m² de las 5 primeras limpiezas frente a las 5 últimas; aparece a
    partir de 10 limpiezas válidas. Se guarda en `battery_health.json` (no se borra al vaciar la
    actividad).

## 0.27.1
- **Conga antiguos (backend `legacy`): correcciones con la captura de la APP OFICIAL del 4090**
  (gracias a @mactron254, que decompiló la app y capturó 11 h de uso real). Lo que manda CA es ahora
  idéntico byte a byte a lo que manda la app de Cecotec.
  - **Succión y agua estaban intercambiadas** (la referencia, `@agnoc/core`, las tiene al revés):
    succión = 10 silencio / 11 estándar / 12 turbo / 13 máximo; agua = 0 off … 3 alto. Además, el agua
    llegaba al robot con un valor fuera de rango.
  - **Batería**: el robot la da ×2 (200 = 100 %); antes salía unos puntos por debajo.
  - **Consumibles**: el robot da el % de uso; se convierte a horas como en el resto de modelos.
  - **Actualizaciones automáticas**: ahora sí se controlan (`0x10F3`). Al conectar se dejan
    **apagadas**, como en los demás modelos, salvo que las actives.
  - **Modos Fregado y Bordes** con sus órdenes reales (iniciar y pausar en el modo que toca).
  - CA **retoma el control** del robot cada minuto, como hace la nube.
- **Docker**: el `docker-compose.yml` abre los puertos del modo legacy (4010/4030/4050) y el
  `.env.example` explica `CONGA_BACKEND`.

## 0.27.0
- **Estadísticas totales en la Actividad** (todos los modelos): «Limpiezas en total: N · m² · tiempo»,
  sumando el propio historial (como las estadísticas totales de Valetudo).
- **Conga antiguos (backend `legacy`): cuatro funciones que ya tenía Congatudo**, portadas de `@agnoc/core`:
  - **Ir aquí**: nuevo botón en la barra; tocas un punto del mapa y el robot va y limpia esa zona.
  - **Reiniciar mapa** (Ajustes → Mapas de la casa): el robot borra el mapa y crea uno nuevo en la
    siguiente limpieza.
  - **Mapa nuevo pendiente**: cuando el robot termina un mapa nuevo, aparece un aviso sobre el mapa
    para **guardarlo o descartarlo**.
  - **Mapa persistente** (Ajustes → Robot): activar o desactivar que el robot guarde el mapa.
  - Además, **la red WiFi del robot** (nombre e IP) en Ajustes → Configuración de red.
- Legacy: se oculta el título «Modo de funcionamiento», que quedaba suelto.

## 0.26.1
- **Conga antiguos (backend `legacy`): la interfaz ya no muestra lo que no aplica a esa generación.**
  - Instrucciones de DNS (Ajustes y asistente de primer arranque) con los dominios correctos:
    `cecotec.das.3irobotix.net` para controlar el robot y, para cortar del todo con la nube, los demás
    que redirige Congatudo (OTA, descargas, logs). Antes salían los de la generación nueva.
  - Se ocultan el selector Local / Cloud + Local (el modo cloud no existe en legacy), crear y borrar
    mapas (aún no soportado) y la llave de recuperación (el robot se identifica solo al conectar).
  - Los ajustes de mopa, autovaciado, tipo de base y actualizaciones se mantienen visibles mientras
    se confirma qué tiene cada robot.

## 0.26.0
- **Conga antiguos (backend `legacy`, experimental): horarios.** Esa generación liga cada horario
  a un «plan» de habitaciones compartido en el robot, que no permite los horarios por habitación
  de CA; por eso **los ejecuta Clean Assistant a su hora**, con la misma limpieza por habitaciones
  que «Ejecutar ahora» (validada contra el 4090 real). Salen como «Programada» en el historial.
  Necesita Home Assistant encendido.
- **Legacy: habitaciones y mapas**: renombrar, unir y dividir habitaciones; los mapas guardados en
  el robot aparecen en la lista de mapas y se pueden activar. Aún no: crear un mapa nuevo ni
  borrar mapas (sin referencia fiable del protocolo).
- **Legacy: arreglo de una carrera al conectar**: si el canal del mapa (4030) se registraba antes
  que el de comandos (4010), las órdenes salían por el del mapa. Ahora van siempre por el 4010,
  como hace Congatudo en la captura real.

## 0.25.0
- **Nuevo: soporte EXPERIMENTAL para los Conga antiguos (3090 / 3490 / 4090)** mediante un segundo
  backend, `legacy` (issue #12, gracias a @mactron254). Esa generación habla otro protocolo de
  3irobotix (TCP en claro en 4010/4030/4050, tramas binarias + Protobuf), el de Congatudo, en vez
  del TLS + WebSocket del 9090. Se activa con la nueva opción **`BACKEND: legacy`** y apuntando
  `cecotec.das.3irobotix.net` a Home Assistant. No hace falta rellenar IDs.
  - Portado a Python desde `@agnoc/core` (sin dependencias nuevas; Protobuf decodificado a mano) y
    **validado contra una captura de tráfico real de un 4090**: respuestas, mapa y orden de limpiar
    habitaciones idénticas byte a byte a las reales. Aún sin probar en vivo con un robot.
  - Funciona: estado, batería y avisos; mapa en vivo (habitaciones, robot, base, recorrido, paredes
    virtuales); iniciar/pausar/reanudar/base/localizar; succión y agua; habitaciones; zonas; paredes
    virtuales; mando manual; voz, horario silencioso, alfombras, doble pasada; consumibles. Pendiente:
    horarios y gestión de varios mapas. En HA aparece como «Conga 3xxx/4xxx (legacy)».
  - Arranca sin quedarse esperando la auto-provisión (era el síntoma con el 4090). Si el robot ya
    estuvo con Congatudo, se adoptan sus identificadores y no hace falta re-emparejarlo.
- El dibujado del mapa (`build_map`) se separa del decodificador para compartirlo entre ambas
  generaciones (sin cambios de comportamiento en los modelos actuales).
- README: sección de Conga antiguos y lista de robots completada (6090, 3890).

## 0.24.3
- **Conga 3890** reconocido por su nombre (`project_type` `CECOTECCRL20S-1001`; confirmado por
  @Here87 en el foro de Home Assistant).
- **Guardado de mapa nuevo robusto para todos los modelos**: `setSaveMap` ahora se envía **solo
  cuando el robot está realmente en la base** (`docked`), no al reportar «inactivo». Así el mapa se
  guarda aunque el modelo use un `workMode` de «volviendo» que no reconozcamos (generaliza el
  arreglo del 6090 y soluciona el 3890 reportado por @Here87).

## 0.24.2
- **Arreglo: el Conga 6090 no guardaba el mapa nuevo** (issue #10, @SitoSt). Al terminar de mapear,
  el 6090 reporta `workMode=47` mientras vuelve a la base; se interpretaba como «inactivo» y se
  enviaba `setSaveMap` **antes** de llegar al dock (el robot lo ignoraba). Ahora `workMode=47` =
  «volviendo a la base», así que `setSaveMap` se envía al acoplarse y el mapa se guarda. (Cierra el
  quirk #4 reportado en #9.)

## 0.24.1
- **Conga 6090** reconocido por su nombre (`project_type` `CECOTECCRL30S-1001`; confirmado por
  @Nitrosito, issue #9).
- **Arreglo de estado en el 6090**: `workMode=10` (que el 6090 usa a mitad de limpieza) ya no se
  publica como «inactivo» → ahora «limpiando».
- Descripción y README actualizados: modelos confirmados (4690 / 6090 / 7090 / 9090), 3890
  reportado, y **nota de compatibilidad** (los Conga basados en **Tuya**, como la línea
  **8290 / Immortal**, no están soportados → usar LocalTuya).

## 0.24.0
- **Control manual (mando)**: nuevo botón «Manual» en la barra de controles que despliega un mando
  en la esquina del mapa. Cuatro flechas para mover el robot (adelante / atrás / izquierda /
  derecha) y un **joystick** en el centro: mantén pulsado y arrástralo para conducirlo en cualquier
  dirección, con curvas en diagonal (el robot es de dos ruedas, así que las diagonales son arcos).
  Usa el comando `set_direct` del robot. Se oculta al desactivar el modo manual.

## 0.23.4
- **Nombres de habitación estables** (issue #2, @miajed): a veces el historial de actividad y el
  sensor «Conga Habitación actual» mostraban el ID en crudo (`Hab 15`, `Habitación 20`) en vez del
  nombre. Pasaba porque se resolvían contra el mapa **cargado en ese momento** en lugar del mapa de
  esa limpieza (los IDs se repiten entre mapas), o si el robot reconectaba y el mapa no estaba
  cargado un instante. Ahora Clean Assistant **cachea los nombres por mapa** (persistente), así que
  cada habitación resuelve a su nombre esté activo el mapa que esté.

## 0.23.3
- **Modo oscuro**: la **pestaña activa** (Limpieza / Zonas / Horarios / Actividad / Ajustes) ya se
  distingue con claridad; antes se confundía con el fondo, igual que pasaba con el segmentado.

## 0.23.2
- **Modo oscuro**: el botón activo de los **controles segmentados** (p. ej. Local / Cloud + Local
  en Ajustes, o el modo/potencia/agua) ya se distingue con claridad; antes se confundía con el
  fondo. Completa el ajuste de contraste del issue #1 (gracias @teosoft0).

## 0.23.1
- **Mejor contraste en modo oscuro** (issue #1, @teosoft0): los elementos **seleccionados**
  (habitaciones, chips, filas de zona…) se ven ahora con más claridad en el tema oscuro.

## 0.23.0
- **Diccionario de errores del Conga** (issue #6, gracias @teosoft0; + faultCode 510 de @serra410 en
  el PR #5): **29 códigos** de error/aviso con mensaje entendible, traducidos a los **9 idiomas**
  («Cepillo central bloqueado», «Coloca bien el depósito de agua», «Depósito de polvo lleno»…).
  Nuevo sensor **«Conga Aviso»** en Home Assistant con el aviso/error actual (vacío si no hay
  ninguno), para automatizar notificaciones.
- **Conga 4690 reconocido de verdad** (issue #1, @teosoft0): había un **typo** en el `project_type`
  (`CCECOTECCRL300-1001` con doble C en vez de `CECOTECCRL300-1001`), por el que el 4690 salía como
  «Conga» genérico. Corregido.
- **Estado nada más conectar** (issue #1, @teosoft0): algunos modelos (p. ej. 4690) **no envían
  datos solos al conectar**, así que no aparecían estado, consumibles ni mapa activo hasta forzar un
  cambio de mapa. Ahora Clean Assistant **pide el estado y el mapa justo tras el login**.
- **Modelo y versión reales en la interfaz** (issue #1, @teosoft0): la cabecera muestra el **modelo
  real** del robot y el pie la **versión instalada** (antes estaban fijos a «Conga 8090 Ultra» y
  «v0.17»). La cabecera indica también si el control es **local** o **cloud + local**.
- Home Assistant ya no llena el log con avisos de plantilla `battery_level` mientras aún no hay
  batería.

## 0.22.0
- **Mapa por MQTT para tarjetas de Home Assistant** (issue #2, @miajed): nuevo sensor **«Conga
  Mapa»** que publica la **geometría del mapa** (habitaciones, `bbox`, `world`, robot, base) y la
  **traza del recorrido** como atributos (topic `conga/<node>/map`), para pintar el mapa en
  tarjetas/floorplans propios **sin pasar por el ingress**. NO incluye la rejilla de píxeles (esa
  sigue en `GET /api/map`). Se publica **con margen (throttle de 10 s)** y la traza va
  submuestreada, para no cargar el broker ni el recorder de HA mientras el robot limpia.

## 0.21.1
- **Consumibles sin abrir la app de Cecotec** (issue #1, @teosoft0): en algunas unidades las horas
  de uso de cepillos/filtro/mopa solo aparecían tras abrir la app oficial. Ahora Clean Assistant
  **reintenta pedirlas de forma persistente** (cada ~20 s, hasta que el robot las envíe), así que
  deberían salir solas al conectar.

## 0.21.0
- **Traza del recorrido en el mapa.** Ahora se dibuja por dónde ha ido limpiando (o mapeando) el
  robot: una línea que traza su recorrido en la limpieza actual. Se reinicia al empezar una limpieza
  nueva y se conserva al pausar/reanudar. El recorrido va también en `GET /api/map` (campo `trail`,
  en metros) por si quieres pintarlo en tarjetas o floorplans propios de Home Assistant.

## 0.20.0
- **Cuatro idiomas nuevos en la interfaz: Alemán, Italiano, Neerlandés y Catalán.** Con estos, Clean
  Assistant habla ya **9 idiomas** (ES/EN/DE/IT/FR/PT/NL/CA/PL). Se eligen desde el selector de la
  cabecera y se detecta el del navegador automáticamente. Las traducciones son un primer aporte
  (revisión de hablantes nativos muy bienvenida — abre un issue o PR si ves algo mejorable).

## 0.19.1
- **Diagnóstico de códigos de error.** El registro del add-on ahora anota cada `faultCode` nuevo del
  robot: los conocidos con su mensaje (525 = depósito de agua bajo, 512 = error al volver a la base)
  y los **sin traducir** con un aviso para reportarlos. Así se puede ir construyendo el diccionario
  de errores del Conga con ayuda de la comunidad (se omiten los avisos normales de estación 21xx).

## 0.19.0
- **Ejecutar un plan guardado bajo demanda** (issue #2, sugerido por @miajed): cada horario
  aparece en Home Assistant también como **botón «Ejecutar …»** que lanza **ya** las habitaciones
  de ese plan, sin esperar a su hora. También por REST: `POST /api/schedules/run {"id":"…"}`. Así
  puedes crear los planes en Clean Assistant y dispararlos desde HA sin rehacer la lógica de
  habitaciones. *Nota:* `setRoomClean` no admite ajustes por habitación en una sola orden, así que
  la ejecución bajo demanda aplica la potencia/agua/mopa de la **primera** habitación del plan al
  conjunto; los ajustes por habitación se respetan cuando el horario salta a su **hora**.
- **Habitación actual** (issue #2, sugerido por @miajed): nuevo sensor **«Conga Habitación actual»**
  con el **nombre** de la habitación que el robot está limpiando en ese momento (de
  `cleaning_roomId`). Evita tener que deducirla desde la posición y el mapa.

## 0.18.2
- **Conga 9090 compatible** (issue #3, gracias @serra410): en el 9090 (`project_type`
  `CECOTECCRL350-2001`), iniciar una limpieza reporta `workMode=1`, que el add-on tomaba por
  «inactivo» aunque el robot **sí estaba limpiando** (se movía y el mapa crecía). Ahora `workMode=1`
  se reconoce como **limpiando** y desaparece el aviso `workMode=1 no reconocido`.
- Home Assistant muestra el **modelo real** también para el **Conga 9090** (antes salía genérico).
- La fase de **mapeado** (mapa nuevo) se refleja en HA como **limpiando** en vez de «inactivo»
  (el robot se mueve y limpia mientras construye el mapa; `mapping` no es un estado válido de la
  entidad `vacuum` de HA, así que se presenta como `cleaning`).

## 0.18.1
- **Posición del robot por MQTT** (issue #2, gracias @miajed): nuevo sensor **«Conga Posición»**
  con `x`, `y` y `angle` (en celdas del mapa) como atributos, publicado en
  `conga/conga8090/pose`. Útil para floorplans o tarjetas propias en Home Assistant. Solo cambia
  mientras el robot se mueve (limpiando). El **mapa completo** ya estaba disponible en
  `GET /api/map` (cells_b64, rooms, bbox, robot, charger…).

## 0.18.0
- **Muchísimas menos escrituras en la base de datos de Home Assistant.** El Conga cierra y reabre
  la conexión de control con frecuencia; en cada reconexión las ~35 entidades pasaban a «no
  disponible» y de nuevo a «disponible», generando **miles de filas** en el recorder (cientos de
  miles con el tiempo). Ahora la disponibilidad tiene un **margen (debounce) de 120 s**: un corte
  breve ya no la hace parpadear, así que el estado se mantiene estable y solo se registran los
  cambios reales.
  - Para vaciar lo ya acumulado: en *Ajustes → Sistema → Almacenamiento* (o el panel del recorder),
    pulsa **Purge**, o llama al servicio `recorder.purge` / `recorder.purge_entities`.

## 0.17.11
- Home Assistant muestra ahora el **modelo real** del robot (según su `project_type`, aprendido
  del propio robot): **Conga 8090 Ultra**, **Conga 4690 Ultra**, etc., en vez de siempre
  «Conga 8090». Atiende parte del issue #1 (gracias @teosoft0, que tiene un 4690). Otros modelos
  no mapeados aún aparecen como «Conga» con su project_type.

## 0.17.10
- Pie de la app: el enlace **☕ Ko-fi** pasa a su **propia línea** (antes se descuadraba/partía en
  móvil). Sigue traducido en todos los idiomas.

## 0.17.9
- **Arreglado:** las **actualizaciones automáticas (OTA)** volvían a activarse tras cada
  actualización del add-on. El robot las reactiva al reconectar; ahora Clean Assistant **guarda tu
  preferencia y la reaplica** automáticamente. Por defecto quedan **OFF** (recomendado en local);
  si las activas tú, se respetan. (La protección real ya existía: el servidor OTA local siempre
  responde «sin actualización», así que el robot nunca se actualizaba de todos modos.)
- Añadida la **licencia MIT** del proyecto (`LICENSE`), con aviso de ingeniería inversa
  independiente (no afiliado a Cecotec/3irobotix).

## 0.17.8
- Enlace de apoyo **☕ Ko-fi** en el pie de la app (junto al de GitHub), traducido a todos los
  idiomas, y botón **Sponsor** en el repositorio (`.github/FUNDING.yml`). Totalmente opcional.

## 0.17.7
- **Arreglado (issue #1, gracias @teosoft0):** los horarios con **ñ, tildes o espacios** en el
  nombre generaban un topic de descubrimiento MQTT ilegal y Home Assistant lo **rechazaba**
  («Received message on illegal discovery topic … contains non allowed characters»). Ahora el
  identificador del topic se **sanea** (`[a-zA-Z0-9_-]`); el nombre visible del horario no cambia.
- **Home Assistant: nueva "Frecuencia de vaciado"** (selector), igual que en la web
  (Nunca / Después de cada limpieza / Cada 30·60·90 min / Cada 2 h).
- **Home Assistant: se publican solo los horarios del MAPA ACTIVO** (como la web) y se **retiran
  automáticamente** los botones de habitación y switches de horario **obsoletos** (de mapas de
  prueba, de otros mapas o de nombres cambiados) que antes quedaban como entidades fantasma.

## 0.17.6
- Arreglado el **"Conga fantasma"** en Home Assistant: aparecía un segundo dispositivo *Conga
  8090* con solo los 4 botones de *Restablecer* consumibles. Causa: al aprender el DID real del
  robot (auto-provisión), la limpieza del dispositivo antiguo no retiraba esos botones de reset.
  Ahora se limpian, y al arrancar se eliminan las identidades antiguas (conga_0/123456/entorno).
  Tras actualizar y reconectar, el dispositivo duplicado desaparece solo.
- El pie de la interfaz enlaza al **repositorio de GitHub** (github.com/miguelsg29/clean-assistant).

## 0.17.5
- La imagen precompilada se publica para **aarch64 y amd64** (las de Home Assistant OS en
  Raspberry Pi 3/4/5 y equipos x86). Se retira **armv7** (ARM de 32 bits): sus dependencias
  (pydantic-core en Rust, uvloop…) no tienen binarios para esa arquitectura y habría que
  compilarlas desde fuente, algo que tampoco funcionaba bien en el modelo anterior.

## 0.17.4
- Arreglado el build de CI para **armv7** (el builder oficial de HA está obsoleto y rechazaba esa
  arquitectura). Ahora la imagen se compila con **docker buildx** para las 3 arquitecturas
  (aarch64/amd64/armv7). Sin cambios de funcionamiento.

## 0.17.3
- **Actualizaciones más rápidas y con barra de progreso.** El add-on ahora usa una **imagen
  precompilada** (GitHub Actions la construye para cada arquitectura y la publica en GHCR), en
  vez de compilarse en tu Raspberry en cada actualización. Home Assistant la **descarga** →
  updates en segundos, con progreso real, y sin fallos de compilación en el dispositivo.
- Sin cambios de funcionamiento respecto a 0.17.2.

## 0.17.2
- Arreglada la **frecuencia de vaciado** («Después de cada limpieza», etc.), que se perdía cada
  vez que se actualizaba el add-on. El robot no siempre responde a la consulta de este ajuste, así
  que ahora se **guarda en local** (`prefs.json`) y se restaura al arrancar (el robot conserva su
  propio ajuste; esto conserva lo que se muestra). Lo mismo para el **tipo de base**.
- Nuevo **valor por defecto** de la frecuencia de vaciado: **«Después de cada limpieza»** cuando
  hay **colector automático** (y «Nunca» con base de carga simple), en vez de quedar en «Nunca».

## 0.17.1
- **Añadido el polaco (pl)** a la interfaz multiidioma: ahora son **5 idiomas** (español,
  inglés, portugués, francés y polaco), seleccionables desde la cabecera. Cumple la petición
  de @m-l (fork *conga-8090-home-assistant-EN-PL*), que ya había traducido al polaco.

## 0.17.0
- **Multiidioma (i18n): español, inglés, portugués y francés.** Toda la interfaz se traduce,
  con un selector de idioma en la cabecera (arriba a la derecha). Detecta el idioma del
  navegador la primera vez y recuerda tu elección. Los datos tuyos (nombres de habitaciones,
  mapas y horarios) no se traducen; los avisos del robot y los días del historial, sí.
  - Gracias a la idea de @m-l (fork *conga-8090-home-assistant-EN-PL*) de añadir más idiomas.
- Detalle técnico: las cadenas se traducen por texto-origen en español (fuente de la verdad);
  los valores de los comandos van desacoplados de la etiqueta visible (`data-v`), así que
  traducir la interfaz nunca cambia lo que se le manda al robot.

## 0.16.35
- Horarios: arreglado que las limpiezas programadas se disparaban con DESFASE (p. ej. 2 h más
  tarde en verano). Causa: la imagen del add-on (Alpine) no incluía `tzdata`, así que aplicar la
  zona horaria de Home Assistant no surtía efecto y el contenedor se quedaba en UTC; el reloj del
  robot acababa en UTC y un horario de las 11:00 disparaba a las 13:00 (CEST). Ahora se instala
  `tzdata` y el log del add-on muestra el offset aplicado (`[tz] ... (offset +120 min)`) para
  poder verificarlo. Tras actualizar, el arreglo se aplica al reconectar el robot (o reinícialo).

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
