import os, sys, tempfile, types
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from backend.sensors import SensorCare
ok = 0; bad = 0
def check(c, m):
    global ok, bad
    if c: ok += 1
    else: bad += 1; print("FAIL", m)
p = os.path.join(tempfile.mkdtemp(), "sc.json")
S = lambda st, on=True: types.SimpleNamespace(state=st, online=on)
sc = SensorCare(p)
check(sc.summary()["hours"] == 0 and not sc.summary()["due"], "inicio")
t = 1000.0
for i in range(1800):                     # 1 h limpiando, muestras cada 2 s
    sc.update(S("cleaning"), t); t += 2
check(abs(sc.summary()["hours"] - 1.0) < 0.05, f"1h {sc.summary()}")
sc.update(S("docked"), t); t += 7200      # parado 2 h: no cuenta
sc.update(S("cleaning"), t); t += 2
sc.update(S("cleaning"), t)
check(abs(sc.summary()["hours"] - 1.0) < 0.05, "parado no cuenta")
sc.update(S("cleaning"), t + 3600)        # hueco grande (desconexión): no cuenta
check(abs(sc.summary()["hours"] - 1.0) < 0.05, "hueco no cuenta")
sc.update(S("cleaning", on=False), t + 3700)
sc2 = SensorCare(p)                       # persistencia
check(abs(sc2.summary()["hours"] - 1.0) < 0.05, "persistencia")
sc2.data["seconds"] = 35 * 3600 - 1; t = 9e5
sc2.update(S("mapping"), t); ch = sc2.update(S("mapping"), t + 2)
check(sc2.summary()["due"] and ch, "aviso a 35 h")
sc2.reset(t + 3)
check(sc2.summary()["hours"] == 0 and not sc2.summary()["due"] and sc2.summary()["reset_ts"], "reset")
check(SensorCare(p).summary()["hours"] == 0, "reset persistido")
print(f"{ok}/{ok+bad}")
