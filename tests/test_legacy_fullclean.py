"""Limpieza completa legacy: reactiva todas las habitaciones del plan antes del automático."""
import sys
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from conga_core.legacy import robot as LR
from conga_core.config import RobotConfig

r = LR.LegacyRobot(RobotConfig()); r.log = lambda *a, **k: None
sent = []
r._send = lambda op, f: (sent.append((op, f)), {"result": 0})[1]
r._send_recv = lambda op, f, rsp, *a, **k: sent.append((op, f))
r._in_background = lambda fn, *a: (fn(*a), {"result": 0})[1]
r._lmap = {"head": {"map_head_id": 77}, "plans": [{"id": 2, "name": "P"}], "walls": {},
           "rooms": [{"id": 10, "name": "Cocina"}, {"id": 11, "name": "Salón"}]}
r._mode = 0; r.state.state = "docked"
r._run_mode(LR.CTRL_START, starting=True)
ops = [o for o, _ in sent]
assert ops == ["DEVICE_MAPID_SET_PLAN_PARAMS_REQ", "DEVICE_MAPID_SELECT_MAP_PLAN_REQ", "DEVICE_AUTO_CLEAN_REQ"], ops
assert all(x[4] for x in sent[0][1][5]), sent[0][1][5]
# reanudar tras pausa: solo el automático
sent.clear(); r.state.state = "paused"; r._run_mode(LR.CTRL_START, starting=False)
assert [o for o, _ in sent] == ["DEVICE_AUTO_CLEAN_REQ"], sent
print("OK legacy full clean")
