import sys, json
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "backend"))
from conga_core import commands as cmd
plan = {"id": "x", "name": "P", "time": "21:00", "days": ["lun"], "rooms": [{"room": 18, "water": "Off", "fan": "Normal"}]}
o8 = cmd.build_order(plan, 1, {18: {"name": "Salón", "type": 2006}})["order"]["roomPer"][0]
o3 = cmd.build_order(plan, 1, {18: {"name": "Salón", "type": 2006}}, project_type="CECOTECCRL20S-1001")["order"]["roomPer"][0]
assert o8["cleanmode"] == 0 and o8["sweep_mode"] == 0, o8
assert o3["cleanmode"] == 3 and o3["sweep_mode"] == 3 and o3["waterlevel"] == 10, o3
from schedules import ScheduleStore
import tempfile, os
st = ScheduleStore(os.path.join(tempfile.mkdtemp(), "s.json"))
assert st.order_command(plan, 1)["order"]["roomPer"][0]["cleanmode"] == 0
st.project_type = lambda: "CECOTECCRL20S-1001"
assert st.order_command(plan, 1)["order"]["roomPer"][0]["cleanmode"] == 3
# observe: la petición de la nube no vacía los horarios
from conga_core.robot import RealRobot
from conga_core.config import RobotConfig
r = RealRobot(RobotConfig())
r.log = lambda *a, **k: None
r.orders = [{"orderid": 1}]
def frame(content): return json.dumps({"service": "x/transmit", "content": json.dumps(content)}).encode()
r._observe("nube->robot", frame({"control": "getOrder6090", "is_open": -1}))
assert r.orders == [{"orderid": 1}], r.orders
r._observe("robot->nube", frame({"data": {"control": "getOrder6090", "orders": [{"orderid": 2}, {"orderid": 3}]}}))
assert len(r.orders) == 2, r.orders
print("OK v0.30.1")
