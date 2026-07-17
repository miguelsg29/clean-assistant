"""Mapa de la vivienda como datos estructurados para el frontend.

v0.1: mapa de EJEMPLO (las 7 habitaciones reales, con sus IDs 10-16). Coordenadas
en un espacio 400x300 que el frontend pinta directamente.

PRÓXIMO HITO: portar aquí el decodificador real (`decodificar_mapa.py` del repo de
documentación): el robot envía el mapa por `syn_no_cache` como binario zlib (78 9c)
+ Protobuf, con rejilla 800x800 y las habitaciones. `decode_map(raw_bytes)` sustituirá
a `sample_map()` devolviendo esta misma estructura desde el mapa real del robot.
"""
from __future__ import annotations

# id de habitación (del mapa) -> (nombre, clave visual, rect x,y,w,h en 400x300)
_ROOMS = [
    (13, "Cocina",             "r2", (14, 14, 156, 118)),
    (15, "Salón",              "r1", (14, 132, 156, 154)),
    (16, "Pasillo",            "r7", (170, 14, 42, 272)),
    (14, "Dormitorio Principal", "r3", (212, 14, 174, 106)),
    (10, "Dormitorio",         "r4", (212, 120, 174, 76)),
    (12, "Baño",               "r5", (212, 196, 88, 90)),
    (11, "Baño privado",       "r6", (300, 196, 86, 90)),
]


def sample_map() -> dict:
    rooms = []
    for rid, name, ck, (x, y, w, h) in _ROOMS:
        rooms.append({
            "id": rid, "name": name, "color": ck,
            "rect": [x, y, w, h],
            "center": [x + w / 2, y + h / 2],
        })
    return {
        "map_head_id": 1700000000,
        "name": "Interior",
        "size": {"w": 400, "h": 300},
        "rooms": rooms,
        "robot": {"x": 92, "y": 258, "angle": 0},
        "charger": {"x": 92, "y": 283},
        "sample": True,   # marca que es un mapa de ejemplo, no del robot real
    }


def room_ids() -> list[int]:
    return [r[0] for r in _ROOMS]


def rooms_meta() -> dict:
    """id -> {name} (para rellenar roomPer de los horarios)."""
    return {rid: {"name": name} for rid, name, _, _ in _ROOMS}
