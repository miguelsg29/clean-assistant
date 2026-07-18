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


# Categoría de habitación = dos últimos dígitos del roomTypeId. El robot usa varias
# familias (2001 y 2101 = dormitorio; 2006 y 2106 = salón), por eso miramos type % 100.
CAT_BEDROOM, CAT_BATHROOM = 1, 3   # 1=dormitorio, 3=baño, 4=pasillo, 5=cocina, 6=salón
_ALL_DAYS = ["lun", "mar", "mie", "jue", "vie", "sab", "dom"]


def _category(rtype) -> int:
    try:
        return int(rtype) % 100
    except (TypeError, ValueError):
        return -1


def suggested_plans(rooms) -> list[dict]:
    """Planes sugeridos (inactivos) generados del mapa actual, tipo los que propone
    la app de Cecotec. La config de cada habitación sale de su tipo de suelo."""
    real = [r for r in (rooms or []) if r.get("named", True) and r.get("id") is not None]
    if not real:
        return []

    def room_cfg(r):
        d = cmd.floor_defaults(r.get("material"))
        return {"room": r["id"], "fan": d["fan"], "water": d["water"],
                "mop": d["mop"], "twice": False}

    beds = [r for r in real if _category(r.get("type")) == CAT_BEDROOM]
    baths = [r for r in real if _category(r.get("type")) == CAT_BATHROOM]
    out = []
    if beds:
        out.append({"id": "sug_dormitorios", "name": "Solo dormitorios",
                    "time": "09:00", "days": ["lun", "jue"],
                    "rooms": [room_cfg(r) for r in beds]})
    if baths:
        out.append({"id": "sug_banos", "name": "Solo baños",
                    "time": "09:00", "days": list(_ALL_DAYS),
                    "rooms": [room_cfg(r) for r in baths]})
    if len(real) >= 2:
        out.append({"id": "sug_profunda", "name": "Limpieza profunda",
                    "time": "10:00", "days": list(_ALL_DAYS),
                    "rooms": [room_cfg(r) for r in real]})
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
        plan["id"] = plan.get("id") or _slug(plan.get("name", ""))
        plan.setdefault("enable", True)
        self.plans = [p for p in self.plans if p.get("id") != plan["id"]] + [plan]
        self._save()
        return plan

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
        return cmd.build_order(plan, map_head_id, rooms_meta, plan.get("enable", True))

    def delete_command(self, plan: dict):
        return cmd.delete_order(cmd._order_id(plan))
