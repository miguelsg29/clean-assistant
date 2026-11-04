"""Salud de batería: simulación de limpiezas y cargas."""
import os, sys, tempfile, types
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from backend.battery import BatteryHealth

ok = 0
def check(name, cond, extra=""):
    global ok
    assert cond, f"FALLO: {name} {extra}"
    ok += 1; print(f"  ok  {name}")

path = os.path.join(tempfile.mkdtemp(), "bh.json")
bh = BatteryHealth(path)
st = types.SimpleNamespace(online=True, battery=100, charging=True, state="docked", area=0, clean_time=0)
t = [1_000_000.0]
def tick(sec=60, **kw):
    t[0] += sec
    for k, v in kw.items(): setattr(st, k, v)
    return bh.update(st, t[0])

def clean(pct_per_m2, area=40, minutes=50, recharge=False):
    """Una limpieza: sale de la base al 100 %, gasta pct_per_m2 por m², vuelve y carga."""
    tick(10, state="cleaning", charging=False, battery=100, area=0, clean_time=0)
    used = round(pct_per_m2 * area)
    for i in range(1, minutes + 1):
        b = 100 - round(used * i / minutes)
        tick(60, battery=b, area=round(area * i / minutes, 2), clean_time=i)
        if recharge and i == minutes // 2:
            tick(60, charging=True); tick(60, charging=False)
    tick(30, state="returning")
    tick(30, state="docked", charging=True)
    # carga: rápida hasta 80 % (2 %/min) y lenta hasta 100 % (0,5 %/min)
    b = st.battery
    while b < 100:
        b += 1
        tick(30 if b <= 80 else 120, battery=b)
    tick(60, charging=True)

print("== 12 limpiezas, la batería envejece (gasta más por m²) ==")
for i in range(12):
    clean(0.80 + 0.02 * i)
s = bh.summary()
print("   ", s)
check("12 limpiezas válidas", s["valid_cleans"] == 12)
# cada limpieza gasta round(0.8..1.02 * 40) puntos; ciclos = suma / 100
expected = sum(round((0.80 + 0.02 * i) * 40) for i in range(12)) / 100
check(f"ciclos = {expected:.1f}", abs(s["cycles"] - expected) < 0.15, s["cycles"])
check("consumo reciente ~0.98 %/m²", 0.95 <= s["pct_per_m2"] <= 1.0, s["pct_per_m2"])
check("consumo reciente ~0.78 %/min", 0.75 <= s["pct_per_min"] <= 0.82, s["pct_per_min"])
check("carga rápida ~2 %/min", 1.9 <= s["charge_rate_low"] <= 2.1, s["charge_rate_low"])
check("carga lenta ~0.5 %/min", 0.45 <= s["charge_rate_high"] <= 0.55, s["charge_rate_high"])
check("salud estimada ~82 % (0.84 base / ~0.98 ahora)", 80 <= s["health"] <= 88, s["health"])

print("== limpiezas que NO sirven para medir ==")
clean(1.0, recharge=True)
check("con recarga a mitad: se descarta", bh.summary()["valid_cleans"] == 12)
clean(1.0, area=2, minutes=4)
check("muy corta (2 m², 4 min): se descarta", bh.summary()["valid_cleans"] == 12)

print("== pocos datos y persistencia ==")
bh2 = BatteryHealth(os.path.join(tempfile.mkdtemp(), "x.json"))
check("sin datos: salud desconocida", bh2.summary()["health"] is None and bh2.summary()["valid_cleans"] == 0)
bh3 = BatteryHealth(path)
check("se recarga del disco (limpiezas y ciclos)", bh3.summary()["valid_cleans"] == 12 and bh3.summary()["cycles"] > 0)
print(f"\nTODO OK: {ok} comprobaciones")
