import sys, json, time, datetime
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from conga_core import commands as cmd
from conga_core.robot import RealRobot
from conga_core.config import RobotConfig

o = cmd.immediate_order([18], 1793033544, {18: {"name": "Salón", "type": 2006}}, "CECOTECCRL20S-1001",
                        now=datetime.datetime(2026, 10, 27, 21, 5))   # martes
od = o["order"]
assert o["control"] == "setOrder6090" and od["day_time"] == 21 * 60 + 6 and od["weekday"] == 4, od
assert od["repeat"] == 0 and od["enable"] == 1 and od["mapid"] == 1793033544
rp = od["roomPer"][0]
assert rp["room_id"] == 18 and rp["room_name"] == "Salón" and rp["cleanmode"] == 3 and rp["waterlevel"] == 10, rp
# a medianoche pasa al día siguiente
o2 = cmd.immediate_order([18], 1, {}, "CECOTECCRL20S-1001", now=datetime.datetime(2026, 10, 27, 23, 59, 30))
assert o2["order"]["day_time"] == 0 and o2["order"]["weekday"] != od["weekday"], o2["order"]

# forma exacta del setOrder6090 de la app del 3890 (sin shake_shift: con él salta el 522, #14)
assert "shake_shift" not in rp and rp["room_material"] == 0 and rp["isDone"] is False, rp
assert rp["room_type"] == 2006, rp     # la categoría del mapa, como la app (2006 = Salón)
# 8090: material y categoría reales; sin dato -> valores por defecto
o8 = cmd.build_order({"rooms": [{"room": 3}, {"room": 4}]}, 1,
                     {3: {"name": "A", "type": 2001, "material": 3}, 4: {"name": "B", "type": None, "material": None}})
r8a, r8b = o8["order"]["roomPer"]
assert (r8a["room_type"], r8a["material_type"]) == (2001, 3) and (r8b["room_type"], r8b["material_type"]) == (0, 2)
assert list(od) == ["arealist", "orderid", "enable", "repeat", "weekday", "mapid", "virwallList",
                    "day_time", "roomPer", "order_name"], list(od)

class FakeSock: pass
sent = []
def mk(pt):
    c = RobotConfig(); c.project_type = pt
    r = RealRobot(c); r.log = lambda *a, **k: None
    r._sock = FakeSock(); r.state.map_head_id = 1793033544
    r.rooms_meta = lambda: {18: {"name": "Salón"}}
    import conga_core.ws as w
    w.send = lambda s, m, **k: sent.append(json.loads(json.loads(m)["content"]))
    return r

r = mk("CECOTECCRL20S-1001")
r.command(cmd.clean_rooms([18]))
assert sent[-1]["control"] == "setOrder6090", sent[-1]
assert sent[-2] == {"control": "set_preference", "ctrltype": 2, "value": 10}, sent[-2]   # agua general Off (522, #14)
oid = sent[-1]["order"]["orderid"]
r.state.state = "cleaning"; r.tick(); assert r._oneoff["started"]
r.state.state = "docked"; r.tick()
assert sent[-1] == {"control": "deleteOrder6090", "orderid": oid}, sent[-1]
assert r._oneoff is None
# no arranca: se retira a los 5 min
r.command(cmd.clean_rooms([18])); r._oneoff["ts"] -= 301; r.state.state = "docked"; r.tick()
assert sent[-1]["control"] == "deleteOrder6090"
# 8090: setRoomClean intacto
r8 = mk("CECOTECCRL350-1001"); r8.command(cmd.clean_rooms([3]))
assert sent[-1]["control"] == "setRoomClean" and r8._oneoff is None
print("OK 3890 rooms")
