import json, os, sys, tempfile
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from backend.mock import MockRobot
from backend.schedules import ScheduleStore
from backend.mqtt_bridge import MqttBridge


class FakeClient:
    def __init__(self):
        self.pubs = []   # (topic, payload, retain)
        self.subs = []

    def publish(self, topic, payload, retain=False):
        self.pubs.append((topic, payload, retain))

    def subscribe(self, sub):
        self.subs.append(sub)


class Msg:
    def __init__(self, topic, payload):
        self.topic = topic
        self.payload = payload.encode() if isinstance(payload, str) else payload


ENV = {"MQTT_HOST": "localhost", "MQTT_PORT": "1883", "ROBOT_DID": "999888",
       "DEFAULT_FAN": "Normal", "DEFAULT_WATER": "Medio", "DEFAULT_MOP": "Estándar"}
def env(k, d=None): return ENV.get(k, d)

rooms = {13: {"name": "Cocina"}, 15: {"name": "Salón"}}

tmp = os.path.join(tempfile.gettempdir(), "ca_sched_test.json")
if os.path.exists(tmp): os.remove(tmp)
sched = ScheduleStore(tmp)
sched.upsert({"id": "noche", "name": "Noche", "enable": True, "time": "22:00",
              "days": ["lun"], "rooms": [{"room": 13, "fan": "Turbo", "water": "Alto", "mop": "Potente"}]})

mock = MockRobot()
sent = []
_orig = mock.command
mock.command = lambda c: (sent.append(c), _orig(c))[1]

br = MqttBridge(mock, sched, env, lambda: 1700000000, lambda: rooms)
assert br.enabled(), "deberia estar habilitado con MQTT_HOST"
fake = FakeClient()
br.client = fake

def mqtt_match(filt, topic):
    """Coincidencia de un topic con un filtro MQTT (+ = un nivel)."""
    f, t = filt.split("/"), topic.split("/")
    if "#" in f:
        f = f[:f.index("#")]
        if len(t) < len(f): return False
        t = t[:len(f)]
    if len(f) != len(t): return False
    return all(a == "+" or a == b for a, b in zip(f, t))

# --- 0. toda command_topic publicada debe estar suscrita ---
br._on_connect(fake, None, None, 0)
cmd_topics = set()
for topic, payload, _ in fake.pubs:
    if topic.endswith("/config") and payload:
        cfg = json.loads(payload)
        if "command_topic" in cfg:
            cmd_topics.add(cfg["command_topic"])
for ct in sorted(cmd_topics):
    assert any(mqtt_match(s, ct) for s in fake.subs), f"command_topic SIN suscripcion: {ct}"
print("cobertura de suscripciones OK:", len(cmd_topics), "command_topics, todas suscritas")
fake.pubs.clear(); fake.subs.clear()

# --- 1. discovery ---
br.publish_discovery()
topics = [p[0] for p in fake.pubs]
def has(t): return any(x == t for x in topics)
assert has("homeassistant/vacuum/conga8090/config"), "falta vacuum"
assert has("homeassistant/button/conga_999888_room_13/config"), "falta boton hab 13"
assert has("homeassistant/button/conga_999888_room_15/config"), "falta boton hab 15"
assert has("homeassistant/select/conga_999888_sel_fan/config"), "falta select fan"
assert has("homeassistant/switch/conga_999888_quiet/config"), "falta switch quiet"
assert has("homeassistant/switch/conga_999888_sched_noche/config"), "falta switch horario"
assert has("homeassistant/number/conga_999888_volume/config"), "falta number volumen"
# device grouping correcto
vac = json.loads(next(p[1] for p in fake.pubs if p[0].endswith("vacuum/conga8090/config")))
assert vac["device"]["identifiers"] == ["conga_999888"], vac["device"]
print("discovery OK:", len(fake.pubs), "topics")

# --- 2. estado ---
fake.pubs.clear()
br.publish_state()
# disponibilidad (v0.18.0, con debounce): "online" solo se publica cuando CAMBIA (ya se publicó al
# conectar), así que publish_state() no la repite; "offline" espera AVAIL_OFFLINE_GRACE_S
assert br._avail_state == "online", "availability deberia ser online (mock online)"
assert not [p for p in fake.pubs if p[0] == "conga/conga8090/availability"], "online repetido"
br._update_availability(False)
assert br._avail_timer is not None and br._avail_state == "online", "offline deberia esperar el margen"
br._update_availability(True)
assert br._avail_timer is None and br._avail_state == "online", "reconexion deberia cancelar el offline"
assert not [p for p in fake.pubs if p[0] == "conga/conga8090/availability"], "parpadeo publicado"
stt = json.loads(next(p[1] for p in fake.pubs if p[0] == "conga/conga8090/state"))
assert stt["state"] == "docked" and stt["battery_level"] == 99, stt
print("estado OK:", stt)

# --- 3. comandos entrantes de HA ---
# a) limpiar habitación 13 -> aplica prefs + setRoomClean
sent.clear()
br._on_message(None, None, Msg("conga/conga8090/room_command", "13"))
ctrls = [c.get("control") for c in sent]
assert "set_preference" in ctrls and "setRoomClean" in ctrls, ctrls
rc = next(c for c in sent if c.get("control") == "setRoomClean")
assert rc["roomsID"] == [13], rc
assert mock.state.state == "cleaning", mock.state.state
print("room_command OK ->", ctrls)

# b) cambiar potencia desde HA
sent.clear(); fake.pubs.clear()
br._on_message(None, None, Msg("conga/conga8090/pref/fan/set", "Turbo"))
sp = next(c for c in sent if c.get("control") == "set_preference")
assert sp["ctrltype"] == 1 and sp["value"] == 3, sp   # FAN Turbo = 3
assert br.prefs["fan"] == "Turbo"
assert ("conga/conga8090/pref/fan", "Turbo", True) in fake.pubs
print("pref fan OK ->", sp)

# c) no molestar ON begin 23:30
sent.clear()
br._on_message(None, None, Msg("conga/conga8090/quiet/set", "on"))
br._on_message(None, None, Msg("conga/conga8090/quiet_begin/set", "23:30"))
sq = [c for c in sent if c.get("control") == "set_quiet"]
assert sq, "falta set_quiet"
q = sq[-1]["quiet_list"][0]
assert q["is_open"] == 1 and q["begin_time"] == 1410, q   # 23:30 = 1410
print("quiet OK ->", q)

# d) comando vacuum start -> cleaning; pause -> paused
sent.clear()
mock.state.state = "docked"; mock.state.charging = True
br._on_message(None, None, Msg("conga/conga8090/command", "start"))
assert mock.state.state == "cleaning", mock.state.state
br._on_message(None, None, Msg("conga/conga8090/command", "pause"))
assert mock.state.state == "paused", mock.state.state
print("vacuum start/pause OK")

# e) toggle horario off
sent.clear(); fake.pubs.clear()
br._on_message(None, None, Msg("conga/conga8090/sched/noche/set", "off"))
so = [c for c in sent if c.get("control") == "setOrder6090"]
assert so and so[-1]["order"]["enable"] == 0, so
assert sched.plans[0]["enable"] is False
assert ("conga/conga8090/sched/noche", "off", True) in fake.pubs
print("toggle horario OK")

# f) borrar horario de HA -> discovery vacío
fake.pubs.clear()
br.forget_schedule("noche")
assert ("homeassistant/switch/conga_999888_sched_noche/config", "", True) in fake.pubs
print("forget_schedule OK")

print("\nTODO OK: puente MQTT (discovery + estado + comandos HA)")
if os.path.exists(tmp): os.remove(tmp)
