import json, os, sys, tempfile
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from backend.mock import MockRobot
from backend.schedules import ScheduleStore
from backend.mqtt_bridge import MqttBridge

class FakeClient:
    def __init__(self): self.pubs = []
    def publish(self, topic, payload, retain=False): self.pubs.append((topic, payload, retain))
    def subscribe(self, sub): pass

ENV = {"MQTT_HOST": "localhost", "CONGA_BACKEND": "robeye"}
robot = MockRobot(); robot.robeye = True
robot.captured = {"name": "Robot", "firmware": "SER80-1.2.3-release:3.9.2804"}
tmp = os.path.join(tempfile.gettempdir(), "ca_sched_robeye.json")
if os.path.exists(tmp): os.remove(tmp)
br = MqttBridge(robot, ScheduleStore(tmp), lambda k, d=None: ENV.get(k, d), lambda: 3, lambda: {2: {"name": "Salón"}})
br.client = FakeClient()
br.publish_discovery()
cfg = {t: json.loads(p) for t, p, _ in br.client.pubs if t.endswith("/config") and p}
cleared = {t for t, p, _ in br.client.pubs if t.endswith("/config") and not p}
vac = cfg["homeassistant/vacuum/conga8090/config"]
assert vac["unique_id"] == "robeye" and vac["device"]["manufacturer"] == "Rowenta", vac["device"]
assert vac["device"]["model"].startswith("Rowenta X-plorer Serie 80")
assert not any("Conga" in (c.get("name") or "") for c in cfg.values()), [c["name"] for c in cfg.values() if "Conga" in (c.get("name") or "")]
assert not any(k in t for t in cfg for k in ("_sel_water", "_sel_mop", "_volume", "_dust", "_low_water")), sorted(cfg)
assert "homeassistant/select/robeye_sel_water/config" in cleared
assert "homeassistant/button/robeye_room_2/config" in cfg
assert cfg["homeassistant/button/robeye_clean_all/config"]["payload_press"] == "start"
assert cfg["homeassistant/select/robeye_sel_mode/config"]["options"] == ["Auto", "Bordes"], cfg["homeassistant/select/robeye_sel_mode/config"]["options"]
assert cfg["homeassistant/select/robeye_sel_fan/config"]["options"] == ["Silencio", "Eco", "Normal", "Turbo"], cfg["homeassistant/select/robeye_sel_fan/config"]["options"] and "homeassistant/select/robeye_sel_fan/config" in cfg
assert "homeassistant/sensor/robeye_cons_filter/config" in cfg and "homeassistant/sensor/robeye_tot_distance/config" in cfg
st = cfg["homeassistant/sensor/robeye_tot_distance/config"]; assert st["unit_of_measurement"] == "km" and "distance_km" in st["value_template"]
# consumibles: % de vida restante (no horas de uso)
robot.state.consumables = {"main_brush": 0, "side_brush": 22, "filter": 50, "dishcloth": 400}
robot.state.online = True; br.client.pubs.clear(); br.publish_state()
cons = {t.rsplit("/", 1)[1]: p for t, p, _ in br.client.pubs if "/consumable/" in t}
assert cons == {"main_brush": "100", "side_brush": "90", "filter": "50", "dishcloth": "0"}, cons
print("OK robeye mqtt", len(cfg), "entidades")
