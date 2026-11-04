import sys
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from conga_core.map import build_map, GRID_W as W, GRID_H as H
def mk(clean_upto):
    g = bytearray(W * H)
    for y in range(100, 140):
        for x in range(100, 200):
            g[y*W+x] = 60 if x < clean_upto else 10
    for y in range(100, 140):
        for x in range(210, 240): g[y*W+x] = 11
    return build_map({"grid": g, "rooms": [(10, "Salón", 0, 0), (11, "Baño", 0, 0)], "map_name": "x"})
c0 = {r["id"]: r["center"] for r in mk(100)["rooms"]}
for cut in (130, 170, 200):
    m = mk(cut); c = {r["id"]: r for r in m["rooms"]}
    assert c[10]["center"] == c0[10], (cut, c[10]["center"], c0[10])
    assert c[10]["bbox"] == [0, 0, 100, 40], c[10]["bbox"]
assert 10 in {r["id"] for r in mk(200)["rooms"]}      # todo limpiado: sigue la etiqueta
print("OK centros fijos", c0)
