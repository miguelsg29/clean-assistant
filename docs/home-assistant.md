# Clean Assistant in Home Assistant: extras

[Español](home-assistant.es.md)

Ready-made pieces to get more out of Clean Assistant in Home Assistant: **automation
blueprints**, **map cards** and **voice commands**. Everything is local and works with any robot
Clean Assistant supports.

> Entity IDs below (`vacuum.conga_conga`, `image.conga_conga_mapa_imagen`…) are examples: yours
> depend on the robot's name and the entity language (installs from v0.36.1 on get shorter ones,
> e.g. `image.conga_8090_mapa_imagen`). Look them up in
> *Settings → Devices & services → MQTT → your robot*.

---

## 1. Blueprints

Click a button to import it into your Home Assistant, then create an automation from it
(*Settings → Automations → Blueprints*).

| Blueprint | What it does | Import |
|---|---|---|
| **Clean when everyone leaves** | Starts the robot when nobody is home (after a delay, inside a time window and on the days you pick, at most once a day). Can clean the whole house, a room or a saved plan, and sends the robot back to the dock when someone comes home. | [![Import](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fmiguelsg29%2Fclean-assistant%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fclean_assistant%2Fclean_when_away.yaml) |
| **Notify when the robot needs help** | A notification on your phone when the robot reports a warning (stuck, dustbin full, mop missing, low water…) or goes into error. The text is Clean Assistant's, in your language. Optional extra actions (e.g. announce it on a speaker). | [![Import](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fmiguelsg29%2Fclean-assistant%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fclean_assistant%2Fnotify_attention.yaml) |
| **Consumables reminder** | Reminds you to replace brushes, filter or mop below a threshold (10 % by default) and, optionally, to clean the sensors every 35 h. Repeats once a day until you reset it. | [![Import](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fmiguelsg29%2Fclean-assistant%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fclean_assistant%2Fconsumables_reminder.yaml) |

To clean **several rooms** from an automation, create a schedule with those rooms in Clean
Assistant: each one gets a **"Run …"** button in Home Assistant that you can pick in the blueprint.

---

## 2. Map cards

Clean Assistant publishes the map as an `image` entity (**Mapa imagen**). With **Settings →
House maps → Live map in Home Assistant** turned on, the image also shows the robot and its path
while cleaning, refreshed every 5–30 s (you choose).

### Simple map

```yaml
type: picture-entity
entity: image.conga_conga_mapa_imagen
show_state: false
show_name: false
```

### Map with a robot marker that moves right away

The **Position** sensor has `x_pct` and `y_pct` attributes: the robot's position as a percentage
of the map image, with your view's rotation/flip already applied. It updates every time the
robot reports its position, without waiting for the image. A core `picture-elements` card can't
use templates in `style`, so this uses
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

Leave the live map **off** with this card if you want the static image without the robot
drawn on it: the marker is enough.

### Room buttons on the map

Add one element per room, placed by hand (percentages of the image), that presses the room's
button:

```yaml
type: picture-elements
image_entity: image.conga_conga_mapa_imagen
elements:
  - type: icon
    icon: mdi:broom
    title: Kitchen
    style:
      left: 30%
      top: 55%
    tap_action:
      action: perform-action
      perform_action: button.press
      target:
        entity_id: button.conga_limpiar_cocina
```

### Calibration for other map cards

The image entity's `calibration_points` attribute gives 3 points with their position in metres
(`vacuum`) and in image pixels (`map`), and the **Map** sensor has the room geometry, the robot,
the dock and the path. Map cards that accept manual calibration points can use them.

---

## 3. Voice commands (Assist)

**Built in:** Home Assistant already understands commands like *"start the vacuum"* or
*"return the vacuum to the dock"* for Clean Assistant's `vacuum` entity.

**Clean one room** (*"clean the kitchen"*, *"limpia la cocina"*): two files.

1. Copy [`assist/custom_sentences/en/clean_assistant.yaml`](../assist/custom_sentences/en/clean_assistant.yaml)
   to `<config>/custom_sentences/en/` (for Spanish, the `es` one to `<config>/custom_sentences/es/`).
2. Add the `CleanAssistantRoom` block from [`assist/intent_script.yaml`](../assist/intent_script.yaml)
   to `configuration.yaml` and restart Home Assistant.

It looks for the Clean Assistant button whose name ends with the room you said ("Clean Kitchen")
and presses it, so new rooms work with no extra setup. *"Clean the whole house"* works too.
