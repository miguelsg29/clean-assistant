# -*- coding: utf-8 -*-
import io, json, re, sys
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from conga_core import commands as cmd
from conga_core.robot import RealRobot

ok = 0
def check(c, msg):
    global ok
    assert c, msg
    ok += 1

c = cmd.run_plan([11, 12], 1748940943, {11: {"name": "Salón", "type": 0}}, True, 3, 12, 1,
                 "CECOTECCRL30V-7003")
check(c["control"] == "setRoomCleanPlan", "control")
for pt in cmd.ROOMS_AS_PLAN:                     # 7003 (7090) y 7004 (7090 IA, #28)
    check(cmd.run_plan([11], 1, {}, False, 2, 10, 0, pt)["control"] == "setRoomCleanPlan", pt)
check("CECOTECCRL30V-7004" in cmd.ROOMS_AS_PLAN, "7004")
o = c["order"]
check(o["enable"] == 0 and o["mapid"] == 1748940943, "order base")
check([r["room_id"] for r in o["roomPer"]] == [11, 12], "rooms")
r = o["roomPer"][0]
check(r["room_name"] == "Salón" and r["windpower"] == 3 and r["waterlevel"] == 12
      and r["twiceclean"] == 1 and r["shake_shift"] == 1 and r["cleanmode"] == 0, r)


class Cfg:
    project_type = "CECOTECCRL30V-7003"


sent = []
rb = RealRobot.__new__(RealRobot)
import threading
rb.cfg = Cfg(); rb.log = lambda *a: None
rb._lock = threading.Lock(); rb._wlock = threading.Lock(); rb._sock = None
rb._oneoff = None; rb._prefs = {}; rb.rooms_meta = lambda: {}
from conga_core.state import RobotState
rb.state = RobotState(); rb.state.map_head_id = 99
import conga_core.robot as R
R.ws.send = lambda s, m: sent.append(json.loads(json.loads(m)["content"]))
rb._sock = object()
rb.command(cmd.fan("Turbo")); rb.command(cmd.water("Alto"))
rb.command(cmd.clean_rooms([11]))
check(sent[-1]["control"] == "setRoomCleanPlan", sent[-1])
rp = sent[-1]["order"]["roomPer"][0]
check(rp["windpower"] == 3 and rp["waterlevel"] == 13 and rp["twiceclean"] == 0, rp)
# 8090: sin traducir
rb.cfg.project_type = "CECOTECCRL350-1001"
rb.command(cmd.clean_rooms([11]))
check(sent[-1]["control"] == "setRoomClean", sent[-1])

# log con fecha/hora
import importlib
buf = io.StringIO()
from backend import app as A
w = A._Timestamped(buf)
print("hola", "mundo", file=w); w.write("a\nb"); w.write("c\n")
lines = buf.getvalue().splitlines()
check(all(re.match(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d ", l) for l in lines), lines)
check([l[20:] for l in lines] == ["hola mundo", "a", "bc"], lines)
print("OK", ok)
