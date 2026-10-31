"""Puente MQTT opcional: expone el robot en Home Assistant (autodiscovery).

A diferencia del puente clásico (`conga_mqtt_bridge.py`), este NO abre un segundo
servidor TLS+WS en el 9090: se monta ENCIMA del `RealRobot` ya existente como un
consumidor más (igual que la web). Publica el estado a HA cuando el robot cambia y
traduce los comandos de HA a `robot.command(...)`. Así la web y HA conviven con una
sola conexión al robot.

Se activa solo si `MQTT_HOST` está definido (en `.env` o entorno). Si no, no hace nada,
por lo que el modo de desarrollo (mock, sin broker) sigue funcionando igual.
"""
from __future__ import annotations
import json
import re
import threading
import time

# Margen antes de anunciar "offline" en HA. El Conga cierra y reabre la conexión de control muy a
# menudo; sin este margen cada reconexión marcaría las ~35 entidades como no disponibles y otra vez
# disponibles, generando MILES de escrituras en la BD del recorder. Con el margen, un hueco corto no
# hace parpadear la disponibilidad.
AVAIL_OFFLINE_GRACE_S = 120.0

from conga_core import commands as cmd
from backend.i18n import t, VALID_LANGS

# Estados válidos del esquema 'state' de la entidad vacuum de HA (schema: state). HA SOLO acepta
# estos seis; 'mapping' NO es válido (HA lo rechaza con "Received unsupported state"), por eso el
# mapeado interno se publica como 'cleaning' (ver publish_state): el robot se mueve y limpia mientras
# construye el mapa, así que 'cleaning' es lo correcto de cara a HA.
_VACUUM_STATES = {"cleaning", "docked", "paused", "idle", "returning", "error"}

# Frecuencia de autovaciado: nombre visible en HA <-> valor del robot (set_preference 16).
DUST_FREQ = {"Nunca": -1, "Después de cada limpieza": 0, "Cada 30 minutos": 30,
             "Cada 60 minutos": 60, "Cada 90 minutos": 90, "Cada 2 horas": 120}
DUST_FREQ_REV = {v: k for k, v in DUST_FREQ.items()}

# ---------------- etiquetas (ES) de las opciones de los `select`, por idioma (i18n) ----------------
# La CLAVE de cada entrada sigue siendo la que espera conga_core.commands (lo que viaja al robot);
# el VALOR es el texto en español que se le pasa a t() para traducirlo a mostrar en HA.
#
# "Off" en succión (conga_core.commands.FAN["Off"]=0) es "apagar de verdad" SOLO en el backend
# "new" (conga_core/commands.py, confirmado por ingeniería inversa sobre el propio 8090: se manda
# set_preference(1, 0) tal cual). En el backend "legacy" NO lo es: conga_core/legacy/robot.py
# remapea ese mismo 0 a 13 ("máximo" en la tabla real capturada de la app oficial) antes de
# mandarlo al robot, así que ahí sí es un nivel de potencia más, no un apagado. Antes esta
# etiqueta decía "Máx" para los dos backends (copiado del error que tenía la propia interfaz web,
# ver backend/static/index.html); en el backend nuevo eso hacía que elegir "Máx" apagara
# realmente la succión. Ver MqttBridge.legacy / self._fan_labels (__init__).
FAN_LABELS_NEW = {"Off": "Off", "Eco": "Eco", "Normal": "Normal", "Turbo": "Turbo"}
FAN_LABELS_LEGACY = {"Off": "Máx", "Eco": "Eco", "Normal": "Normal", "Turbo": "Turbo"}
WATER_LABELS = {"Off": "Off", "Bajo": "Bajo", "Medio": "Medio", "Alto": "Alto"}
MOP_LABELS = {"Off": "Off", "Estándar": "Estándar", "Fuerte": "Fuerte", "Potente": "Potente"}
CLEAN_MODE_LABELS = {"Auto": "Auto", "Limpieza completa": "Limpieza completa",
                      "Fregado": "Fregado", "Bordes": "Bordes", "Espiral": "Espiral",
                      "Espiral cuadrada": "Espiral cuadrada", "Punto": "Punto"}
BASE_TYPE_LABELS = {"Base de carga": "Base de carga", "Colector automático": "Colector automático"}
DUST_FREQ_LABELS = {k: k for k in DUST_FREQ}


# Modelo del robot para Home Assistant, según el project_type (aprendido del propio robot por
# auto-provisión, o el configurado). (nombre corto, modelo). Amplía el mapa según se confirmen.
CONGA_MODELS = {
    "CECOTECCRL350-1001": ("Conga 8090", "Conga 8090 Ultra"),
    "CECOTECCRL300-1001": ("Conga 4690", "Conga 4690 Ultra"),    # confirmado por @teosoft0 (issue #1)
    "CECOTECCRL350-2001": ("Conga 9090", "Conga 9090"),          # confirmado por @serra410 (issue #3)
    "CECOTECCRL30S-1001": ("Conga 6090", "Conga 6090"),          # confirmado por @Nitrosito (issue #9)
    "CECOTECCRL20S-1001": ("Conga 3890", "Conga 3890"),          # confirmado por @Here87 (foro HA)
    "CECOTECCRL30V-7003": ("Conga 7090", "Conga 7090"),          # confirmado por @zjuanma (issue #13)
}


def _safe_id(s) -> str:
    """El object_id de los topics de descubrimiento MQTT solo admite [a-zA-Z0-9_-]; HA rechaza
    'ñ', tildes o espacios (p. ej. un horario llamado 'Baño matrimonio'). Sustituye lo no
    permitido por '_'. Se usa SOLO en el segmento del topic de descubrimiento; los topics de
    comando/estado pueden llevar el id real."""
    return re.sub(r"[^a-zA-Z0-9_-]", "_", str(s))


def _min_to_hhmm(mins) -> str:
    try:
        m = int(mins)
    except (TypeError, ValueError):
        return "00:00"
    return f"{(m // 60) % 24:02d}:{m % 60:02d}"


def _hhmm_to_min(hhmm) -> int:
    h, m = str(hhmm).split(":")
    return int(h) * 60 + int(m)


class MqttBridge:
    """Puente Home Assistant. `rooms_provider` devuelve {room_id: {'name': ...}}
    (habitaciones del mapa vivo); `map_head_id` es un callable -> int."""

    def __init__(self, robot, schedules, env, map_head_id, rooms_provider, log=print,
                 persist=None):
        self.robot = robot
        self.schedules = schedules
        self._map_head_id = map_head_id
        self._rooms = rooms_provider
        # ver el comentario sobre FAN_LABELS_NEW/FAN_LABELS_LEGACY: el significado real de
        # FAN["Off"] depende del backend (nuevo = apagado real; legacy = remapeado a "máximo").
        # robeye (Rowenta…) usa la misma tabla: su «Off» también es el nivel máximo
        self.legacy = (env("CONGA_BACKEND", "new") or "new").lower() in ("legacy", "robeye")
        self._fan_labels = FAN_LABELS_LEGACY if self.legacy else FAN_LABELS_NEW
        self.log = log
        self._persist = persist        # callback opcional para persistir prefs (frecuencia/base)
        self.host = env("MQTT_HOST")
        self.port = int(env("MQTT_PORT", "1883") or 1883)
        self.user = env("MQTT_USER")
        self.password = env("MQTT_PASS") or env("MQTT_PASSWORD")
        self._env_did = env("ROBOT_DID", "123456")
        self.node = "conga8090"
        self.uid = self._current_uid()
        self._published_uid = None
        self._legacy_cleaned = False   # limpieza única de "Congas fantasma" de identidades antiguas
        self._avail_state = None        # disponibilidad publicada ("online"/"offline")
        self._avail_timer = None        # temporizador de gracia antes de anunciar offline
        self._map_pub_ts = 0.0          # último publish del mapa por MQTT (para acotar frecuencia)
        # imagen del mapa (entidad `image`): la base solo cuando cambia; en vivo (robot + recorrido)
        # solo si el usuario lo activa, mientras limpia y como mucho cada MAP_IMAGE_LIVE_S
        self.map_image_live = False     # preferencia (prefs.json), OFF por defecto
        self.view_provider = None       # callback -> {"rot", "flip"} (la vista de la interfaz)
        self._img_sig = None            # firma de la última imagen BASE publicada
        self._img_live_ts = 0.0         # última imagen EN VIVO publicada
        self._img_was_live = False      # la última publicada llevaba robot/recorrido
        self._img_busy = threading.Lock()
        self.battery_provider = None    # callback -> resumen de salud de batería (backend/battery.py)
        self.sensors_provider = None    # callback -> aviso de limpieza de sensores (backend/sensors.py)
        self.sensors_reset = None       # callback -> 'Hecho' (sensores limpios)
        self._sensors_last = None
        self._battery_last = None
        self.lang_provider = None       # callback -> código de idioma ('es','en',...), ver backend/i18n.py
        self._opt_reverse = {}          # {clave select: {opción traducida -> clave canónica}}, por idioma actual
        self.ha_notify_provider = None  # callback(connected: bool) -> avisa a HA de la propia
                                         # conexión MQTT de la app (distinto de la disponibilidad
                                         # del ROBOT, que ya lleva su propio margen -- ver
                                         # _update_availability). Sin margen: un automatismo que
                                         # observe la entidad de disponibilidad no se entera si la
                                         # app se cae y reconecta rápido; esto avisa al instante.
        self._mqtt_was_up = False       # para no avisar "restablecida" en la primera conexión
        self._mqtt_ever_connected = False  # distingue "primer arranque" de "reconexión tras caída"
        self._stopping = False          # True durante stop(): no avisar de una desconexión buscada
        self.disc = "homeassistant"
        self.client = None
        # preferencias "para la próxima limpieza" (sombra local: el robot no las reporta)
        self.prefs = {
            "fan": env("DEFAULT_FAN", "Normal"), "water": env("DEFAULT_WATER", "Medio"),
            "mop": env("DEFAULT_MOP", "Estándar"), "twice": False,
            "mode": env("DEFAULT_MODE", "Auto"), "base_type": "Base de carga", "turbo_carpet": False,
        }
        self.t_state = f"conga/{self.node}/state"
        self.t_cmd = f"conga/{self.node}/command"
        self.t_avail = f"conga/{self.node}/availability"

    def _current_uid(self) -> str:
        """Identidad del dispositivo en HA. Usa el DID REAL del robot (capturado por
        auto-provisión o del .env), no el del entorno del add-on (que es 0). Así el
        add-on y las pruebas del PC convergen en UN solo Conga y no salen duplicados."""
        if getattr(self.robot, "robeye", False):   # sin DID: un único robot RobEye por instalación
            return "robeye"
        did = getattr(getattr(self.robot, "cfg", None), "did", 0) or 0
        if did in (0, 123456):
            did = self._env_did
        return f"conga_{did}"

    def _model_names(self):
        """(nombre, modelo) del dispositivo para HA según el project_type del robot. Para modelos
        no mapeados usa un nombre genérico 'Conga' e incluye el project_type crudo en el modelo."""
        if getattr(self.robot, "robeye", False):   # Rowenta X-plorer y demás RobArt «RobEye»
            cap = getattr(self.robot, "captured", {}) or {}
            fw = cap.get("firmware") or ""
            model = "Rowenta X-plorer Serie 80" if fw.startswith("SER80") else "RobEye"
            return (cap.get("name") or "Robot", f"{model} ({fw.split('-release')[0]})" if fw else model)
        if getattr(self.robot, "legacy", False):   # gen. 3xxx/4xxx: no reporta project_type
            return ("Conga", "Conga 3xxx/4xxx (legacy)")
        pt = (getattr(getattr(self.robot, "cfg", None), "project_type", "") or "").strip()
        if pt in CONGA_MODELS:
            return CONGA_MODELS[pt]
        return ("Conga", f"Conga ({pt})" if pt else "Conga")

    def _lang(self) -> str:
        """Idioma actual para las etiquetas publicadas en HA ('es' por defecto). Viene de
        `lang_provider` (backend/app.py lo conecta a la preferencia persistida, la misma que
        elige el selector de idioma de la interfaz web -- issue pedido por m-l)."""
        try:
            lang = self.lang_provider() if self.lang_provider else None
        except Exception:
            lang = None
        return lang if lang in VALID_LANGS else "es"

    def _localized_options(self, canon_labels: dict):
        """De {clave_canónica: texto_es} (self._fan_labels, WATER_LABELS...) construye, en el idioma
        actual, la lista de `options` a publicar en HA y el mapa inverso {opción_traducida ->
        clave_canónica} que _on_message necesita para volver a la clave que entiende
        conga_core.commands cuando HA manda de vuelta el valor elegido."""
        lang = self._lang()
        options, reverse = [], {}
        for key, es_label in canon_labels.items():
            label = t(lang, es_label)
            options.append(label)
            reverse[label] = key
        return options, reverse

    def enabled(self) -> bool:
        return bool(self.host)

    # ---------------- ciclo de vida ----------------
    def start(self):
        if not self.enabled():
            return
        import paho.mqtt.client as mqtt
        try:
            self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                                      client_id=f"{self.uid}_ca")
        except (AttributeError, TypeError):        # respaldo paho 1.x
            self.client = mqtt.Client(client_id=f"{self.uid}_ca")
        if self.user:
            self.client.username_pw_set(self.user, self.password or None)
        self.client.will_set(self.t_avail, "offline", retain=True)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        self.client.connect_async(self.host, self.port, 60)
        self.client.loop_start()
        self.log(f"[MQTT] puente HA activo -> {self.host}:{self.port}")

    def stop(self):
        self._stopping = True           # distingue esta desconexión buscada de una caída real
        if self._avail_timer is not None:
            self._avail_timer.cancel()
            self._avail_timer = None
        if self.client:
            try:
                self.client.publish(self.t_avail, "offline", retain=True)
                self.client.loop_stop()
                self.client.disconnect()
            except Exception:
                pass

    # ---------------- helpers de publicación ----------------
    def _pub(self, topic, payload, retain=True):
        if self.client:
            self.client.publish(topic, payload, retain=retain)

    # entidades del Conga que no existen en un RobEye (Rowenta…): no se publican (y se retiran)
    ROBEYE_SKIP = ("_low_water", "_cons_", "_creset_", "_sel_water", "_sel_mop", "_sel_base_type",
                   "_volume", "_quiet", "_voice", "_ota", "_dust", "_turbo_carpet")

    def _disc(self, comp, obj, cfg):
        if getattr(self.robot, "robeye", False):
            if any(k in obj for k in self.ROBEYE_SKIP):
                self._pub(f"{self.disc}/{comp}/{obj}/config", "")
                return
            if isinstance(cfg.get("name"), str) and cfg["name"].startswith("Conga "):
                cfg["name"] = cfg["name"][len("Conga "):]      # «Batería», no «Conga Batería»
        cfg.setdefault("availability_topic", self.t_avail)
        cfg.setdefault("payload_available", "online")
        cfg.setdefault("payload_not_available", "offline")
        cfg.setdefault("device", {"identifiers": [self.uid]})
        self._pub(f"{self.disc}/{comp}/{obj}/config", json.dumps(cfg))

    # ---------------- autodiscovery ----------------
    def publish_discovery(self):
        if not self.client:
            return
        node = self.node
        uid = self._current_uid()
        # si el DID cambió (p. ej. tras la auto-provisión pasó de conga_0 al DID real),
        # borra el descubrimiento retenido del anterior para no dejar un Conga duplicado.
        if self._published_uid and self._published_uid != uid:
            self._clear_discovery(self._published_uid)
        self.uid = uid
        self._published_uid = uid
        # elimina "Congas fantasma" de identidades antiguas: antes de la auto-provisión el DID
        # podía ser 0/123456/el del entorno. Una versión previa no retiraba sus botones de reset
        # y dejaba un segundo dispositivo con solo esos 4 botones. Se limpia una vez por arranque.
        if not self._legacy_cleaned:
            self._legacy_cleaned = True
            for legacy in {"conga_0", "conga_123456", f"conga_{self._env_did}"} - {uid}:
                self._clear_discovery(legacy)
        lang = self._lang()
        dev_name, dev_model = self._model_names()
        device = {"identifiers": [uid], "name": dev_name,
                  "manufacturer": "Rowenta" if getattr(self.robot, "robeye", False) else "Cecotec",
                  "model": dev_model, "sw_version": "clean-assistant"}
        self._disc("vacuum", node, {
            "name": dev_name, "unique_id": uid, "schema": "state",
            "supported_features": ["start", "pause", "stop", "return_home",
                                   "status", "locate"],
            "command_topic": self.t_cmd, "state_topic": self.t_state, "device": device})

        # sensores
        for name, sid, topic, tmpl, unit, dclass in (
            (f"Conga {t(lang, 'Batería')}", "bat", self.t_state,
             "{% if value_json.battery_level is defined %}{{ value_json.battery_level }}{% endif %}",
             "%", "battery"),
            (f"Conga {t(lang, 'Área limpiada')}", "area", f"conga/{node}/area", "{{ value }}", "m²", None),
            (f"Conga {t(lang, 'Tiempo limpieza')}", "time", f"conga/{node}/time", "{{ value }}", "min", "duration"),
        ):
            cfg = {"name": name, "unique_id": f"{uid}_{sid}", "state_topic": topic,
                   "value_template": tmpl}
            if unit:
                cfg["unit_of_measurement"] = unit
            if dclass:
                cfg["device_class"] = dclass
            self._disc("sensor", f"{uid}_{sid}", cfg)
        # posición del robot (x/y/ángulo en celdas del mapa) para floorplans/tarjetas externas.
        # El estado es "x,y"; x, y y angle van también como atributos (json_attributes_topic).
        self._disc("sensor", f"{uid}_pose", {
            "name": f"Conga {t(lang, 'Posición')}", "unique_id": f"{uid}_pose",
            "state_topic": f"conga/{node}/pose",
            "value_template": "{{ value_json.x }},{{ value_json.y }}",
            "json_attributes_topic": f"conga/{node}/pose", "icon": "mdi:crosshairs-gps"})
        self.publish_pose()
        # habitación que el robot está limpiando ahora (nombre), para tarjetas/automatizaciones.
        self._disc("sensor", f"{uid}_room_now", {
            "name": f"Conga {t(lang, 'Habitación actual')}", "unique_id": f"{uid}_room_now",
            "state_topic": f"conga/{node}/room_now", "icon": "mdi:home-map-marker"})
        self._pub(f"conga/{node}/room_now", self._current_room_name())
        # mapa (geometría + traza) para tarjetas/floorplans de HA. Estado = nº de habitaciones
        # (estable); habitaciones/bbox/world/robot/base/traza van como atributos. Se publica con
        # margen (throttle) para no llenar el recorder mientras el robot limpia. SIN la rejilla de
        # píxeles (esa sigue en GET /api/map).
        self._disc("sensor", f"{uid}_map", {
            "name": f"Conga {t(lang, 'Mapa')}", "unique_id": f"{uid}_map",
            "state_topic": f"conga/{node}/map",
            "value_template": "{{ (value_json.rooms | default([])) | length }}",
            "json_attributes_topic": f"conga/{node}/map", "icon": "mdi:floor-plan"})
        self.publish_map(force=True)
        # el mapa como IMAGEN (PNG), para tarjetas de imagen/aspiradora; con la calibración
        # píxel <-> metros en los atributos (tarjetas de mapa interactivas)
        self._disc("image", f"{uid}_map_image", {
            "name": f"Conga {t(lang, 'Mapa imagen')}", "unique_id": f"{uid}_map_image",
            "image_topic": f"conga/{node}/map_image", "content_type": "image/png",
            "json_attributes_topic": f"conga/{node}/map_image/attr", "icon": "mdi:map"})
        self.publish_map_image(force=True)
        # aviso de falta de agua (faultCode 525) como binary_sensor
        self._disc("binary_sensor", f"{uid}_low_water", {
            "name": f"Conga {t(lang, 'Falta agua')}", "unique_id": f"{uid}_low_water",
            "state_topic": self.t_state, "value_template": "{{ value_json.low_water }}",
            "payload_on": "ON", "payload_off": "OFF",
            "device_class": "problem", "icon": "mdi:water-alert"})
        # aviso/error actual del robot (texto entendible del diccionario de faultCode), vacío si
        # no hay ninguno. Para automatizar notificaciones en HA (issue #6).
        # salud de la batería (calculada por CA a partir del historial de cargas y limpiezas)
        bt = f"conga/{node}/battery_health"
        for key, name, unit, icon, tpl in (
                ("bh_cycles", f"Conga {t(lang, 'Ciclos de batería')}", None, "mdi:battery-sync", "{{ value_json.cycles }}"),
                ("bh_health", f"Conga {t(lang, 'Salud de batería')}", "%", "mdi:battery-heart-variant",
                 "{{ value_json.health if value_json.health is not none else 'unknown' }}"),
                ("bh_drain", f"Conga {t(lang, 'Consumo de batería')}", "%/m²", "mdi:battery-arrow-down",
                 "{{ value_json.pct_per_m2 if value_json.pct_per_m2 is not none else 'unknown' }}"),
                ("bh_charge", f"Conga {t(lang, 'Velocidad de carga')}", "%/min", "mdi:battery-charging",
                 "{{ value_json.charge_rate_low if value_json.charge_rate_low is not none else 'unknown' }}")):
            cfg = {"name": name, "unique_id": f"{uid}_{key}", "state_topic": bt,
                   "value_template": tpl, "json_attributes_topic": bt, "icon": icon}
            if unit:
                cfg["unit_of_measurement"] = unit
            if key == "bh_cycles":
                cfg["state_class"] = "total_increasing"
            self._disc("sensor", f"{uid}_{key}", cfg)
        self._battery_last = None
        self.publish_battery()
        # aviso de limpieza de sensores (cada 35 h de trabajo; lo cuenta CA, vale para todos)
        sc = f"conga/{node}/sensor_care"
        self._disc("sensor", f"{uid}_sensor_hours", {
            "name": f"Conga {t(lang, 'Horas desde limpiar sensores')}", "unique_id": f"{uid}_sensor_hours",
            "state_topic": sc, "value_template": "{{ value_json.hours }}",
            "json_attributes_topic": sc, "unit_of_measurement": "h", "icon": "mdi:eye-refresh"})
        self._disc("binary_sensor", f"{uid}_sensor_due", {
            "name": f"Conga {t(lang, 'Limpiar sensores')}", "unique_id": f"{uid}_sensor_due",
            "state_topic": sc, "value_template": "{{ 'ON' if value_json.due else 'OFF' }}",
            "payload_on": "ON", "payload_off": "OFF",
            "device_class": "problem", "icon": "mdi:eye-refresh"})
        self._disc("button", f"{uid}_sensor_reset", {
            "name": f"Conga {t(lang, 'Sensores limpiados')}", "unique_id": f"{uid}_sensor_reset",
            "command_topic": f"{sc}/reset", "payload_press": "reset", "icon": "mdi:restart"})
        self._sensors_last = None
        self.publish_sensors()
        self._disc("sensor", f"{uid}_warning", {
            "name": f"Conga {t(lang, 'Aviso')}", "unique_id": f"{uid}_warning",
            "state_topic": f"conga/{node}/warning", "icon": "mdi:alert"})
        # el valor publicado aquí (no solo el nombre/icono de la entidad) debe traducirse: es el
        # texto que ve el usuario como estado del sensor "Conga Aviso" (ver WARN_MESSAGES en
        # conga_core/state.py y el bloque de traducciones correspondiente en backend/i18n.py).
        self._pub(f"conga/{node}/warning", t(lang, getattr(self.robot.state, "warning", None) or ""))
        for key, name, icon in (("main_brush", "Cepillo central", "mdi:broom"),
                                ("side_brush", "Cepillo lateral", "mdi:broom"),
                                ("filter", "Filtro", "mdi:air-filter"),
                                ("dishcloth", "Mopa", "mdi:water")):
            label = t(lang, name)
            self._disc("sensor", f"{uid}_cons_{key}", {
                "name": f"Conga {label}", "unique_id": f"{uid}_cons_{key}",
                "state_topic": f"conga/{node}/consumable/{key}",
                "unit_of_measurement": "%", "icon": icon})
            self._disc("button", f"{uid}_creset_{key}", {
                "name": f"Conga {t(lang, 'Restablecer')} {label}", "unique_id": f"{uid}_creset_{key}",
                "command_topic": f"conga/{node}/consumable/{key}/reset",
                "payload_press": key, "icon": "mdi:restart"})

        # botones de limpieza por habitación (del mapa vivo). El nombre de la habitación es
        # DATO del usuario y no se traduce (igual que en la web); solo "Limpiar"/"Habitación".
        for rid, meta in (self._rooms() or {}).items():
            rname = (meta or {}).get("name") or f"{t(lang, 'Habitación')} {rid}"
            self._disc("button", f"{uid}_room_{rid}", {
                "name": f"{t(lang, 'Limpiar')} {rname}", "unique_id": f"{uid}_room_{rid}",
                "command_topic": f"conga/{node}/room_command", "payload_press": str(rid),
                "icon": "mdi:broom"})

        # selectores: potencia / agua / mopa / modo / tipo de base. Las OPCIONES se traducen,
        # pero la clave canónica que entiende conga_core.commands se guarda en _opt_reverse
        # para poder volver a ella cuando HA manda de vuelta el valor elegido (_on_message).
        for key, name, labels, icon in (
            ("fan", "Potencia succión", self._fan_labels, "mdi:fan"),
            ("water", "Nivel agua", WATER_LABELS, "mdi:water"),
            ("mop", "Vibración mopa", MOP_LABELS, "mdi:vibrate"),
            ("mode", "Modo de limpieza", CLEAN_MODE_LABELS, "mdi:broom"),
            ("base_type", "Tipo de base", BASE_TYPE_LABELS, "mdi:home-import-outline"),
        ):
            opts, reverse = self._localized_options(labels)
            self._opt_reverse[key] = reverse
            self._disc("select", f"{uid}_sel_{key}", {
                "name": f"Conga {t(lang, name)}", "unique_id": f"{uid}_sel_{key}",
                "command_topic": f"conga/{node}/pref/{key}/set",
                "state_topic": f"conga/{node}/pref/{key}", "options": opts, "icon": icon})
            self._pub(f"conga/{node}/pref/{key}", t(lang, labels.get(self.prefs[key], self.prefs[key])))

        # switches: doble pasada, turbo alfombras, no molestar, voz, OTA
        for key, name, icon in (("twice", "Doble pasada (x2)", "mdi:repeat"),
                                ("turbo_carpet", "Turbo en alfombras", "mdi:rug"),
                                ("quiet", "No molestar", "mdi:sleep"),
                                ("voice", "Voz", "mdi:account-voice"),
                                ("ota", "Actualizaciones automáticas", "mdi:cloud-download")):
            self._disc("switch", f"{uid}_{key}", {
                "name": f"Conga {t(lang, name)}", "unique_id": f"{uid}_{key}",
                "command_topic": f"conga/{node}/{key}/set",
                "state_topic": f"conga/{node}/{key}",
                "payload_on": "on", "payload_off": "off", "icon": icon})
        self._pub(f"conga/{node}/twice", "on" if self.prefs["twice"] else "off")
        self._pub(f"conga/{node}/turbo_carpet", "on" if self.prefs["turbo_carpet"] else "off")

        # number: volumen de voz; text: horas de no molestar
        self._disc("number", f"{uid}_volume", {
            "name": f"Conga {t(lang, 'Volumen voz')}", "unique_id": f"{uid}_volume",
            "command_topic": f"conga/{node}/voice_volume/set",
            "state_topic": f"conga/{node}/voice_volume",
            "min": 0, "max": 10, "step": 1, "icon": "mdi:volume-high"})
        for part, name, icon in (("begin", "No molestar inicio", "mdi:weather-night"),
                                ("end", "No molestar fin", "mdi:weather-sunny")):
            self._disc("text", f"{uid}_quiet_{part}", {
                "name": f"Conga {t(lang, name)}", "unique_id": f"{uid}_quiet_{part}",
                "command_topic": f"conga/{node}/quiet_{part}/set",
                "state_topic": f"conga/{node}/quiet_{part}",
                "pattern": "^([01][0-9]|2[0-3]):[0-5][0-9]$", "icon": icon})

        # botón: vaciar base
        self._disc("button", f"{uid}_dust", {
            "name": f"Conga {t(lang, 'Vaciar base')}", "unique_id": f"{uid}_dust",
            "command_topic": f"conga/{node}/dust_action", "payload_press": "1",
            "icon": "mdi:delete-empty"})

        # select: frecuencia de autovaciado (igual que en la web)
        opts, reverse = self._localized_options(DUST_FREQ_LABELS)
        self._opt_reverse["dust_freq"] = reverse
        self._disc("select", f"{uid}_dust_freq", {
            "name": f"Conga {t(lang, 'Frecuencia de vaciado')}", "unique_id": f"{uid}_dust_freq",
            "command_topic": f"conga/{node}/dust_freq/set",
            "state_topic": f"conga/{node}/dust_freq",
            "options": opts, "icon": "mdi:delete-clock"})
        self._pub_dust_freq()

        # horarios: un switch por plan del MAPA ACTIVO (igual que la web). El object_id del topic
        # de descubrimiento se SANEA (HA no admite ñ/tildes/espacios); los topics de comando y
        # estado llevan el id real. Los horarios de otros mapas / ya borrados se retiran de HA
        # en _sweep_stale() (barrido de configs retenidas al conectar).
        active = getattr(self.robot.state, "map_head_id", None)
        active_plans = self.schedules.for_map(active)
        for p in active_plans:
            pid = p["id"]
            obj = f"{uid}_sched_{_safe_id(pid)}"
            self._disc("switch", obj, {
                "name": f"{t(lang, 'Horario')} {p.get('name', pid)}", "unique_id": obj,
                "command_topic": f"conga/{node}/sched/{pid}/set",
                "state_topic": f"conga/{node}/sched/{pid}",
                "payload_on": "on", "payload_off": "off", "icon": "mdi:calendar-clock"})
            self._pub(f"conga/{node}/sched/{pid}", "on" if p.get("enable", True) else "off")
            # botón "Ejecutar": lanza YA las habitaciones del plan (sin esperar a su hora).
            run_obj = f"{uid}_planrun_{_safe_id(pid)}"
            self._disc("button", run_obj, {
                "name": f"{t(lang, 'Ejecutar')} {p.get('name', pid)}", "unique_id": run_obj,
                "command_topic": f"conga/{node}/plan_run", "payload_press": pid,
                "icon": "mdi:play-box-multiple"})

        self.publish_state()
        self.log(f"[MQTT] autodiscovery publicado ({len(self._rooms() or {})} hab., "
                 f"{len(active_plans)} horario(s) del mapa activo)")

    def _clear_discovery(self, uid: str):
        """Borra el descubrimiento retenido de un dispositivo viejo (uid distinto al
        actual) publicando payload vacío en cada topic de config -> HA lo elimina."""
        objs = [("sensor", f"{uid}_bat"), ("sensor", f"{uid}_area"),
                ("sensor", f"{uid}_time"), ("sensor", f"{uid}_pose"),
                ("sensor", f"{uid}_room_now"), ("sensor", f"{uid}_map"), ("image", f"{uid}_map_image"),
                ("sensor", f"{uid}_bh_cycles"), ("sensor", f"{uid}_bh_health"),
                ("sensor", f"{uid}_bh_drain"), ("sensor", f"{uid}_bh_charge"),
                ("sensor", f"{uid}_sensor_hours"), ("binary_sensor", f"{uid}_sensor_due"),
                ("button", f"{uid}_sensor_reset"),
                ("sensor", f"{uid}_warning"),
                ("number", f"{uid}_volume"), ("button", f"{uid}_dust"),
                ("select", f"{uid}_dust_freq"), ("binary_sensor", f"{uid}_low_water")]
        for key in ("main_brush", "side_brush", "filter", "dishcloth"):
            objs.append(("sensor", f"{uid}_cons_{key}"))
            objs.append(("button", f"{uid}_creset_{key}"))   # botones de reset (faltaban -> dejaban un device fantasma)
        for rid in (self._rooms() or {}):
            objs.append(("button", f"{uid}_room_{rid}"))
        for key in ("fan", "water", "mop", "mode", "base_type"):
            objs.append(("select", f"{uid}_sel_{key}"))
        for key in ("twice", "turbo_carpet", "quiet", "voice", "ota"):
            objs.append(("switch", f"{uid}_{key}"))
        for part in ("begin", "end"):
            objs.append(("text", f"{uid}_quiet_{part}"))
        for p in self.schedules.plans:
            objs.append(("switch", f"{uid}_sched_{_safe_id(p['id'])}"))
            objs.append(("button", f"{uid}_planrun_{_safe_id(p['id'])}"))
        for comp, obj in objs:
            self._pub(f"{self.disc}/{comp}/{obj}/config", "")
        self.log(f"[MQTT] retirado descubrimiento duplicado ({uid})")

    def republish_with_rename(self):
        """Como publish_discovery(), pero primero BORRA el descubrimiento retenido del uid
        ACTUAL antes de volver a publicarlo (ver _clear_discovery, pensado originalmente solo
        para uids viejos/duplicados). Hace falta porque Home Assistant NO actualiza el nombre
        visible de una entidad MQTT ya registrada solo porque llegue un nuevo discovery con
        "name" distinto -- se queda con el nombre con el que se creó hasta que la entidad se
        borra/recrea, o se reinicia HA (comportamiento conocido de core, p. ej.
        github.com/home-assistant/core/issues/99936). Se usa al cambiar el idioma de las
        entidades (ver /api/prefs/lang); un simple publish_discovery() ahí dejaría los nombres
        antiguos pegados hasta el próximo reinicio de HA, que es justo el síntoma reportado."""
        if not self.client:
            return
        self._clear_discovery(self._current_uid())
        self.publish_discovery()

    def note_web_command(self, action, p):
        """Sincroniza la sombra de preferencias en HA cuando el cambio viene de la web. Sigue
        actualizando self.prefs y persistiendo aunque no haya MQTT configurado (MQTT_HOST vacío)
        -- antes el "if not self.client: return" de aquí arriba cortaba esto en seco, así que sin
        MQTT un cambio desde la web ni se guardaba ni sobrevivía al siguiente broadcast de estado
        (review PR #22, @miguelsg29). _pub() ya es un no-op sin client, así que no hace falta
        guardia extra para las publicaciones de abajo."""
        node, v = self.node, p.get("value")
        if action in ("fan", "water", "mop", "mode", "base_type"):
            self.prefs[action] = v
            # publicar la opción TRADUCIDA, no la clave canónica -- las options del select ya
            # están traducidas (_localized_options en publish_discovery), así que mandar la
            # clave cruda hace que HA la rechace por no ser una de sus opciones válidas (en
            # inglés, p. ej.) o, en el backend legacy, incluso en español ("Off" cuando la
            # opción publicada es "Máx"). Mismo patrón que _pub_dust_freq(). (review PR #18)
            labels = {"fan": self._fan_labels, "water": WATER_LABELS, "mop": MOP_LABELS,
                      "mode": CLEAN_MODE_LABELS, "base_type": BASE_TYPE_LABELS}[action]
            self._pub(f"conga/{node}/pref/{action}", t(self._lang(), labels.get(v, v)))
        elif action == "twice":
            self.prefs["twice"] = bool(v)
            self._pub(f"conga/{node}/twice", "on" if v else "off")
        elif action == "carpet_turbo":
            self.prefs["turbo_carpet"] = bool(v)
            self._pub(f"conga/{node}/turbo_carpet", "on" if v else "off")
        elif action == "dust_freq":
            self._pub_dust_freq()   # el estado ya está en robot.state.collect_freq
            return
        # persiste también cuando el cambio viene de la propia web (antes solo quedaba en
        # memoria: se perdía al reiniciar el add-on, igual que por MQTT -- ver _on_message)
        if self._persist:
            self._persist()

    def _current_room_name(self):
        """Nombre de la habitación que el robot limpia AHORA (cleaning_roomId), o '—' si no
        está limpiando/mapeando. Un id sin nombre en el mapa (segmento temporal) sale como
        'Habitación N'."""
        s = self.robot.state
        rid = getattr(s, "cleaning_room", None)
        if not rid or s.state not in ("cleaning", "mapping", "paused"):
            return "—"
        meta = self._rooms() or {}
        info = meta.get(rid) or meta.get(str(rid))
        return (info or {}).get("name") or f"{t(self._lang(), 'Habitación')} {rid}"

    def _pub_dust_freq(self):
        """Publica el estado del select de frecuencia de vaciado según robot.state.collect_freq."""
        cf = getattr(self.robot.state, "collect_freq", None)
        try:
            name = DUST_FREQ_REV.get(int(cf)) if cf is not None else None
        except (TypeError, ValueError):
            name = None
        if name:
            self._pub(f"conga/{self.node}/dust_freq", t(self._lang(), name))

    def publish_pose(self):
        """Publica la posición del robot {x, y, angle} (celdas del mapa) en conga/<node>/pose,
        para tarjetas/floorplans externos en Home Assistant. Retenido: la última posición queda
        disponible al recargar. Solo cambia mientras el robot se mueve (limpiando)."""
        if not self.client:
            return
        p = getattr(self.robot, "pose", None)
        if not p or p.get("x") is None:
            return
        self._pub(f"conga/{self.node}/pose",
                  json.dumps({"x": p.get("x"), "y": p.get("y"), "angle": p.get("angle")}))

    def publish_map(self, force=False):
        """Publica la geometría del mapa + la traza en conga/<node>/map (retenido), para tarjetas
        y floorplans de HA. SIN la rejilla de píxeles (esa va en /api/map). Con margen: si no es
        forzado (cambio de mapa), no republica antes de 10 s, para no llenar el recorder mientras
        limpia. La traza se submuestrea a <=500 puntos para no pasarse del límite de atributos de HA."""
        if not self.client:
            return
        m = getattr(self.robot, "map", None)
        if not m or m.get("sample"):
            return
        now = time.time()
        if not force and (now - self._map_pub_ts) < 10:
            return
        self._map_pub_ts = now
        trail = list(getattr(self.robot, "trail", None) or [])
        if len(trail) > 500:
            trail = trail[::(len(trail) + 499) // 500]   # submuestrea a <=500 puntos
        payload = {
            "name": m.get("name"),
            "bbox": m.get("bbox"), "world": m.get("world"),
            "charger": m.get("charger"), "robot": m.get("robot"),
            "rooms": [{"id": r.get("id"), "name": r.get("name"),
                       "center": r.get("center"), "bbox": r.get("bbox")}
                      for r in (m.get("rooms") or []) if r.get("named", True)],
            "trail": trail,
        }
        self._pub(f"conga/{self.node}/map", json.dumps(payload))

    def publish_battery(self):
        """Publica el resumen de salud de batería (solo si cambió)."""
        if not self.client or not self.battery_provider:
            return
        s = json.dumps(self.battery_provider(), sort_keys=True)
        if s != self._battery_last:
            self._battery_last = s
            self._pub(f"conga/{self.node}/battery_health", s)

    def publish_sensors(self):
        """Publica el aviso de limpieza de sensores (solo si cambió)."""
        if not self.client or not self.sensors_provider:
            return
        s = json.dumps(self.sensors_provider(), sort_keys=True)
        if s != self._sensors_last:
            self._sensors_last = s
            self._pub(f"conga/{self.node}/sensor_care", s)

    MAP_IMAGE_LIVE_S = 30

    def publish_map_image(self, force=False):
        """Publica el mapa como PNG en conga/<node>/map_image (retenido) + atributos (calibración).

        - Base (habitaciones, base, paredes virtuales): SOLO cuando cambia el mapa o la vista.
        - En vivo (robot + recorrido): solo si `map_image_live` está activado, mientras limpia y
          como mucho cada MAP_IMAGE_LIVE_S. Al terminar se vuelve a publicar la base.
        El dibujo va en un hilo aparte para no bloquear el bucle de la interfaz."""
        if not self.client:
            return
        m = getattr(self.robot, "map", None)
        if not m or m.get("sample") or not m.get("cells_b64"):
            return
        view = (self.view_provider() if self.view_provider else None) or {}
        state = getattr(self.robot.state, "state", None)
        live = self.map_image_live and state in ("cleaning", "mapping", "paused", "returning")
        now = time.time()
        if live:
            if not force and now - self._img_live_ts < self.MAP_IMAGE_LIVE_S:
                return
        sig = None
        if not live:
            sig = (m.get("cells_b64"), json.dumps(m.get("stored_zones", []), sort_keys=True),
                   json.dumps(m.get("charger"), sort_keys=True), view.get("rot"), view.get("flip"))
            if not force and sig == self._img_sig and not self._img_was_live:
                return
        if not self._img_busy.acquire(blocking=False):
            return                                   # ya se está dibujando una (se reintenta luego)
        if live:
            self._img_live_ts = now
        else:
            self._img_sig = sig
        self._img_was_live = live
        trail = list(getattr(self.robot, "trail", None) or []) if live else None

        def work():
            try:
                from conga_core.mapimage import render_png
                png, attrs = render_png(m, view, live=live, trail=trail)
                self._pub(f"conga/{self.node}/map_image", png)
                self._pub(f"conga/{self.node}/map_image/attr", json.dumps(attrs))
            except Exception as e:
                self.log(f"[mqtt] no se pudo generar la imagen del mapa: {e}")
            finally:
                self._img_busy.release()
        threading.Thread(target=work, daemon=True).start()

    def _update_availability(self, online):
        """Disponibilidad con debounce: 'online' inmediato; 'offline' SOLO si el robot lleva
        desconectado más de AVAIL_OFFLINE_GRACE_S. El Conga cierra/reabre la conexión a menudo, así
        que sin esto la disponibilidad parpadearía y llenaría el recorder de HA de escrituras."""
        if online:
            if self._avail_timer is not None:
                self._avail_timer.cancel()
                self._avail_timer = None
            if self._avail_state != "online":
                self._avail_state = "online"
                self._pub(self.t_avail, "online")
        else:
            if self._avail_state == "offline" or self._avail_timer is not None:
                return                       # ya offline, o ya contando el margen
            def _go_offline():
                self._avail_timer = None
                self._avail_state = "offline"
                self._pub(self.t_avail, "offline")
            self._avail_timer = threading.Timer(AVAIL_OFFLINE_GRACE_S, _go_offline)
            self._avail_timer.daemon = True
            self._avail_timer.start()

    def reflect_schedule(self, plan):
        """Refleja el estado on/off de un horario en HA (sin republicar todo)."""
        self._pub(f"conga/{self.node}/sched/{plan['id']}",
                  "on" if plan.get("enable", True) else "off")

    def forget_schedule(self, pid):
        """Retira de HA el switch y el botón "Ejecutar" de un horario borrado (discovery vacío).
        El object_id del topic de descubrimiento va saneado (igual que al publicarlo)."""
        self._pub(f"{self.disc}/switch/{self.uid}_sched_{_safe_id(pid)}/config", "")
        self._pub(f"conga/{self.node}/sched/{pid}", "")
        self._pub(f"{self.disc}/button/{self.uid}_planrun_{_safe_id(pid)}/config", "")

    # ---------------- reflejo de estado ----------------
    def publish_state(self):
        if not self.client:
            return
        s = self.robot.state
        self._update_availability(bool(s.online))
        # 'mapping' (workMode 45 construyendo mapa) no es un estado válido de la entidad vacuum de HA:
        # se presenta como 'cleaning' (el robot se mueve y limpia mientras mapea).
        st = "cleaning" if s.state == "mapping" else s.state
        state = st if st in _VACUUM_STATES else "idle"
        payload = {"state": state}
        if s.battery is not None:
            payload["battery_level"] = s.battery
        try:
            low_water = int(s.fault or 0) == 525
        except (TypeError, ValueError):
            low_water = False
        payload["low_water"] = "ON" if low_water else "OFF"
        self._pub(self.t_state, json.dumps(payload))
        # traducido (ver el comentario equivalente en publish_discovery más arriba)
        self._pub(f"conga/{self.node}/warning", t(self._lang(), s.warning or ""))
        if s.area is not None:
            self._pub(f"conga/{self.node}/area", s.area)
        if s.clean_time is not None:
            self._pub(f"conga/{self.node}/time", s.clean_time)
        self._pub(f"conga/{self.node}/room_now", self._current_room_name())
        if s.quiet:
            self._pub(f"conga/{self.node}/quiet", "on" if s.quiet.get("is_open") else "off")
            self._pub(f"conga/{self.node}/quiet_begin", _min_to_hhmm(s.quiet.get("begin_time")))
            self._pub(f"conga/{self.node}/quiet_end", _min_to_hhmm(s.quiet.get("end_time")))
        if s.voice:
            self._pub(f"conga/{self.node}/voice", "on" if s.voice.get("voiceMode") else "off")
            self._pub(f"conga/{self.node}/voice_volume", str(s.voice.get("volume", 10)))
        if s.auto_upgrade is not None:
            self._pub(f"conga/{self.node}/ota", "on" if s.auto_upgrade else "off")
        self._pub_dust_freq()
        if s.consumables:
            for key in ("main_brush", "side_brush", "filter", "dishcloth"):
                if s.consumables.get(key) is not None:
                    self._pub(f"conga/{self.node}/consumable/{key}", str(s.consumables[key]))

    # ---------------- entrada: MQTT -> robot ----------------
    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        rc = getattr(reason_code, "value", reason_code)
        self.log(f"[MQTT] conectado al broker (rc={rc})")
        if rc != 0:
            self.log("  [!] rc!=0: revisa credenciales/host del broker")
            return
        # avisa a HA (persistent_notification) si esto es una RECONEXIÓN tras una caída real de
        # la propia conexión MQTT de la app (no la primera conexión al arrancar) -- ver stop()/
        # _on_disconnect() y ha_notify_provider más arriba.
        if self._mqtt_ever_connected and not self._mqtt_was_up and self.ha_notify_provider:
            try:
                self.ha_notify_provider(True)
            except Exception as e:
                self.log(f"  [MQTT] error avisando a HA de la reconexión: {e}")
        self._mqtt_was_up = True
        self._mqtt_ever_connected = True
        node = self.node
        client.publish(self.t_cmd, "", retain=True)      # limpia comandos retained viejos
        for sub in (self.t_cmd, "homeassistant/status",
                    f"conga/{node}/room_command", f"conga/{node}/plan_run",
                    f"conga/{node}/dust_action",
                    f"conga/{node}/consumable/+/reset", f"conga/{node}/dust_freq/set",
                    f"conga/{node}/sensor_care/reset",
                    f"conga/{node}/pref/+/set", f"conga/{node}/sched/+/set",
                    f"conga/{node}/twice/set", f"conga/{node}/turbo_carpet/set",
                    f"conga/{node}/ota/set", f"conga/{node}/quiet/set",
                    f"conga/{node}/quiet_begin/set", f"conga/{node}/quiet_end/set",
                    f"conga/{node}/voice/set", f"conga/{node}/voice_volume/set",
                    # barrido de configs retenidas: para retirar habitaciones/horarios obsoletos
                    f"{self.disc}/switch/+/config", f"{self.disc}/button/+/config"):
            client.subscribe(sub)
        self.publish_discovery()

    def _on_disconnect(self, client, userdata, *args):
        """Paho dispara esto tanto si la app llama a disconnect() (ver stop()) como si la
        conexión se CAE de verdad (red, broker reiniciado, etc.) -- la firma varía entre la
        API v1 y v2 de paho, así que se acepta *args sin interpretarlo, solo para saber que
        ha ocurrido. Avisa a HA (persistent_notification) solo en el segundo caso: una app que
        se para a propósito (reinicio del add-on, actualización) no debería generar un aviso."""
        self.log("[MQTT] desconectado del broker")
        if self._stopping or not self._mqtt_was_up:
            return                       # desconexión buscada, o ya sabíamos que estaba caída
        self._mqtt_was_up = False
        if self.ha_notify_provider:
            try:
                self.ha_notify_provider(False)
            except Exception as e:
                self.log(f"  [MQTT] error avisando a HA de la caída: {e}")

    def _cmd(self, control):
        """Envía un objeto control al robot (misma vía que la web)."""
        try:
            self.robot.command(control)
        except Exception as e:
            self.log(f"  [MQTT] error enviando al robot: {e}")

    def _sweep_stale_config(self, topic):
        """Recibe un config de descubrimiento retenido (homeassistant/{comp}/{obj}/config) y, si
        es un botón de habitación o un switch de horario de ESTE dispositivo que ya no existe, lo
        retira (publica config vacío). Así se auto-limpian habitaciones de mapas viejos y horarios
        de otros mapas / borrados, sin dejar entidades fantasma en HA."""
        parts = topic.split("/")
        if len(parts) != 4:
            return
        obj = parts[2]
        uid = self.uid
        if obj.startswith(f"{uid}_room_"):
            rid = obj[len(f"{uid}_room_"):]
            if rid not in {str(r) for r in (self._rooms() or {})}:
                self._pub(topic, "")
                self.log(f"[MQTT] retirada habitación obsoleta de HA ({obj})")
        elif obj.startswith(f"{uid}_sched_") or obj.startswith(f"{uid}_planrun_"):
            prefix = f"{uid}_sched_" if obj.startswith(f"{uid}_sched_") else f"{uid}_planrun_"
            active = getattr(self.robot.state, "map_head_id", None)
            current = {_safe_id(p["id"]) for p in self.schedules.for_map(active)}
            if obj[len(prefix):] not in current:
                self._pub(topic, "")
                self.log(f"[MQTT] retirado horario/botón obsoleto de HA ({obj})")

    def _on_message(self, client, userdata, msg):
        topic = msg.topic
        payload = msg.payload.decode("utf-8", "replace").strip()
        node = self.node
        try:
            # barrido de descubrimiento retenido: retira de HA botones de habitación u horarios
            # que ya no existen (mapas de prueba, planes de otros mapas, nombres cambiados…).
            if topic.startswith(f"{self.disc}/") and topic.endswith("/config"):
                if payload:
                    self._sweep_stale_config(topic)
                return

            if topic == "homeassistant/status":
                if payload == "online":
                    time.sleep(1)
                    self.publish_discovery()
                return

            if topic == f"conga/{node}/room_command":
                rid = int(payload)
                self._cmd(cmd.fan(self.prefs["fan"]))
                self._cmd(cmd.water(self.prefs["water"]))
                self._cmd(cmd.mop(self.prefs["mop"]))
                time.sleep(0.3)
                self._cmd(cmd.clean_rooms([rid], self.prefs["twice"]))
                self.log(f"[MQTT] limpiar habitación {rid}")
                return

            if topic == f"conga/{node}/plan_run":
                p = next((x for x in self.schedules.plans if x.get("id") == payload), None)
                rooms = [r for r in (p.get("rooms") or []) if r.get("room") is not None] if p else []
                if rooms:
                    first = rooms[0]
                    self._cmd(cmd.fan(first.get("fan") if first.get("fan") in cmd.FAN else self.prefs["fan"]))
                    self._cmd(cmd.water(first.get("water") if first.get("water") in cmd.WATER else self.prefs["water"]))
                    self._cmd(cmd.mop(first.get("mop") if first.get("mop") in cmd.MOP else self.prefs["mop"]))
                    time.sleep(0.3)
                    self._cmd(cmd.clean_rooms([r["room"] for r in rooms],
                                              any(r.get("twice") for r in rooms)))
                    self.log(f"[MQTT] ejecutar plan '{p.get('name', payload)}' ({len(rooms)} hab.)")
                return

            if topic.startswith(f"conga/{node}/pref/") and topic.endswith("/set"):
                key = topic.split("/")[-2]
                # HA manda el valor TRADUCIDO (es uno de los `options` publicados); se traduce de
                # vuelta a la clave canónica que entiende conga_core.commands. Si no se encuentra
                # (p. ej. un mensaje retenido de antes de cambiar de idioma), se usa tal cual -- ya
                # era así antes de que existiera la traducción.
                canon = self._opt_reverse.get(key, {}).get(payload, payload)
                if key in ("fan", "water", "mop"):
                    self.prefs[key] = canon
                    self._cmd({"fan": cmd.fan, "water": cmd.water, "mop": cmd.mop}[key](canon))
                elif key == "mode":
                    self.prefs["mode"] = canon
                    self._cmd(cmd.select_mode(canon))
                elif key == "base_type":
                    self.prefs["base_type"] = canon
                    self.robot.state.base_type = canon
                    self._cmd(cmd.base_type(canon))
                # se guarda para la próxima limpieza Y para que sobreviva a un reinicio del
                # add-on (antes solo "base_type" persistía; fan/water/mop/mode volvían siempre
                # a su valor por defecto al reiniciar)
                if key in ("fan", "water", "mop", "mode", "base_type") and self._persist:
                    self._persist()
                self._pub(f"conga/{node}/pref/{key}", payload)
                return

            if topic == f"conga/{node}/dust_freq/set":
                canon = self._opt_reverse.get("dust_freq", {}).get(payload, payload)
                val = DUST_FREQ.get(canon)
                if val is not None:
                    self._cmd(cmd.dust_freq(val))
                    self.robot.state.collect_freq = val
                    if self._persist:
                        self._persist()
                    self._pub(f"conga/{node}/dust_freq", payload)
                return

            if topic == f"conga/{node}/twice/set":
                self.prefs["twice"] = (payload == "on")
                self._cmd(cmd.twice(self.prefs["twice"]))
                self._pub(f"conga/{node}/twice", payload)
                return
            if topic == f"conga/{node}/turbo_carpet/set":
                self.prefs["turbo_carpet"] = (payload == "on")
                self._cmd(cmd.carpet_turbo(self.prefs["turbo_carpet"]))
                self._pub(f"conga/{node}/turbo_carpet", payload)
                return

            if topic in (f"conga/{node}/quiet/set", f"conga/{node}/quiet_begin/set",
                         f"conga/{node}/quiet_end/set"):
                q = dict(self.robot.state.quiet or {"is_open": 0, "begin_time": 1320,
                                                    "end_time": 420})
                if topic.endswith("/quiet/set"):
                    q["is_open"] = 1 if payload == "on" else 0
                elif topic.endswith("/quiet_begin/set"):
                    q["begin_time"] = _hhmm_to_min(payload)
                else:
                    q["end_time"] = _hhmm_to_min(payload)
                self._cmd(cmd.set_quiet(q["is_open"], q["begin_time"], q["end_time"]))
                self.robot.state.quiet = q
                self.publish_state()
                return

            if topic == f"conga/{node}/voice/set" or topic == f"conga/{node}/voice_volume/set":
                v = dict(self.robot.state.voice or {"voiceMode": 1, "volume": 10})
                if topic.endswith("/voice/set"):
                    v["voiceMode"] = 1 if payload == "on" else 0
                else:
                    v["volume"] = max(0, min(10, int(float(payload))))
                self._cmd(cmd.set_voice(v["voiceMode"], v["volume"]))
                self.robot.state.voice = v
                self.publish_state()
                return

            if topic == f"conga/{node}/ota/set":
                on = (payload == "on")
                self._cmd(cmd.set_upgrade(on))
                self.robot.state.auto_upgrade = 1 if on else 0
                self.robot.ota_enforce = 1 if on else 0   # respeta la elección en reconexiones
                if self._persist:
                    self._persist()
                self._pub(f"conga/{node}/ota", payload)
                return

            if topic == f"conga/{node}/dust_action":
                self._cmd(cmd.dust_action())
                return

            if topic == f"conga/{node}/sensor_care/reset":
                if self.sensors_reset:
                    self.sensors_reset()
                    self.publish_sensors()
                return

            if topic.startswith(f"conga/{node}/consumable/") and topic.endswith("/reset"):
                key = topic.split("/")[-2]
                if key in cmd.CONSUMABLE_RESET:
                    self._cmd(cmd.reset_consumable(key))
                return

            if topic.startswith(f"conga/{node}/sched/") and topic.endswith("/set"):
                pid = topic.split("/")[-2]
                enable = (payload == "on")
                p = self.schedules.toggle(pid, enable)
                if p:
                    self._cmd(self.schedules.order_command(p, self._map_head_id(), self._rooms()))
                    self._pub(f"conga/{node}/sched/{pid}", payload)
                return

            if topic == self.t_cmd and payload:
                self._vacuum_command(payload)
        except Exception as e:
            self.log(f"  [MQTT] error procesando {topic}='{payload}': {e}")

    def _vacuum_command(self, c: str):
        state = self.robot.state.state
        if c == "start":
            self._cmd(cmd.resume() if state in ("paused", "returning") else cmd.start())
        elif c in ("pause", "stop"):
            self._cmd(cmd.cancel_home() if state == "returning" else cmd.pause())
        elif c == "return_to_base":
            self._cmd(cmd.home())
        elif c == "clean_spot":
            self._cmd(cmd.start())
        elif c == "locate":
            self._cmd(cmd.locate())
        else:
            self.log(f"  [MQTT] comando vacuum no mapeado: {c}")
