"""Mapa de la vivienda: decodificador real + mapa de ejemplo (fallback).

El robot envía el mapa por el servicio `sweeper-map/robot/syn_no_cache` como frame
binario: [cabecera][zlib (78 9c)][Protobuf]. Descomprimido, el Protobuf trae una
rejilla 800x800 (campo 4) con 0=desconocido, 1=pared fina, 255=pared, 10..=celdas
de cada habitación, y la lista de habitaciones (campo 12: id + nombre).

`decode_map(frame)` devuelve una estructura lista para el frontend: la rejilla
recortada a su caja envolvente (base64) + las habitaciones con su centro. Portado del
decodificador probado del repo de documentación (decodificar_mapa.py).
"""
from __future__ import annotations
import base64
import struct
import zlib

GRID_W = 800
GRID_H = 800


# ---------------- decodificador real ----------------
def _read_varint(data, pos):
    result = shift = 0
    while True:
        b = data[pos]
        pos += 1
        result |= (b & 0x7f) << shift
        if not (b & 0x80):
            return result, pos
        shift += 7


def _extract_zlib(frame: bytes) -> bytes:
    pos = frame.find(b"\x78\x9c")
    if pos < 0:
        raise ValueError("frame de mapa sin firma zlib (78 9c)")
    return zlib.decompress(frame[pos:])


def _f32(chunk, p):
    return struct.unpack("<f", chunk[p:p + 4])[0]


def _parse_params(chunk) -> dict:
    """Campo 3: w(f2), h(f3), min_x(f4), min_y(f5), max_x(f6), max_y(f7), res(f8)."""
    keymap = {2: "w", 3: "h", 4: "min_x", 5: "min_y", 6: "max_x", 7: "max_y", 8: "res"}
    out = {}
    p = 0
    while p < len(chunk):
        st, p = _read_varint(chunk, p)
        sf, sw = st >> 3, st & 7
        if sw == 0:
            v, p = _read_varint(chunk, p)
            if sf in keymap:
                out[keymap[sf]] = v
        elif sw == 5:
            if sf in keymap:
                out[keymap[sf]] = round(_f32(chunk, p), 4)
            p += 4
        elif sw == 1:
            p += 8
        elif sw == 2:
            sl, p = _read_varint(chunk, p); p += sl
        else:
            break
    return out


def _floats_by_subfield(chunk) -> dict:
    """Devuelve {subcampo: float} de los subcampos wire-type 5 de un sub-mensaje."""
    vals = {}
    p = 0
    while p < len(chunk):
        st, p = _read_varint(chunk, p)
        sf, sw = st >> 3, st & 7
        if sw == 5:
            vals[sf] = round(_f32(chunk, p), 4); p += 4
        elif sw == 0:
            _, p = _read_varint(chunk, p)
        elif sw == 1:
            p += 8
        elif sw == 2:
            sl, p = _read_varint(chunk, p); p += sl
        else:
            break
    return vals


def _parse_pose(chunk) -> dict:
    """Campo 7 = base de carga: x(f1), y(f2), angle(f3) en metros/radianes."""
    v = _floats_by_subfield(chunk)
    return {"x": v.get(1), "y": v.get(2), "angle": v.get(3)}


def _parse_robot(chunk) -> dict:
    """Campo 8 = robot vivo: contador(i1), i2, x(f3), y(f4), angle(f5)."""
    v = _floats_by_subfield(chunk)
    return {"x": v.get(3), "y": v.get(4), "angle": v.get(5)}


def _parse_protobuf(pb: bytes) -> dict:
    """Extrae rejilla (4), habitaciones (12), nombre (5), params (3) y pose (7)."""
    pos = 0
    grid = None
    rooms = []
    map_name = None
    params = None
    pose = None
    robot = None
    while pos < len(pb):
        try:
            tag, pos = _read_varint(pb, pos)
        except IndexError:
            break
        fn, wt = tag >> 3, tag & 0x7
        if wt == 0:
            _, pos = _read_varint(pb, pos)
        elif wt == 1:
            pos += 8
        elif wt == 5:
            pos += 4
        elif wt == 2:
            length, pos = _read_varint(pb, pos)
            chunk = pb[pos:pos + length]
            pos += length
            if fn == 4:                                   # rejilla (subcampo 1)
                p = 0
                _, p = _read_varint(chunk, p)
                glen, p = _read_varint(chunk, p)
                grid = chunk[p:p + glen]
            elif fn == 12:                                # habitación {id, nombre}
                rid = name = None
                p = 0
                while p < len(chunk):
                    st, p = _read_varint(chunk, p)
                    sf, sw = st >> 3, st & 7
                    if sw == 0:
                        v, p = _read_varint(chunk, p)
                        if sf == 1:
                            rid = v
                    elif sw == 2:
                        sl, p = _read_varint(chunk, p)
                        if sf == 2:
                            name = chunk[p:p + sl].decode("utf-8", "replace")
                        p += sl
                    elif sw == 5:
                        p += 4
                    elif sw == 1:
                        p += 8
                    else:
                        break
                rooms.append((rid, name))
            elif fn == 3:                                 # params (origen, resolución)
                params = _parse_params(chunk)
            elif fn == 7:                                 # base de carga (estática)
                pose = _parse_pose(chunk)
            elif fn == 8:                                 # robot vivo (se mueve al limpiar)
                robot = _parse_robot(chunk)
            elif fn == 5 and map_name is None:            # nombre del mapa
                p = 0
                while p < len(chunk):
                    st, p = _read_varint(chunk, p)
                    sf, sw = st >> 3, st & 7
                    if sw == 2:
                        sl, p = _read_varint(chunk, p)
                        try:
                            map_name = chunk[p:p + sl].decode("utf-8")
                        except Exception:
                            pass
                        p += sl
                    elif sw == 0:
                        _, p = _read_varint(chunk, p)
                    else:
                        break
        else:
            break
    return {"grid": grid, "rooms": rooms, "map_name": map_name,
            "params": params, "pose": pose, "robot": robot}


def decode_map(frame: bytes) -> dict:
    """Frame binario crudo -> mapa estructurado para el frontend."""
    info = _parse_protobuf(_extract_zlib(frame))
    grid = info["grid"]
    if not grid or len(grid) < GRID_W * GRID_H:
        raise ValueError("rejilla de mapa incompleta")
    names = {rid: n for rid, n in info["rooms"] if rid is not None}

    # caja envolvente + acumuladores por habitación (una sola pasada, saltando filas vacías)
    minx = miny = 10 ** 9
    maxx = maxy = -1
    rp = {}   # id -> [minx,miny,maxx,maxy,count,sumx,sumy]
    W = GRID_W
    for y in range(GRID_H):
        row = grid[y * W:(y + 1) * W]
        if not any(row):
            continue
        for x, v in enumerate(row):
            if v == 0:
                continue
            if x < minx: minx = x
            if x > maxx: maxx = x
            if y < miny: miny = y
            if y > maxy: maxy = y
            if v not in (1, 255):                          # celda de habitación
                r = rp.get(v)
                if r is None:
                    r = rp[v] = [x, y, x, y, 0, 0, 0]
                if x < r[0]: r[0] = x
                if y < r[1]: r[1] = y
                if x > r[2]: r[2] = x
                if y > r[3]: r[3] = y
                r[4] += 1; r[5] += x; r[6] += y
    if maxx < 0:
        raise ValueError("mapa vacío")

    w, h = maxx - minx + 1, maxy - miny + 1
    cropped = bytearray(w * h)
    for y in range(miny, maxy + 1):
        src = y * W + minx
        dst = (y - miny) * w
        cropped[dst:dst + w] = grid[src:src + w]

    rooms = []
    for rid in sorted(rp):
        r = rp[rid]
        cnt = r[4]
        rooms.append({
            "id": rid,
            "name": names.get(rid) or f"Habitación {rid}",
            # named=False -> segmento temporal que el firmware crea al limpiar (sin
            # nombre en el mapa): se pinta el suelo pero NO se lista como habitación.
            "named": bool(names.get(rid)),
            "center": [round(r[5] / cnt - minx, 1), round(r[6] / cnt - miny, 1)],
            "bbox": [r[0] - minx, r[1] - miny, r[2] - r[0] + 1, r[3] - r[1] + 1],
        })
    # transformación mundo(metros) <-> rejilla:  celda = (mundo - min) / res
    prm = info.get("params") or {}
    mnx = prm.get("min_x", -20.0)
    mny = prm.get("min_y", -20.0)
    res = prm.get("res") or 0.05

    def _to_cell(pose):
        if pose and pose.get("x") is not None:
            return {"x": round((pose["x"] - mnx) / res - minx, 1),
                    "y": round((pose["y"] - mny) / res - miny, 1),
                    "angle": pose.get("angle")}
        return None

    # campo 8 = robot vivo; campo 7 = base de carga. Si no llega el 8, caemos al 7.
    charger = _to_cell(info.get("pose"))
    robot = _to_cell(info.get("robot")) or charger
    return {
        "name": info["map_name"] or "Interior",
        "grid_size": [GRID_W, GRID_H],
        "bbox": [minx, miny, w, h],
        "cells_b64": base64.b64encode(bytes(cropped)).decode(),
        "rooms": rooms,
        "robot": robot,
        "charger": charger,
        # origen del mundo para convertir celda(recortada)<->metros en el frontend:
        # metros = (celda_recortada + bbox_min) * res + min
        "world": {"min_x": mnx, "min_y": mny, "res": res},
        "sample": False,
    }


# ---------------- mapa de ejemplo (fallback sin robot / sin mapa aún) ----------------
_ROOMS = [
    (13, "Cocina", "r2", (14, 14, 156, 118)),
    (15, "Salón", "r1", (14, 132, 156, 154)),
    (16, "Pasillo", "r7", (170, 14, 42, 272)),
    (14, "Dormitorio Principal", "r3", (212, 14, 174, 106)),
    (10, "Dormitorio", "r4", (212, 120, 174, 76)),
    (12, "Baño", "r5", (212, 196, 88, 90)),
    (11, "Baño privado", "r6", (300, 196, 86, 90)),
]


def sample_map() -> dict:
    rooms = []
    for rid, name, ck, (x, y, w, h) in _ROOMS:
        rooms.append({"id": rid, "name": name, "color": ck,
                      "rect": [x, y, w, h], "center": [x + w / 2, y + h / 2]})
    return {"map_head_id": 1700000000, "name": "Interior",
            "size": {"w": 400, "h": 300}, "rooms": rooms,
            "robot": {"x": 92, "y": 258, "angle": 0},
            "charger": {"x": 92, "y": 283}, "sample": True}


def room_ids() -> list:
    return [r[0] for r in _ROOMS]


def rooms_meta() -> dict:
    return {rid: {"name": name} for rid, name, _, _ in _ROOMS}
