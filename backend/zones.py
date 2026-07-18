"""Gestión de zonas de Clean Assistant.

Clean Assistant es la fuente de la verdad de sus zonas: las guarda (zones.json) y,
en cada cambio, reenvía al robot la lista COMPLETA del grupo afectado (así funcionan
set_virwall y set_area: reemplazo de lista completa).

Tipos:
  nogo    -> zona prohibida   (set_virwall, Type 200)
  nomop   -> zona sin fregona (set_virwall, Type 301)
  clean   -> zona de limpieza (set_area,    Type 200, 1 pasada)
  clean2  -> zona de limpieza (set_area,    Type 201, doble pasada)
"""
from __future__ import annotations
import json
import os
import time

from conga_core import commands as cmd

# kind -> (grupo, Type del comando)
KINDS = {
    "nogo":   ("restricted", cmd.VIRWALL_NOGO),
    "nomop":  ("restricted", cmd.VIRWALL_NOMOP),
    "clean":  ("cleaning",   cmd.AREA_ONE),
    "clean2": ("cleaning",   cmd.AREA_TWICE),
}
KIND_LABEL = {"nogo": "Prohibida", "nomop": "Sin fregona",
              "clean": "Limpieza", "clean2": "Limpieza x2"}


class ZoneStore:
    def __init__(self, path: str = "zones.json"):
        self.path = path
        self.zones: list[dict] = []
        self._load()

    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, encoding="utf-8") as f:
                    self.zones = json.load(f).get("zones", [])
            except Exception:
                self.zones = []

    def _save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump({"zones": self.zones}, f, ensure_ascii=False, indent=1)
        except Exception:
            pass

    def add(self, kind: str, points, name: str = "") -> dict:
        if kind not in KINDS:
            raise ValueError(f"tipo de zona desconocido: {kind}")
        z = {"id": int(time.time() * 1000) % 2_000_000_000,
             "kind": kind,
             "name": name or KIND_LABEL[kind],
             "points": [[round(float(x), 4), round(float(y), 4)] for x, y in points]}
        self.zones.append(z)
        self._save()
        return z

    def rename(self, zid: int, name: str) -> dict | None:
        z = next((x for x in self.zones if x["id"] == int(zid)), None)
        if z and name.strip():
            z["name"] = name.strip()
            self._save()
        return z

    def update_points(self, zid: int, points) -> dict | None:
        z = next((x for x in self.zones if x["id"] == int(zid)), None)
        if z and points:
            z["points"] = [[round(float(x), 4), round(float(y), 4)] for x, y in points]
            self._save()
        return z

    def delete(self, zid: int) -> bool:
        n = len(self.zones)
        self.zones = [z for z in self.zones if z["id"] != int(zid)]
        if len(self.zones) != n:
            self._save()
            return True
        return False

    def group_of(self, kind: str) -> str:
        return KINDS[kind][0]

    def build_command(self, group: str, map_head_id: int):
        """Comando (set_virwall o set_area) con TODAS las zonas del grupo."""
        zs = [{"points": z["points"], "type": KINDS[z["kind"]][1],
               "name": z["name"], "id": z["id"]}
              for z in self.zones if KINDS[z["kind"]][0] == group]
        if group == "restricted":
            return cmd.set_virwall(zs, map_head_id)
        return cmd.set_area(zs, map_head_id)
