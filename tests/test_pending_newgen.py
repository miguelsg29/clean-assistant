import sys, time
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from conga_core.robot import RealRobot
from conga_core.config import RobotConfig
ok = bad = 0
def check(c, m):
    global ok, bad
    if c: ok += 1
    else: bad += 1; print("FAIL", m)
logs, sent, notes = [], [], []
r = RealRobot(RobotConfig(), logger=logs.append)
r.command = lambda c: sent.append(c) or {"ok": True}
r.on_update = lambda *a: notes.append(1)
check(not r.state.pending_map, "inicio sin pendiente")
r._parse_ack({"control": "noticeSaveMap", "mapType": 2})
check(r.state.pending_map is True, "noticeSaveMap -> pendiente")
check(any("mapa nuevo sin guardar" in l for l in logs), "log")
n = len(logs)
for _ in range(5): r._parse_ack({"control": "noticeSaveMap", "mapType": 2})
check(len(logs) == n, "no repite el log en cada aviso")
r.tick(); check(r.state.pending_map, "sigue pendiente mientras avisa")
r._save_notice_ts = time.time() - 31; r.tick()
check(r.state.pending_map is False, "caduca a los 30 s sin avisos")
print(f"{ok}/{ok+bad}")
# PR #16: estado del 6090 por to_bind control=status
r2 = RealRobot(RobotConfig(), logger=logs.append)
r2.command = lambda c: {"ok": True}
r2._apply_report({"control": "status", "workMode": 0, "chargeStatus": 1, "battary": 200,
                  "map_head_id": 1792680307, "current_map_name": "Casa", "faultCode": 2105})
print("estado 6090:", r2.state.state, r2.state.battery, r2.state.charging, getattr(r2.state, "map_head_id", None))
