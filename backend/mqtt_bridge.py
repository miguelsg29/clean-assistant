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

# Estados válidos del esquema 'state' de la entidad vacuum de HA.
_VACUUM_STATES = {"cleaning", "docked", "paused", "idle", "returning", "error"}

# Frecuencia de autovaciado: nombre visible en HA <-> valor del robot (set_preference 16).
DUST_FREQ = {"Nunca": -1, "Después de cada limpieza": 0, "Cada 30 minutos": 30,
             "Cada 60 minutos": 60, "Cada 90 minutos": 90, "Cada 2 horas": 120}
DUST_FREQ_REV = {v: k for k, v in DUST_FREQ.items()}


# Modelo del robot para Home Assistant, según el project_type (aprendido del propio robot por
# auto-provisión, o el configurado). (nombre corto, modelo). Amplía el mapa según se confirmen.
CONGA_MODELS = {
    "CECOTECCRL350-1001": ("Conga 8090", "Conga 8090 Ultra"),
    "CCECOTECCRL300-1001": ("Conga 4690", "Conga 4690 Ultra"),   # confirmado por @teosoft0 (issue #1)
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
        self.disc = "homeassistant"
        self.client = None
        # preferencias "para la próxima limpieza" (sombra local: el robot no las reporta)
        self.prefs = {
            "fan": env("DEFAULT_FAN", "Normal"), "water": env("DEFAULT_WATER", "Medio"),
            "mop": env("DEFAULT_MOP", "Estándar"), "twice": False,
            "mode": "Auto", "base_type": "Base de carga", "turbo_carpet": False,
        }
        self.t_state = f"conga/{self.node}/state"
        self.t_cmd = f"conga/{self.node}/command"
        self.t_avail = f"conga/{self.node}/availability"

    def _current_uid(self) -> str:
        """Identidad del dispositivo en HA. Usa el DID REAL del robot (capturado por
        auto-provisión o del .env), no el del entorno del add-on (que es 0). Así el
        add-on y las pruebas del PC convergen en UN solo Conga y no salen duplicados."""
        did = getattr(getattr(self.robot, "cfg", None), "did", 0) or 0
        if did in (0, 123456):
            did = self._env_did
        return f"conga_{did}"

    def _model_names(self):
        """(nombre, modelo) del dispositivo para HA según el project_type del robot. Para modelos
        no mapeados usa un nombre genérico 'Conga' e incluye el project_type crudo en el modelo."""
        pt = (getattr(getattr(self.robot, "cfg", None), "project_type", "") or "").strip()
        if pt in CONGA_MODELS:
            return CONGA_MODELS[pt]
        return ("Conga", f"Conga ({pt})" if pt else "Conga")

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
        self.client.on_message = self._on_message
        self.client.connect_async(self.host, self.port, 60)
        self.client.loop_start()
        self.log(f"[MQTT] puente HA activo -> {self.host}:{self.port}")

    def stop(self):
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

    def _disc(self, comp, obj, cfg):
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
        dev_name, dev_model = self._model_names()
        device = {"identifiers": [uid], "name": dev_name, "manufacturer": "Cecotec",
                  "model": dev_model, "sw_version": "clean-assistant"}
        self._disc("vacuum", node, {
            "name": dev_name, "unique_id": uid, "schema": "state",
            "supported_features": ["start", "pause", "stop", "return_home",
                                   "status", "locate"],
            "command_topic": self.t_cmd, "state_topic": self.t_state, "device": device})

        # sensores
        for name, sid, topic, tmpl, unit, dclass in (
            ("Conga Batería", "bat", self.t_state, "{{ value_json.battery_level }}", "%", "battery"),
            ("Conga Área limpiada", "area", f"conga/{node}/area", "{{ value }}", "m²", None),
            ("Conga Tiempo limpieza", "time", f"conga/{node}/time", "{{ value }}", "min", "duration"),
        ):
            cfg = {"name": name, "unique_id": f"{uid}_{sid}", "state_topic": topic,
                   "value_template": tmpl}
            if unit:
                cfg["unit_of_measurement"] = unit
            if dclass:
                cfg["device_class"] = dclass
            self._disc("sensor", f"{uid}_{sid}", cfg)
        # aviso de falta de agua (faultCode 525) como binary_sensor
        self._disc("binary_sensor", f"{uid}_low_water", {
            "name": "Conga Falta agua", "unique_id": f"{uid}_low_water",
            "state_topic": self.t_state, "value_template": "{{ value_json.low_water }}",
            "payload_on": "ON", "payload_off": "OFF",
            "device_class": "problem", "icon": "mdi:water-alert"})
        for key, name, icon in (("main_brush", "Cepillo central", "mdi:broom"),
                                ("side_brush", "Cepillo lateral", "mdi:broom"),
                                ("filter", "Filtro", "mdi:air-filter"),
                                ("dishcloth", "Mopa", "mdi:water")):
            self._disc("sensor", f"{uid}_cons_{key}", {
                "name": f"Conga {name}", "unique_id": f"{uid}_cons_{key}",
                "state_topic": f"conga/{node}/consumable/{key}",
                "unit_of_measurement": "%", "icon": icon})
            self._disc("button", f"{uid}_creset_{key}", {
                "name": f"Conga Restablecer {name}", "unique_id": f"{uid}_creset_{key}",
                "command_topic": f"conga/{node}/consumable/{key}/reset",
                "payload_press": key, "icon": "mdi:restart"})

        # botones de limpieza por habitación (del mapa vivo)
        for rid, meta in (self._rooms() or {}).items():
            rname = (meta or {}).get("name") or f"Habitación {rid}"
            self._disc("button", f"{uid}_room_{rid}", {
                "name": f"Limpiar {rname}", "unique_id": f"{uid}_room_{rid}",
                "command_topic": f"conga/{node}/room_command", "payload_press": str(rid),
                "icon": "mdi:broom"})

        # selectores: potencia / agua / mopa / modo / tipo de base
        for key, name, opts, icon in (
            ("fan", "Potencia succión", list(cmd.FAN), "mdi:fan"),
            ("water", "Nivel agua", list(cmd.WATER), "mdi:water"),
            ("mop", "Vibración mopa", list(cmd.MOP), "mdi:vibrate"),
            ("mode", "Modo de limpieza", list(cmd.CLEAN_MODES), "mdi:broom"),
            ("base_type", "Tipo de base", list(cmd.BASE_TYPES), "mdi:home-import-outline"),
        ):
            self._disc("select", f"{uid}_sel_{key}", {
                "name": f"Conga {name}", "unique_id": f"{uid}_sel_{key}",
                "command_topic": f"conga/{node}/pref/{key}/set",
                "state_topic": f"conga/{node}/pref/{key}", "options": opts, "icon": icon})
            self._pub(f"conga/{node}/pref/{key}", self.prefs[key])

        # switches: doble pasada, turbo alfombras, no molestar, voz, OTA
        for key, name, icon in (("twice", "Doble pasada (x2)", "mdi:repeat"),
                                ("turbo_carpet", "Turbo en alfombras", "mdi:rug"),
                                ("quiet", "No molestar", "mdi:sleep"),
                                ("voice", "Voz", "mdi:account-voice"),
                                ("ota", "Actualizaciones automáticas", "mdi:cloud-download")):
            self._disc("switch", f"{uid}_{key}", {
                "name": f"Conga {name}", "unique_id": f"{uid}_{key}",
                "command_topic": f"conga/{node}/{key}/set",
                "state_topic": f"conga/{node}/{key}",
                "payload_on": "on", "payload_off": "off", "icon": icon})
        self._pub(f"conga/{node}/twice", "on" if self.prefs["twice"] else "off")
        self._pub(f"conga/{node}/turbo_carpet", "on" if self.prefs["turbo_carpet"] else "off")

        # number: volumen de voz; text: horas de no molestar
        self._disc("number", f"{uid}_volume", {
            "name": "Conga Volumen voz", "unique_id": f"{uid}_volume",
            "command_topic": f"conga/{node}/voice_volume/set",
            "state_topic": f"conga/{node}/voice_volume",
            "min": 0, "max": 10, "step": 1, "icon": "mdi:volume-high"})
        for part, name, icon in (("begin", "No molestar inicio", "mdi:weather-night"),
                                ("end", "No molestar fin", "mdi:weather-sunny")):
            self._disc("text", f"{uid}_quiet_{part}", {
                "name": f"Conga {name}", "unique_id": f"{uid}_quiet_{part}",
                "command_topic": f"conga/{node}/quiet_{part}/set",
                "state_topic": f"conga/{node}/quiet_{part}",
                "pattern": "^([01][0-9]|2[0-3]):[0-5][0-9]$", "icon": icon})

        # botón: vaciar base
        self._disc("button", f"{uid}_dust", {
            "name": "Conga Vaciar base", "unique_id": f"{uid}_dust",
            "command_topic": f"conga/{node}/dust_action", "payload_press": "1",
            "icon": "mdi:delete-empty"})

        # select: frecuencia de autovaciado (igual que en la web)
        self._disc("select", f"{uid}_dust_freq", {
            "name": "Conga Frecuencia de vaciado", "unique_id": f"{uid}_dust_freq",
            "command_topic": f"conga/{node}/dust_freq/set",
            "state_topic": f"conga/{node}/dust_freq",
            "options": list(DUST_FREQ), "icon": "mdi:delete-clock"})
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
                "name": f"Horario {p.get('name', pid)}", "unique_id": obj,
                "command_topic": f"conga/{node}/sched/{pid}/set",
                "state_topic": f"conga/{node}/sched/{pid}",
                "payload_on": "on", "payload_off": "off", "icon": "mdi:calendar-clock"})
            self._pub(f"conga/{node}/sched/{pid}", "on" if p.get("enable", True) else "off")

        self.publish_state()
        self.log(f"[MQTT] autodiscovery publicado ({len(self._rooms() or {})} hab., "
                 f"{len(active_plans)} horario(s) del mapa activo)")

    def _clear_discovery(self, uid: str):
        """Borra el descubrimiento retenido de un dispositivo viejo (uid distinto al
        actual) publicando payload vacío en cada topic de config -> HA lo elimina."""
        objs = [("sensor", f"{uid}_bat"), ("sensor", f"{uid}_area"),
                ("sensor", f"{uid}_time"), ("number", f"{uid}_volume"),
                ("button", f"{uid}_dust"), ("select", f"{uid}_dust_freq"),
                ("binary_sensor", f"{uid}_low_water")]
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
        for comp, obj in objs:
            self._pub(f"{self.disc}/{comp}/{obj}/config", "")
        self.log(f"[MQTT] retirado descubrimiento duplicado ({uid})")

    def note_web_command(self, action, p):
        """Sincroniza la sombra de preferencias en HA cuando el cambio viene de la web."""
        if not self.client:
            return
        node, v = self.node, p.get("value")
        if action in ("fan", "water", "mop", "mode", "base_type"):
            self.prefs[action] = v
            self._pub(f"conga/{node}/pref/{action}", v)
        elif action == "twice":
            self.prefs["twice"] = bool(v)
            self._pub(f"conga/{node}/twice", "on" if v else "off")
        elif action == "carpet_turbo":
            self.prefs["turbo_carpet"] = bool(v)
            self._pub(f"conga/{node}/turbo_carpet", "on" if v else "off")
        elif action == "dust_freq":
            self._pub_dust_freq()   # el estado ya está en robot.state.collect_freq

    def _pub_dust_freq(self):
        """Publica el estado del select de frecuencia de vaciado según robot.state.collect_freq."""
        cf = getattr(self.robot.state, "collect_freq", None)
        try:
            name = DUST_FREQ_REV.get(int(cf)) if cf is not None else None
        except (TypeError, ValueError):
            name = None
        if name:
            self._pub(f"conga/{self.node}/dust_freq", name)

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
        """Retira de HA el switch de un horario borrado (discovery vacío). El object_id del topic
        de descubrimiento va saneado (igual que al publicarlo)."""
        self._pub(f"{self.disc}/switch/{self.uid}_sched_{_safe_id(pid)}/config", "")
        self._pub(f"conga/{self.node}/sched/{pid}", "")

    # ---------------- reflejo de estado ----------------
    def publish_state(self):
        if not self.client:
            return
        s = self.robot.state
        self._update_availability(bool(s.online))
        state = s.state if s.state in _VACUUM_STATES else "idle"
        payload = {"state": state}
        if s.battery is not None:
            payload["battery_level"] = s.battery
        try:
            low_water = int(s.fault or 0) == 525
        except (TypeError, ValueError):
            low_water = False
        payload["low_water"] = "ON" if low_water else "OFF"
        self._pub(self.t_state, json.dumps(payload))
        if s.area is not None:
            self._pub(f"conga/{self.node}/area", s.area)
        if s.clean_time is not None:
            self._pub(f"conga/{self.node}/time", s.clean_time)
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
        node = self.node
        client.publish(self.t_cmd, "", retain=True)      # limpia comandos retained viejos
        for sub in (self.t_cmd, "homeassistant/status",
                    f"conga/{node}/room_command", f"conga/{node}/dust_action",
                    f"conga/{node}/consumable/+/reset", f"conga/{node}/dust_freq/set",
                    f"conga/{node}/pref/+/set", f"conga/{node}/sched/+/set",
                    f"conga/{node}/twice/set", f"conga/{node}/turbo_carpet/set",
                    f"conga/{node}/ota/set", f"conga/{node}/quiet/set",
                    f"conga/{node}/quiet_begin/set", f"conga/{node}/quiet_end/set",
                    f"conga/{node}/voice/set", f"conga/{node}/voice_volume/set",
                    # barrido de configs retenidas: para retirar habitaciones/horarios obsoletos
                    f"{self.disc}/switch/+/config", f"{self.disc}/button/+/config"):
            client.subscribe(sub)
        self.publish_discovery()

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
        elif obj.startswith(f"{uid}_sched_"):
            active = getattr(self.robot.state, "map_head_id", None)
            current = {_safe_id(p["id"]) for p in self.schedules.for_map(active)}
            if obj[len(f"{uid}_sched_"):] not in current:
                self._pub(topic, "")
                self.log(f"[MQTT] retirado horario obsoleto de HA ({obj})")

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

            if topic.startswith(f"conga/{node}/pref/") and topic.endswith("/set"):
                key = topic.split("/")[-2]
                if key in ("fan", "water", "mop"):
                    self.prefs[key] = payload
                    self._cmd({"fan": cmd.fan, "water": cmd.water, "mop": cmd.mop}[key](payload))
                elif key == "mode":
                    self.prefs["mode"] = payload
                    self._cmd(cmd.select_mode(payload))
                elif key == "base_type":
                    self.prefs["base_type"] = payload
                    self.robot.state.base_type = payload
                    self._cmd(cmd.base_type(payload))
                    if self._persist:
                        self._persist()
                self._pub(f"conga/{node}/pref/{key}", payload)
                return

            if topic == f"conga/{node}/dust_freq/set":
                val = DUST_FREQ.get(payload)
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
