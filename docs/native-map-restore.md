# Recuperar los planos de una Conga 4090

En **Ajustes → Mapas de la casa → Copia nativa del mapa del robot** puedes copiar los archivos de navegación al servidor mientras el plano está bien. Si el robot los pierde, el panel permite devolverle esa copia. Una exportaci?n JSON del dibujo no recupera la navegaci?n. Para recuperar la navegación necesitas haber creado **una copia nativa antes de la pérdida**.

## Configurar el acceso

Esta función experimental admite la 4090 con backend `legacy`, producto interno `CECOTECCRL300` y versión de sistema `S3.3.8`. Exige una cuenta SSH ya autorizada en tu robot, con acceso de lectura y escritura a los archivos de mapas. El servidor comprueba la clave de host y la identidad de la unidad. La contraseña del router y la sesión de la aplicación Android sirven para otros servicios.

1. En la carpeta de configuración **del complemento** de Home Assistant, crea el directorio `native-ssh`. Dentro del complemento estará en `/config/native-ssh`.
2. Coloca en ese directorio la clave privada correspondiente a la clave pública autorizada en la Conga y el archivo `known_hosts` con la clave de host del robot, cuya huella hayas verificado por un canal de confianza. Usa permisos privados para el directorio y la clave (en Linux, `0700` y `0600`, respectivamente).
3. Crea `native-ssh/config`. Sustituye la IP de ejemplo y el usuario por los de tu unidad. El alias debe llamarse `conga-map`.

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

4. En la configuración del complemento, selecciona `BACKEND: legacy`, activa `NATIVE_MAPS_ENABLED`, reinicia el complemento y abre su interfaz desde Home Assistant. La Conga debe haber comunicado su identidad, su versión y su estado en la conexión actual. Algunos servidores SSH antiguos requieren algoritmos específicos. Comprueba la compatibilidad del cliente con tu conexión autorizada antes de crear la primera copia.

En una instalación independiente, configura `CONGA_MODE=real`, `CONGA_BACKEND=legacy`, un `DATA_DIR` privado y persistente, y `NATIVE_MAP_SSH_CONFIG` con la ruta del archivo de configuración SSH. Para estas operaciones abre la interfaz a través de una conexión local a `localhost` en el entorno donde se ejecuta el servidor. Inicia Uvicorn con `--no-proxy-headers`, como en las imágenes incluidas.

## Guardar y recuperar

1. Con el robot en la base y cargando, espera a que llegue el plano en directo. Comprueba las habitaciones y pulsa **Crear copia nativa**. Esto lee el robot y guarda los datos en el servidor. Se incluye el conjunto de planos guardados porque comparten índice y archivos de navegación.
2. Si se pierde el plano, deja la Conga en la base y espera a que vuelva a informar que está cargando. Selecciona la copia por fecha y plano activo, pulsa **Restaurar copia nativa** y confirma el reemplazo. Se admite que falten el índice o los archivos de mapas actuales. Un archivo de mapa adicional que solo exista en el robot, o un cambio del marcador de vinculación, requiere revisión antes de continuar.
3. Espera al mensaje de escritura verificada antes de reiniciar la Conga de forma normal. Evita iniciar una limpieza durante la operación. Cuando vuelva a conectarse y envíe su plano, pulsa **Actualizar estado**. El panel compara el identificador y la geometría con la copia. Revisa en el mapa las habitaciones, la base y las restricciones antes de volver a limpiar.

## Dónde quedan las copias

El servidor conserva hasta 20 copias nativas en `DATA_DIR/native-map-backups/`. Incluyen planos privados de la casa. Al alcanzar el límite, un administrador puede archivar fuera de ese directorio el archivo `<id>.json` correspondiente a una copia antigua para dejar sitio. Conserva el directorio completo al hacer una copia de seguridad del servidor, incluido su `index.json`.

El robot usa una lista cerrada de archivos en `/mnt/UDISK/log`, con el índice, los esquemas de los planos y los archivos de navegación que estén presentes. Antes de escribir comprueba que hay espacio libre y conserva los originales y la lista de archivos ausentes en un directorio privado `.conga-map-<id>`. Tras comprobar el resultado, el administrador puede archivar ese directorio y retirar del robot la transacción completada para permitir otra restauración. Una restauración interrumpida requiere revisar la transacción y cualquier bloqueo pendiente. Un corte de corriente puede dejar algunos archivos reemplazados porque el robot los cambia de uno en uno.

La implementación se ha probado con archivos y sesiones simulados. La comprobación en disco y la comparación del plano en directo son independientes de que el firmware pueda navegar físicamente por las habitaciones. [Documentación de archivos de Congatudo](https://congatudo.cloud/misc/important-files-and-folders/) · [Inventario de una copia de mapas de Conga](https://gist.github.com/gtrabanco/2732d40bc709d21360ebb6faadad5af4)

## Estado experimental y bloqueo conocido

Una captura de los archivos nativos mediante SSH se ha completado en una Conga 4090 real. Esa captura se realiz? fuera del complemento: su archivo ZIP no es una copia creada por esta interfaz. La interfaz guarda JSON privados con bytes base64, hashes e identidad; no importa ZIP ni acepta esa captura externa como copia restaurable.

La restauraci?n f?sica no se ha probado. La unidad de f?brica comprobada dispone de BusyBox y `md5sum`, pero no de `sha256sum` ni `openssl`. Esta implementaci?n exige `sha256sum` remoto y bloquea la restauraci?n antes de preparar o reemplazar archivos si falta, con el error `Robot lacks sha256sum; native restore is blocked before staging or replacing files`. No hay alternativa autom?tica con MD5. Por ello, esta propuesta debe permanecer en borrador hasta validar una soluci?n segura y la restauraci?n f?sica.

El cliente SSH de esa unidad requiere compatibilidad expl?cita por host. Si tu unidad lo necesita, a?ade ?nicamente dentro del bloque `Host conga-map` de su configuraci?n privada:

```sshconfig
    HostKeyAlgorithms +ssh-rsa
    MACs +hmac-sha1
```

Mant?n la verificaci?n estricta de la clave de host y no habilites estos algoritmos globalmente. Las pruebas automatizadas usan datos sint?ticos y no contactan con ning?n robot.
