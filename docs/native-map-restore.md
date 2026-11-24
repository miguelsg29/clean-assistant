# Recuperar los planos de una Conga 4090

En **Ajustes → Mapas de la casa → Copia nativa del mapa del robot** puedes copiar los archivos de navegación al servidor mientras el plano está bien. Si el robot los pierde, el panel permite devolverle esa copia. Una exportación JSON del dibujo no recupera la navegación. Para recuperar la navegación necesitas haber creado **una copia nativa antes de la pérdida**.

## Configurar el acceso

Esta función experimental admite la 4090 con backend `legacy`, producto interno `CECOTECCRL300` y versión de sistema `S3.3.8`. Exige una cuenta SSH ya autorizada en tu robot, con acceso de lectura y escritura a los archivos de mapas. El servidor comprueba la clave de host y la identidad de la unidad. La contraseña del router y la sesión de la aplicación Android sirven para otros servicios.

1. Localiza el **slug completo del complemento instalado** en Home Assistant, por ejemplo mediante `ha addons list`. Incluye el prefijo del repositorio: instalaciones desde un fork y desde el repositorio original pueden tener slugs diferentes aunque ambas terminen en `_clean_assistant`. No copies el prefijo de otra instalación. Abre la carpeta de configuraciones de complementos que expone tu instalación. El recurso compartido puede aparecer como `addon_configs` y Supervisor puede almacenarlo bajo `app_configs`. Dentro de ese recurso crea `<slug_completo_real>/native-ssh/`. Comprueba que has abierto la carpeta del complemento correcto. Home Assistant Core tiene su propia carpeta de configuración. El montaje `addon_config` expone esa carpeta dentro del complemento como `/config`, por lo que el directorio interno es `/config/native-ssh`.
2. Deja exactamente estos cuatro archivos de configuración SSH en `native-ssh`: `config`, `id_conga` (clave privada), `id_conga.pub` (su clave pública, ya autorizada en el robot) y `known_hosts`. La clave pública se conserva como referencia; el transporte utiliza la privada. El usuario del proceso debe poder leerlos. En Linux, usa `0700` para el directorio y `0600` para `config`, `id_conga` y `known_hosts`; `id_conga.pub` puede ser `0644`. No publiques estos archivos ni los añadas al repositorio.
3. Obtén y verifica la huella de la clave de host por un canal de confianza antes de incluirla en `known_hosts`. `ssh-keyscan` puede recopilar una clave candidata, pero no autentica por sí solo al robot: compara su huella con una obtenida de manera independiente. Conserva `StrictHostKeyChecking yes`; no uses `StrictHostKeyChecking no` ni `UserKnownHostsFile /dev/null`.
4. Crea `native-ssh/config`. Sustituye la IP reservada para documentación y el usuario del ejemplo por los de tu unidad. El alias debe llamarse `conga-map`.

```sshconfig
Host conga-map
    HostName 192.0.2.10
    User cuenta_autorizada
    IdentityFile /config/native-ssh/id_conga
    UserKnownHostsFile /config/native-ssh/known_hosts
    IdentitiesOnly yes
    BatchMode yes
    StrictHostKeyChecking yes
```

5. En la configuración del complemento, selecciona `BACKEND: legacy`, activa el booleano `NATIVE_MAPS_ENABLED`, reinicia el complemento y abre su interfaz mediante Ingress de Home Assistant. El arranque fija automáticamente `NATIVE_MAP_SSH_CONFIG=/config/native-ssh/config`. No añadas `NATIVE_MAP_SSH_CONFIG` como opción del complemento: su esquema expone el booleano. La Conga debe haber comunicado su identidad, su versión y su estado en la conexión actual.

### Instalación independiente

Aquí se configura una variable de entorno con una **ruta absoluta dentro del entorno donde se ejecuta el backend**; el booleano del complemento no interviene. Por ejemplo:

```sh
export CONGA_MODE=real
export CONGA_BACKEND=legacy
export DATA_DIR=/var/lib/clean-assistant
export NATIVE_MAP_SSH_CONFIG=/etc/clean-assistant/native-ssh/config
```

Usa un `DATA_DIR` privado y persistente. Conserva los mismos cuatro archivos y permisos; adapta `IdentityFile` y `UserKnownHostsFile` del bloque anterior a `/etc/clean-assistant/native-ssh/id_conga` y `/etc/clean-assistant/native-ssh/known_hosts`. En Docker, monta el directorio SSH privado en esa ruta dentro del contenedor, preferiblemente de solo lectura, y pasa la variable al contenedor. Una ruta que solo exista en el host no basta. Abre la interfaz a través de una conexión local a `localhost` en el entorno donde se ejecuta el servidor, mediante un túnel SSH si es remoto. Inicia Uvicorn con `--no-proxy-headers`, como en las imágenes incluidas.

### Diagnosticar la configuración sin escribir en el robot

Abre **Actualizar estado** en el panel nativo. La consulta `GET api/maps/native/status`, relativa a la URL del backend bajo Ingress, devuelve `configured`, `available`, `backup_available` y los motivos de bloqueo. Puedes verla en la pestaña Red del navegador dentro de la sesión de Ingress; no sustituyas su prefijo por una URL pública `/api/...`. En una instalación independiente usa, por ejemplo, `GET http://localhost:8000/api/maps/native/status` desde una conexión local. Un acceso LAN directo recibe 403 por diseño.

`configured: true` solo confirma que existe el archivo de configuración; esta consulta no abre SSH ni prueba las claves. `available` comprueba conexión, identidad comunicada y estado de carga; `backup_available` exige además un mapa completo de la sesión actual. Para comprobar el transporte autorizado, crea una copia con el robot en su base: esa operación lee los archivos del robot y guarda la copia en el servidor, sin reemplazar archivos del robot. Un error SSH puede indicar permisos, clave de host, autorización o algoritmos incompatibles; el API oculta stderr y los datos privados. Revisa esos puntos desde el servidor sin desactivar la verificación de host.

Si aparece `Robot registration identity is incomplete; reconnect the robot`, el backend sigue esperando que la Conga comunique su identificador y su versión de firmware en la sesión actual. Puedes tener acceso SSH y ver el plano en directo mientras la copia sigue bloqueada. Con el robot en la base, deja que vuelva a conectarse y pulsa **Actualizar estado**. Si persiste el aviso, revisa los mensajes de registro del backend antes de intentar una copia.

## Guardar y recuperar

1. Con el robot en la base y cargando, espera a que llegue el plano en directo. Comprueba las habitaciones y pulsa **Crear copia nativa**. Esto lee el robot y guarda los datos en el servidor. Se incluye el conjunto de planos guardados porque comparten índice y archivos de navegación.
2. Si se pierde el plano, deja la Conga en la base y espera a que vuelva a informar que está cargando. Selecciona la copia por fecha y plano activo, pulsa **Restaurar copia nativa** y confirma el reemplazo. Se admite que falten el índice o los archivos de mapas actuales. Un archivo de mapa adicional que solo exista en el robot, o un cambio del marcador de vinculación, requiere revisión antes de continuar.
3. Espera al mensaje de escritura verificada antes de reiniciar la Conga de forma normal. Evita iniciar una limpieza durante la operación. Cuando vuelva a conectarse y envíe su plano, pulsa **Actualizar estado**. El panel compara el identificador y la geometría con la copia. Revisa en el mapa las habitaciones, la base y las restricciones antes de volver a limpiar.

## Dónde quedan las copias

El servidor conserva hasta 20 copias nativas en `DATA_DIR/native-map-backups/`. Incluyen planos privados de la casa. Al alcanzar el límite, un administrador puede archivar fuera de ese directorio el archivo `<id>.json` correspondiente a una copia antigua para dejar sitio. Conserva el directorio completo al hacer una copia de seguridad del servidor, incluido su `index.json`.

El robot usa una lista cerrada de archivos en `/mnt/UDISK/log`, con el índice, los esquemas de los planos y los archivos de navegación que estén presentes. Antes de escribir comprueba que hay espacio libre y conserva los originales y la lista de archivos ausentes en un directorio privado `.conga-map-<id>`. Tras comprobar el resultado, el administrador puede archivar ese directorio y retirar del robot la transacción completada para permitir otra restauración. Una restauración interrumpida requiere revisar la transacción y cualquier bloqueo pendiente. Un corte de corriente puede dejar algunos archivos reemplazados porque el robot los cambia de uno en uno.

La implementación se ha probado con archivos y sesiones simulados. La comprobación en disco y la comparación del plano en directo son independientes de que el firmware pueda navegar físicamente por las habitaciones. [Documentación de archivos de Congatudo](https://congatudo.cloud/misc/important-files-and-folders/) · [Inventario de una copia de mapas de Conga](https://gist.github.com/gtrabanco/2732d40bc709d21360ebb6faadad5af4)

## Estado experimental y bloqueo conocido

Una captura de solo lectura de los archivos nativos mediante SSH se ha completado en una Conga 4090 real. Esa captura se realizó fuera del complemento: su archivo ZIP no es una copia creada por esta interfaz. La interfaz guarda JSON privados con bytes base64, hashes e identidad; no importa ZIP ni acepta esa captura externa como copia restaurable. En otra prueba, el transporte del propio complemento de Home Assistant autenticó la unidad con la clave configurada y leyó dos veces los seis archivos de navegación con contenido idéntico. El panel seguía esperando la identidad de registro de la sesión. Queda pendiente validar la creación de la copia desde la interfaz.

La restauración física no se ha probado. La unidad de fábrica comprobada dispone de BusyBox y `md5sum`, pero no de `sha256sum` ni `openssl`. Esta implementación exige `sha256sum` remoto y bloquea la restauración antes de preparar o reemplazar archivos si falta, con el error `Robot lacks sha256sum; native restore is blocked before staging or replacing files`. No hay alternativa automática con MD5. Por ello, esta propuesta debe permanecer en borrador hasta validar una solución segura y la restauración física.

El servidor SSH de esa unidad requiere compatibilidad explícita por host. Si los diagnósticos de tu conexión autorizada indican que lo necesita, añade únicamente dentro del bloque `Host conga-map` de su configuración privada:

```sshconfig
    HostKeyAlgorithms +ssh-rsa
    MACs +hmac-sha1
```

Si además la autenticación con la clave RSA autorizada falla porque el servidor solo acepta firmas RSA/SHA-1, añade `PubkeyAcceptedAlgorithms +ssh-rsa` en ese mismo bloque, únicamente si es necesario. Esta opción controla la firma de autenticación del usuario; `HostKeyAlgorithms` controla la clave del servidor. No cambies los algoritmos globales del cliente ni uses un bloque `Host *` para estas excepciones. Mantén la verificación estricta de la clave de host. Las pruebas automatizadas usan datos sintéticos y no contactan con ningún robot.
