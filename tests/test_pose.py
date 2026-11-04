import sys
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from conga_core import robot as R
from conga_core import map as cmap

calls = {"map": 0, "pose": 0}
frames = iter([
    {"name": "Interior", "bbox": [0, 0, 10, 10], "rooms": [{"id": 1}],
     "cells_b64": "AAA", "robot": {"x": 1, "y": 1, "angle": 0.0}},   # nuevo mapa -> map
    {"name": "Interior", "bbox": [0, 0, 10, 10], "rooms": [{"id": 1}],
     "cells_b64": "AAA", "robot": {"x": 2, "y": 2, "angle": 0.1}},   # misma rejilla, movido -> pose
    {"name": "Interior", "bbox": [0, 0, 10, 10], "rooms": [{"id": 1}],
     "cells_b64": "AAA", "robot": {"x": 2.5, "y": 2.5, "angle": 0.1}},  # movido otra vez -> pose
    {"name": "Interior", "bbox": [0, 0, 10, 10], "rooms": [{"id": 1}],
     "cells_b64": "BBB", "robot": {"x": 3, "y": 3, "angle": 0.2}},   # rejilla cambia -> map
])
cmap.decode_map = lambda payload: next(frames)


class Cfg:
    configured = True       # RealRobot lo lee al arrancar (identidad real del robot)


rob = R.RealRobot(Cfg(), logger=lambda *a: None)
rob.on_map = lambda: calls.__setitem__("map", calls["map"] + 1)
rob.on_pose = lambda: calls.__setitem__("pose", calls["pose"] + 1)

payload = b"\x78\x9csyn_no_cache-blob"
for _ in range(4):
    rob._handle_msg(None, payload)

print("calls:", calls)
print("pose:", rob.pose)
assert calls == {"map": 2, "pose": 2}, calls
assert rob.pose == {"x": 3, "y": 3, "angle": 0.2}, rob.pose
print("OK: 2 map (rejilla nueva/cambiada) + 2 pose (solo movimiento)")
