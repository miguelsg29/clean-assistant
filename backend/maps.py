"""Registro de mapas de la casa que Clean Assistant va viendo.

El robot NO expone en local la lista completa de casas/mapas — esa lista vive en la
nube de Cecotec. Pero cada frame de mapa trae la casa actual y sus mapas (campo 17).
Clean Assistant los RECUERDA aquí (maps.json) para poder listarlos y cambiar entre los
que ya haya visto (selectMapPlan). `alias` = nombre personalizado en Clean Assistant.
"""
from __future__ import annotations
import json
import os


class MapStore:
    def __init__(self, path: str = "maps.json"):
        self.path = path
        self.maps: list[dict] = []       # {id, name, house, alias}
        self.deleted: set = set()        # ids borrados (para no re-adoptarlos durante transiciones)
        self._load()

    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, encoding="utf-8") as f:
                    data = json.load(f)
                self.maps = data.get("maps", [])
                self.deleted = set(data.get("deleted", []))
            except Exception:
                self.maps = []
                self.deleted = set()

    def _save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump({"maps": self.maps, "deleted": list(self.deleted)},
                          f, ensure_ascii=False, indent=1)
        except Exception:
            pass

    def record(self, house: dict) -> bool:
        """Registra la casa actual y sus mapas (campo 17 del mapa). True si cambió algo."""
        if not house or not house.get("maps"):
            return False
        hname = house.get("name") or ""
        changed = False
        for m in house["maps"]:
            mid = m.get("id")
            if mid is None or mid in self.deleted:   # no re-adoptar un mapa borrado
                continue
            ex = next((x for x in self.maps if x["id"] == mid), None)
            if ex is None:
                self.maps.append({"id": mid, "name": m.get("name") or f"Mapa {mid}",
                                  "house": hname, "alias": ""})
                changed = True
            else:
                if m.get("name") and ex.get("name") != m["name"]:
                    ex["name"] = m["name"]
                    changed = True
                if hname and ex.get("house") != hname:
                    ex["house"] = hname
                    changed = True
        if changed:
            self._save()
        return changed

    def record_active(self, mid, name, house="") -> bool:
        """Registra el mapa ACTIVO (id fiable = map_head_id, nombre = campo 5)."""
        if mid is None or mid in self.deleted:   # no re-adoptar un mapa borrado
            return False
        ex = next((x for x in self.maps if x["id"] == mid), None)
        if ex is None:
            self.maps.append({"id": mid, "name": name or f"Mapa {mid}",
                              "house": house or "", "alias": ""})
            self._save()
            return True
        changed = False
        if name and ex.get("name") != name:
            ex["name"] = name
            changed = True
        if house and ex.get("house") != house:
            ex["house"] = house
            changed = True
        if changed:
            self._save()
        return changed

    def remove(self, mid) -> bool:
        mid = int(mid)
        self.deleted.add(mid)              # tombstone: no volver a adoptarlo en transiciones
        n = len(self.maps)
        self.maps = [x for x in self.maps if x["id"] != mid]
        self._save()
        return len(self.maps) != n

    def readd_allowed(self, mid):
        """Permite volver a registrar un id borrado (p. ej. si se recrea un mapa)."""
        self.deleted.discard(int(mid))

    def set_house(self, mid, house: str) -> dict | None:
        m = next((x for x in self.maps if x["id"] == int(mid)), None)
        if m is not None:
            m["house"] = (house or "").strip()
            self._save()
        return m

    def rename(self, mid, alias: str) -> dict | None:
        m = next((x for x in self.maps if x["id"] == int(mid)), None)
        if m is not None:
            m["alias"] = (alias or "").strip()
            self._save()
        return m

    def as_list(self, active_id=None) -> list[dict]:
        return [{"id": m["id"], "name": m.get("alias") or m.get("name") or f"Mapa {m['id']}",
                 "house": m.get("house", ""), "active": (m["id"] == active_id)}
                for m in self.maps]
