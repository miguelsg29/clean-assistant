# Clean Assistant en Home Assistant: extras

[English](home-assistant.md)

Piezas listas para sacar más partido a Clean Assistant en Home Assistant: **blueprints de
automatización**, **tarjetas de mapa** y **órdenes de voz**. Todo en local y con cualquier robot
compatible con Clean Assistant.

> Los ID de entidad de abajo (`vacuum.conga_conga`, `image.conga_conga_mapa_imagen`…) son
> ejemplos: los tuyos dependen del nombre del robot y del idioma de las entidades. Búscalos en
> *Ajustes → Dispositivos y servicios → MQTT → tu robot*.

---

## 1. Blueprints

Pulsa un botón para importarlo en tu Home Assistant y crea una automatización a partir de él
(*Ajustes → Automatizaciones → Blueprints*).

| Blueprint | Qué hace | Importar |
|---|---|---|
| **Limpiar cuando salgáis todos** | Arranca el robot cuando no queda nadie en casa (tras una espera, dentro de una franja horaria y los días que elijas, como mucho una vez al día). Puede limpiar toda la casa, una habitación o un plan guardado, y lo manda a la base cuando alguien vuelve. | [![Importar](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fmiguelsg29%2Fclean-assistant%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fclean_assistant%2Fclean_when_away.yaml) |
| **Avisar cuando el robot necesita ayuda** | Una notificación en el móvil cuando el robot da un aviso (atascado, depósito lleno, falta la mopa, poca agua…) o entra en error. El texto es el de Clean Assistant, en tu idioma. Acciones extra opcionales (p. ej. anunciarlo en un altavoz). | [![Importar](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fmiguelsg29%2Fclean-assistant%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fclean_assistant%2Fnotify_attention.yaml) |
| **Recordatorio de consumibles** | Recuerda cambiar cepillos, filtro o mopa por debajo de un umbral (10 % por defecto) y, si quieres, limpiar los sensores cada 35 h. Se repite una vez al día hasta que lo restableces. | [![Importar](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fmiguelsg29%2Fclean-assistant%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fclean_assistant%2Fconsumables_reminder.yaml) |

Para limpiar **varias habitaciones** desde una automatización, crea un horario con ellas en Clean
Assistant: cada uno tiene un botón **«Ejecutar …»** en Home Assistant que puedes elegir en el
blueprint.

Los blueprints están en inglés (es lo que pide Home Assistant para compartirlos); los avisos que
envían salen en el idioma de tus entidades.

---

## 2. Tarjetas de mapa

Clean Assistant publica el mapa como una entidad `image` (**Mapa imagen**). Con **Ajustes → Mapas
de la casa → Mapa en vivo en Home Assistant** activado, la imagen muestra también el robot y su
recorrido mientras limpia, cada 5–30 s (lo eliges tú).

### Mapa sencillo

```yaml
type: picture-entity
entity: image.conga_conga_mapa_imagen
show_state: false
show_name: false
```

### Mapa con un marcador del robot que se mueve al momento

El sensor **Posición** tiene los atributos `x_pct` y `y_pct`: la posición del robot en % de la
imagen del mapa, con el giro/volteo de tu vista ya aplicado. Se actualiza cada vez que el robot
informa su posición, sin esperar a la imagen. La tarjeta `picture-elements` de serie no admite
plantillas en `style`, así que se usa
[config-template-card](https://github.com/iantrich/config-template-card) (HACS):

```yaml
type: custom:config-template-card
entities:
  - sensor.conga_conga_posicion
card:
  type: picture-elements
  image_entity: image.conga_conga_mapa_imagen
  elements:
    - type: icon
      icon: mdi:robot-vacuum
      style:
        left: ${states['sensor.conga_conga_posicion'].attributes.x_pct + '%'}
        top: ${states['sensor.conga_conga_posicion'].attributes.y_pct + '%'}
        color: white
        background: "#1565c0"
        border-radius: 50%
        padding: 4px
```

Con esta tarjeta puedes dejar el mapa en vivo **apagado** si prefieres la imagen fija sin el robot
dibujado: el marcador ya basta.

### Botones de habitación sobre el mapa

Un elemento por habitación, colocado a mano (en % de la imagen), que pulsa su botón:

```yaml
type: picture-elements
image_entity: image.conga_conga_mapa_imagen
elements:
  - type: icon
    icon: mdi:broom
    title: Cocina
    style:
      left: 30%
      top: 55%
    tap_action:
      action: perform-action
      perform_action: button.press
      target:
        entity_id: button.conga_limpiar_cocina
```

### Calibración para otras tarjetas de mapa

El atributo `calibration_points` de la imagen da 3 puntos con su posición en metros (`vacuum`) y
en píxeles de la imagen (`map`), y el sensor **Mapa** tiene la geometría de las habitaciones, el
robot, la base y el recorrido. Las tarjetas de mapa que aceptan puntos de calibración manuales
pueden usarlos.

---

## 3. Órdenes de voz (Assist)

**De serie:** Home Assistant ya entiende órdenes como *«inicia la aspiradora»* o *«manda la
aspiradora a la base»* con la entidad `vacuum` de Clean Assistant.

**Limpiar una habitación** (*«limpia la cocina»*, *«pasa la aspiradora por el salón»*): dos archivos.

1. Copia [`assist/custom_sentences/es/clean_assistant.yaml`](../assist/custom_sentences/es/clean_assistant.yaml)
   a `<config>/custom_sentences/es/` (en inglés, el de `en` a `<config>/custom_sentences/en/`).
2. Añade el bloque `CleanAssistantRoom` de [`assist/intent_script.yaml`](../assist/intent_script.yaml)
   a `configuration.yaml` y reinicia Home Assistant.

Busca el botón de Clean Assistant cuyo nombre acaba en la habitación que has dicho («Limpiar
Cocina») y lo pulsa, así que las habitaciones nuevas funcionan sin configurar nada. También vale
*«limpia toda la casa»*.
