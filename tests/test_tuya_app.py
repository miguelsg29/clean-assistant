"""Backend tuya de punta a punta: app (FastAPI) + robot Tuya simulado + descubrimiento de HA."""
import json, os, sys, tempfile, time
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fake_tuya as F

dev = F.FakeTuya("3.3")
tmp = tempfile.mkdtemp()
os.environ.update({"CONGA_MODE": "real", "CONGA_BACKEND": "tuya", "ROBOT_IP": f"127.0.0.1:{dev.port}",
                   "TUYA_DEVICE_ID": F.DEV_ID, "TUYA_LOCAL_KEY": F.KEY, "TUYA_VERSION": "3.3",
                   "DATA_DIR": tmp, "MQTT_HOST": ""})
import subprocess, urllib.request, socket as _s
_p = _s.socket(); _p.bind(("127.0.0.1", 0)); WEB = _p.getsockname()[1]; _p.close()
proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "backend.app:app", "--app-dir",
                         ROOT, "--port", str(WEB)],
                        cwd=tmp, env=dict(os.environ, PYTHONIOENCODING="utf-8"),
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def get(path):
    with urllib.request.urlopen(f"http://127.0.0.1:{WEB}{path}", timeout=5) as r:
        return json.loads(r.read())


def post(path, body):
    req = urllib.request.Request(f"http://127.0.0.1:{WEB}{path}", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read())


try:
    st = {}
    for _ in range(80):
        try:
            st = get("/api/state")
            if st.get("online"):
                break
        except Exception:
            pass
        time.sleep(0.25)
    assert st.get("online") and st["state"] == "docked" and st["battery"] == 100, st
    assert get("/api/info")["backend"] == "tuya"
    assert not get("/api/setup").get("dns_hosts")
    r = post("/api/command", {"action": "start"})
    assert r.get("ok") is not False, r
    for _ in range(40):
        if get("/api/state")["state"] == "cleaning":
            break
        time.sleep(0.1)
    assert get("/api/state")["state"] == "cleaning"
    assert dev.received[-1].get("1") is True, dev.received
    post("/api/command", {"action": "home"}); time.sleep(0.6)
    assert dev.received[-1] == {"3": True}, dev.received[-1]
finally:
    proc.terminate()
    out = proc.communicate(timeout=10)[0].decode("utf-8", "replace")
    if "Traceback" in out:
        print(out[-3000:])
print("OK app tuya")

from conga_core.config import RobotConfig
from conga_core.tuya.robot import TuyaRobot
robot = TuyaRobot(RobotConfig(), logger=lambda *a: None, host=f"127.0.0.1:{dev.port}", dev_id=F.DEV_ID,
                  local_key=F.KEY, data_dir=tmp)
robot.start()
for _ in range(60):
    if robot.state.online and robot.stats:
        break
    time.sleep(0.1)

# descubrimiento de HA con el robot tuya
from backend.mqtt_bridge import MqttBridge
from backend.schedules import ScheduleStore


class FakeClient:
    def __init__(self): self.pubs = []
    def publish(self, topic, payload, retain=False): self.pubs.append((topic, payload, retain))
    def subscribe(self, sub): pass


ENV = {"MQTT_HOST": "localhost", "CONGA_BACKEND": "tuya"}
br = MqttBridge(robot, ScheduleStore(os.path.join(tmp, "s.json")), lambda k, d=None: ENV.get(k, d),
                lambda: None, lambda: {})
br.client = FakeClient()
br.publish_discovery()
cfg = {t: json.loads(p) for t, p, _ in br.client.pubs if t.endswith("/config") and p}
cleared = {t for t, p, _ in br.client.pubs if t.endswith("/config") and not p}
uid = f"tuya_{F.DEV_ID}"
vac = cfg["homeassistant/vacuum/conga8090/config"]
assert vac["unique_id"] == uid and vac["device"]["manufacturer"] == "Cecotec", vac["device"]
assert "locate" in vac["supported_features"] and vac["device"]["model"] == "Conga (Tuya 3.3)", vac
for gone in ("select/%s_sel_mop", "select/%s_sel_base_type", "switch/%s_ota", "sensor/%s_map",
             "image/%s_map_image", "sensor/%s_pose", "switch/%s_twice", "text/%s_quiet_begin"):
    assert "homeassistant/" + gone % uid + "/config" in cleared, gone
for keep in ("select/%s_sel_water", "select/%s_sel_fan", "number/%s_volume", "switch/%s_quiet",
             "button/%s_dust", "sensor/%s_cons_filter", "sensor/%s_tot_time", "button/%s_clean_all"):
    assert "homeassistant/" + keep % uid + "/config" in cfg, keep
assert "homeassistant/sensor/%s_tot_distance/config" % uid not in cfg
modes = cfg[f"homeassistant/select/{uid}_sel_mode/config"]["options"]
assert modes == ["Auto", "Limpieza completa", "Fregado", "Bordes", "Espiral", "Espiral cuadrada"], modes
br.client.pubs.clear(); br.publish_state()
stats = [json.loads(p) for t, p, _ in br.client.pubs if t.endswith("/stats")]
assert stats and stats[0]["runs"] == 790, stats
cons = {t.rsplit("/", 1)[1]: p for t, p, _ in br.client.pubs if "/consumable/" in t}
assert cons["dishcloth"] == "71" and cons["main_brush"] == "0", cons      # 6395/9000 min = 71 %
dev.close()
print("OK tuya app + HA", len(cfg), "entidades")
