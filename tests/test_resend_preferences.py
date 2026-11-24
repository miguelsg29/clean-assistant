"""Pre-clean safety: settings never replace zones; failed preparation never starts."""
import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.update(CONGA_MODE="mock", MQTT_HOST="", DATA_DIR=tempfile.mkdtemp())
from backend import app as A
from backend.mqtt_bridge import MqttBridge
from backend.schedules import ScheduleStore


# Both API options persist independently and appear in the settings response.
assert asyncio.run(A.set_resend_before_clean({"value": True}))["resend_before_clean"] is True
assert asyncio.run(A.set_resend_restrictions_before_clean({"value": True}))["resend_restrictions_before_clean"] is True
assert A.get_info()["resend_restrictions_before_clean"] is True
A._load_prefs()
assert A._ui_prefs["resend_before_clean"] and A._ui_prefs["resend_restrictions_before_clean"]

sent = []
A.robot.command = lambda c: (sent.append(c), {"result": 0})[1]
A.robot.state.map_head_id = 77
A.robot.map = {"stored_zones": [{"kind": "nogo", "points_m": [[0, 0], [1, 0]]}]}
A.zones.zones = [{"id": 1, "kind": "nogo", "name": "CA", "mapid": 77,
                  "points": [[2, 0], [3, 0]]},
                 {"id": 2, "kind": "clean", "name": "Clean", "mapid": 77,
                  "points": [[4, 0], [5, 1]]}]
A._ui_prefs.update(resend_before_clean=True, resend_restrictions_before_clean=False)
A._resend_zones_and_prefs()
assert sent and all(c["control"] not in ("set_area", "set_virwall") for c in sent)
sent.clear()
A._ui_prefs.update(resend_before_clean=False, resend_restrictions_before_clean=True)
A._resend_zones_and_prefs()
assert len(sent) == 1 and len(sent[0]["virwallList"]) == 2
assert sent[0]["control"] == "set_virwall"
sent.clear()
# Saved coordinates are rounded; an equivalent wall reported in reverse by
# the robot must not be duplicated in its next replacement list.
A.robot.map["stored_zones"][0]["points_m"] = [[3.0000001, 0], [2, 0]]
A._resend_zones_and_prefs()
assert len(sent) == 1 and len(sent[0]["virwallList"]) == 1
sent.clear()
A.zones.zones = []
A.robot.map = {"stored_zones": []}
A._resend_zones_and_prefs()
assert not sent  # An empty CA store must never erase robot restrictions.

A.robot.map = None
result = asyncio.run(A.post_command({"action": "start"}))
assert result["ok"] is False and result["code"] == "pre_clean_failed"
assert not sent and A._state_dict()["last_clean_error"]
A.schedules.plans = [{"id": "p", "rooms": [{"room": 1}]}]
result = asyncio.run(A.schedule_run({"id": "p"}))
assert result["ok"] is False and not sent
now = A.datetime.datetime.now()
A.schedules.plans = [{"id": "due", "name": "Due", "mapid": 77,
                      "time": now.strftime("%H:%M"),
                      "days": ["lun", "mar", "mie", "jue", "vie", "sab", "dom"],
                      "rooms": [{"room": 1}]}]
asyncio.run(A._run_due_schedules_legacy())
assert not sent and A._legacy_sched["last"]["error"]
A.robot.map = {"stored_zones": [], "_cached": True}
assert asyncio.run(A.post_command({"action": "start"}))["ok"] is False
A._ui_prefs.update(resend_before_clean=False, resend_restrictions_before_clean=False)
A.robot.command = lambda c: {"ok": False, "error": "offline"}
result = asyncio.run(A.post_command({"action": "start"}))
assert result["code"] == "command_failed" and result["error"] == "offline"
A.robot.command = lambda c: {"result": 0}
assert asyncio.run(A.post_command({"action": "start"}))["ok"] is True
assert A._state_dict()["last_clean_error"] is None

# Old preferences remain enabled for settings, but never implicitly opt into walls.
Path(A.PREFS_PATH).write_text(json.dumps({"resend_before_clean": True}), encoding="utf-8")
A._load_prefs()
assert A._ui_prefs["resend_before_clean"] is True
assert A._ui_prefs["resend_restrictions_before_clean"] is False

# MQTT start, room button and plan button all stop when pre-clean fails.
robot = SimpleNamespace(state=SimpleNamespace(state="docked"), command=lambda c: sent.append(c))
store = ScheduleStore(str(Path(tempfile.mkdtemp()) / "schedules.json"))
store.plans = [{"id": "p", "rooms": [{"room": 1}]}]
bridge = MqttBridge(robot, store, lambda k, default=None: default, lambda: 77, lambda: {})
errors = []
bridge.on_clean_error = errors.append
def fail():
    raise RuntimeError("preparation failed")
bridge.pre_clean_resend = fail
for topic, payload in ((bridge.t_cmd, "start"), (f"conga/{bridge.node}/room_command", "1"),
                       (f"conga/{bridge.node}/plan_run", "p")):
    sent.clear()
    bridge._on_message(None, None, SimpleNamespace(topic=topic, payload=payload.encode()))
    assert not sent
assert len(errors) == 3
started = []
bridge.pre_clean_resend = None
bridge.on_clean_started = lambda: started.append(True)
bridge._vacuum_command("start")
assert started == [True]
print("OK resend preferences: settings, restrictions, API and MQTT")
