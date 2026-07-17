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
