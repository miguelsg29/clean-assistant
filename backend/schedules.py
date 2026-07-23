"""Gestión de horarios (setOrder6090) de Clean Assistant.

Cada horario es un plan {id, name, enable, time:"HH:MM", days:[...],
rooms:[{room, fan, water, mop, twice}]}. Se persisten en schedules.json y se
sincronizan con el robot con setOrder6090 (por orderid estable) / deleteOrder6090.
"""
from __future__ import annotations
import json
import os
import time

from conga_core import commands as cmd


def _slug(name: str) -> str:
    s = "".join(c if c.isalnum() else "_" for c in (name or "").lower()).strip("_")
    return s or f"plan_{int(time.time())}"


# escalas inversas (valor del robot -> nombre) para reconstruir un plan desde getOrder6090
_FAN_REV = {v: k for k, v in cmd.FAN.items()}
_WATER_REV = {v: k for k, v in cmd.WATER.items()}
_MOP_REV = {v: k for k, v in cmd.MOP.items()}
_WD_REV = [("dom", 1), ("lun", 2), ("mar", 4), ("mie", 8), ("jue", 16), ("vie", 32), ("sab", 64)]


def plan_from_order(order: dict, mapid) -> dict:
    """Convierte un horario del robot (getOrder6090) en un plan de Clean Assistant."""
    mins = int(order.get("day_time", 0) or 0)
    wd = int(order.get("weekday", 0) or 0)
    rooms = []
    for r in order.get("roomPer", []) or []:
        rooms.append({"room": r.get("room_id"),
                      "fan": _FAN_REV.get(r.get("windpower"), "Normal"),
                      "water": _WATER_REV.get(r.get("waterlevel"), "Medio"),
                      "mop": _MOP_REV.get(r.get("shake_shift"), "Estándar"),
                      "twice": bool(r.get("twiceclean"))})
    return {"name": order.get("order_name") or f"Horario {order.get('orderid')}",
            "time": f"{(mins // 60) % 24:02d}:{mins % 60:02d}",
            "days": [k for k, b in _WD_REV if wd & b], "rooms": rooms,
            "enable": bool(order.get("enable", 1)), "mapid": mapid,
            "orderid": order.get("orderid")}


# Categoría de habitación = dos últimos dígitos del roomTypeId. El robot usa varias
# familias (2001 y 2101 = dormitorio; 2006 y 2106 = salón), por eso miramos type % 100.
CAT_BEDROOM, CAT_BATHROOM, CAT_LIVING = 1, 3, 6   # 1=dorm, 3=baño, 4=pasillo, 5=cocina, 6=salón
_ALL_DAYS = ["lun", "mar", "mie", "jue", "vie", "sab", "dom"]

# Config observada en la app de Cecotec para cada plan por defecto. Clave = material
# del suelo (1 Suave, 2 Azulejos, 3 Madera, 4 Alfombra). Valor = (succión, agua, mopa).
# "Solo baños": succión Turbo; suelos mojables a tope, madera/alfombra solo aspiran.
_BANOS_BY_FLOOR = {2: ("Turbo", "Alto", "Potente"), 1: ("Turbo", "Alto", "Potente"),
                   3: ("Turbo", "Off", "Off"),      4: ("Turbo", "Off", "Off")}
# "Solo dormitorios": succión Eco; suave/madera flojo, azulejos medio, alfombra aspira.
_DORM_BY_FLOOR = {3: ("Eco", "Bajo", "Estándar"), 1: ("Eco", "Bajo", "Estándar"),
                  2: ("Eco", "Medio", "Fuerte"),  4: ("Eco", "Off", "Off")}
# "Limpieza profunda": succión por CATEGORÍA de habitación; agua/mopa por suelo.
_PROF_FAN_BY_CAT = {CAT_BEDROOM: "Eco", CAT_LIVING: "Normal"}   # resto (baño/cocina/pasillo) = Turbo
_PROF_WET_BY_FLOOR = {3: ("Bajo", "Estándar"), 1: ("Bajo", "Estándar"),
                      2: ("Alto", "Potente"),  4: ("Off", "Off")}


def _category(rtype) -> int:
    try:
        return int(rtype) % 100
    except (TypeError, ValueError):
        return -1


def _floor(material) -> int:
    return material if material in (1, 2, 3, 4) else 1   # sin definir -> Suave


def suggested_plans(rooms) -> list[dict]:
    """Planes sugeridos (inactivos) generados del mapa actual, replicando los que
    propone la app de Cecotec. La config de cada habitación depende del plan, de la
    categoría de la habitación y de su tipo de suelo (agua Off/mopa Off = solo aspira)."""
    real = [r for r in (rooms or []) if r.get("named", True) and r.get("id") is not None]
    if not real:
        return []

    def by_floor(table, r):
        f, w, m = table[_floor(r.get("material"))]
        return {"room": r["id"], "fan": f, "water": w, "mop": m, "twice": False}

    def profunda(r):
        fan = _PROF_FAN_BY_CAT.get(_category(r.get("type")), "Turbo")
        w, m = _PROF_WET_BY_FLOOR[_floor(r.get("material"))]
        return {"room": r["id"], "fan": fan, "water": w, "mop": m, "twice": False}

    beds = [r for r in real if _category(r.get("type")) == CAT_BEDROOM]
    baths = [r for r in real if _category(r.get("type")) == CAT_BATHROOM]
    out = []
    if beds:
        out.append({"id": "sug_dormitorios", "name": "Solo dormitorios",
                    "time": "09:00", "days": ["lun", "jue"],
                    "rooms": [by_floor(_DORM_BY_FLOOR, r) for r in beds]})
    if baths:
        out.append({"id": "sug_banos", "name": "Solo baños",
                    "time": "09:00", "days": list(_ALL_DAYS),
                    "rooms": [by_floor(_BANOS_BY_FLOOR, r) for r in baths]})
    if len(real) >= 2:
        out.append({"id": "sug_profunda", "name": "Limpieza profunda",
                    "time": "09:00", "days": list(_ALL_DAYS),
                    "rooms": [profunda(r) for r in real]})
    for p in out:
        p["enable"] = False
        p["suggested"] = True
    return out


class ScheduleStore:
    def __init__(self, path: str = "schedules.json"):
        self.path = path
        self.plans: list[dict] = []
        self._load()

    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, encoding="utf-8") as f:
                    self.plans = json.load(f).get("plans", [])
            except Exception:
                self.plans = []

    def _save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump({"plans": self.plans}, f, ensure_ascii=False, indent=1)
        except Exception:
            pass

    def upsert(self, plan: dict) -> dict:
        if not plan.get("id"):
            base = _slug(plan.get("name", ""))
            # id único por mapa: un mismo nombre en dos mapas no colisiona
            plan["id"] = f"{base}_{plan['mapid']}" if plan.get("mapid") else base
        plan.setdefault("enable", True)
        self.plans = [p for p in self.plans if p.get("id") != plan["id"]] + [plan]
        self._save()
        return plan

    def for_map(self, mapid):
        """Horarios del mapa dado. Los antiguos (sin mapid) se asignan al mapa activo
        la primera vez que se consultan (antes solo había un mapa)."""
        if mapid is None:
            return list(self.plans)
        migrated = False
        for p in self.plans:
            if p.get("mapid") is None:
                p["mapid"] = mapid
                migrated = True
        if migrated:
            self._save()
        return [p for p in self.plans if p.get("mapid") == mapid]

    def delete(self, pid: str) -> dict | None:
        p = next((x for x in self.plans if x.get("id") == pid), None)
        if p:
            self.plans = [x for x in self.plans if x.get("id") != pid]
            self._save()
        return p

    def toggle(self, pid: str, enable: bool) -> dict | None:
        p = next((x for x in self.plans if x.get("id") == pid), None)
        if p:
            p["enable"] = bool(enable)
            self._save()
        return p

    # --- comandos para el robot ---
    def order_command(self, plan: dict, map_head_id: int, rooms_meta=None):
        # el horario se guarda en SU mapa (mapid del plan), no en el activo
        mid = plan.get("mapid") or map_head_id
        return cmd.build_order(plan, mid, rooms_meta, plan.get("enable", True))

    def delete_command(self, plan: dict):
        return cmd.delete_order(cmd._order_id(plan))
