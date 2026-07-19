"""Constructores de comandos del Conga 8090 (confirmados por ingeniería inversa).

Cada función devuelve el objeto `control` que viaja hacia el robot dentro de
`{"tag":"sweeper-transmit/to_bind","content": json.dumps(control)}`.
La especificación completa está en el repo de documentación (Conga8090_Protocolo.md).
"""
from __future__ import annotations
import hashlib

# ---------------- escalas (nombre visible -> valor del robot) ----------------
FAN = {"Off": 0, "Eco": 1, "Normal": 2, "Turbo": 3}
WATER = {"Off": 10, "Bajo": 11, "Medio": 12, "Alto": 13}
MOP = {"Off": 0, "Estándar": 1, "Fuerte": 2, "Potente": 3}
CLEAN_MODES = {"Auto": 0, "Limpieza completa": 14, "Fregado": 2, "Bordes": 1,
               "Espiral": 5, "Espiral cuadrada": 15, "Punto": 6}
BASE_TYPES = {"Base de carga": 0, "Colector automático": 1}
MATERIALS = {"Suave": 1, "Azulejos": 2, "Madera": 3, "Alfombra": 4}   # tipo de suelo (roomMaterialId)
WEEKDAY_BITS = {"dom": 1, "lun": 2, "mar": 4, "mie": 8, "jue": 16, "vie": 32, "sab": 64}
# tipos de zona (relativos a cada comando)
VIRWALL_NOGO, VIRWALL_NOMOP = 200, 301   # set_virwall: prohibida / sin fregona
AREA_ONE, AREA_TWICE = 200, 201          # set_area: 1 pasada / doble pasada


def _lvl(table, v):
    """Acepta nombre ('Turbo') o valor numérico directo."""
    return table.get(v, v)


# ---------------- config sugerida según el tipo de suelo (roomMaterialId) ----------------
# La app oficial propone distinta succión/agua/mopa según el suelo. Regla sensata:
#   Alfombra -> solo aspirar (no se friega);  Madera -> suave y poca agua;
#   Azulejos -> fregado fuerte;               Suave -> normal.
FLOOR_DEFAULTS = {
    4: {"fan": "Turbo",  "water": "Off",   "mop": "Off"},       # Alfombra
    3: {"fan": "Eco",    "water": "Bajo",  "mop": "Estándar"},  # Madera
    2: {"fan": "Turbo",  "water": "Alto",  "mop": "Potente"},   # Azulejos
    1: {"fan": "Normal", "water": "Medio", "mop": "Estándar"},  # Suave
}


def floor_defaults(material) -> dict:
    """Config {fan, water, mop} recomendada para un tipo de suelo (1..4)."""
    try:
        m = int(material or 1)
    except (TypeError, ValueError):
        m = 1
    return dict(FLOOR_DEFAULTS.get(m, FLOOR_DEFAULTS[1]))


# ---------------- limpieza (set_mode) ----------------
def start():        return {"control": "set_mode", "mapid": 0, "type": 0, "value": 1}
def pause():        return {"control": "set_mode", "mapid": 0, "type": 2, "value": 2}
def resume():       return {"control": "set_mode", "mapid": 0, "type": 2, "value": 1}
def home():         return {"control": "set_mode", "mapid": 0, "type": 3, "value": 1}
def cancel_home():  return {"control": "set_mode", "mapid": 0, "type": 3, "value": 0}


def select_mode(name: str):
    """Selecciona el TIPO de limpieza (Auto, Fregado, Bordes, Espiral...)."""
    return {"control": "set_mode", "mapid": 0, "type": CLEAN_MODES[name], "value": 4}


def direct(direction: int, angle: int = 0):
    return {"control": "set_direct", "direction": int(direction), "angle": angle}


# ---------------- habitaciones ----------------
def clean_rooms(room_ids, twice: bool = False):
    return {"control": "setRoomClean", "ctrlValue": 1,
            "roomsID": list(room_ids), "clean_type": 1 if twice else 0}


def locate():
    return {"result": 0, "control": "device_ctrl", "ctrltype": 3, "operation": 1}


# ---------------- preferencias (set_preference) ----------------
def set_pref(ctrltype: int, value: int):
    return {"control": "set_preference", "ctrltype": int(ctrltype), "value": int(value)}


def fan(level):     return set_pref(1, _lvl(FAN, level))
def water(level):   return set_pref(2, _lvl(WATER, level))
def mop(level):     return set_pref(15, _lvl(MOP, level))
def twice(on):      return set_pref(3, 1 if on else 0)
def carpet_turbo(on): return set_pref(5, 1 if on else 0)
def base_type(name): return set_pref(17, _lvl(BASE_TYPES, name))


# ---------------- autovaciado / voz / OTA / no molestar ----------------
def dust_action():  return {"control": "set_dust_action", "action": 1}


# reset de consumibles (set_consumables). resetType capturado de la app oficial:
# 1=cepillo central, 2=cepillo lateral, 3=filtro, 4=mopa. Pone las horas de uso a 0.
CONSUMABLE_RESET = {"main_brush": 1, "side_brush": 2, "filter": 3, "dishcloth": 4}


def reset_consumable(which) -> dict:
    rt = CONSUMABLE_RESET.get(which, which)
    return {"control": "set_consumables", "resetType": int(rt)}


def set_voice(voice_on: bool, volume: int):
    return {"control": "set_voice", "voiceMode": 1 if voice_on else 0,
            "volume": max(0, min(10, int(volume)))}


def voice_type(n: int):  return {"control": "setVoiceType", "Voice": int(n)}
def set_upgrade(auto):   return {"control": "set_upgrade_config", "auto_upgrade": 1 if auto else 0}


def set_quiet(is_open: bool, begin_min: int, end_min: int):
    return {"control": "set_quiet", "quiet_count": 1,
            "quiet_list": [{"quietID": 0, "is_open": 1 if is_open else 0,
                            "begin_time": int(begin_min), "end_time": int(end_min)}]}


# ---------------- consultas de estado ----------------
def query(name: str, userid: int | None = None):
    d = {"control": name}
    if userid is not None:
        d["userid"] = userid
    return d


# ---------------- control de sesión ----------------
def lock_device(userid: int):
    """La app 'toma el control' del robot. Necesario para que el robot envíe el
    mapa bajo demanda estando en base (la app lo manda antes de get_map)."""
    return {"control": "lock_device", "userid": int(userid)}


# ---------------- mapa ----------------
def get_map():
    """Pide el estado con el map_head_id (igual que la app oficial)."""
    return {"control": "get_map", "mapid": 0, "type": 0, "mask": 1}


def get_map_all(map_id: int):
    """Pide el mapa binario completo (frame syn_no_cache) por su id."""
    return {"control": "getMapAll", "maplist": [{"map_id": int(map_id)}]}


def select_map(map_id: int, op: int = 1):
    """selectMapPlan: op 1 = activar el mapa, op 2 = borrarlo."""
    return {"control": "selectMapPlan", "mapid": int(map_id), "planid": 0, "type": int(op)}


def delete_map(map_id: int):
    """Borra un mapa de la casa (selectMapPlan type=2)."""
    return select_map(map_id, 2)


# ---------------- zonas (coords en METROS del mapa) ----------------
def _zone(points, ztype, name, zid, area_type=2):
    return {"PointList": [{"PointX": str(x), "PointY": str(y)} for x, y in points],
            "Type": ztype, "name": name, "Count": len(points), "ID": zid,
            "area_type": area_type}


def set_virwall(zones, map_head_id: int):
    """zones: lista de dicts {points:[(x,y)...], type:200|301, name, id}."""
    vw = [_zone(z["points"], z.get("type", VIRWALL_NOGO), z.get("name", ""),
               z.get("id", 0)) for z in zones]
    return {"control": "set_virwall", "VirwallCount": len(vw), "clean_plan_id": 0,
            "virwallList": vw, "map_head_id": int(map_head_id), "area_type": 2}


def set_area(zones, map_head_id: int, top_area_type: int = 2):
    """Zonas de limpieza: type 200 (1 pasada) o 201 (x2). `top_area_type` 2=guardadas
    (persistentes), 3=limpiar ahora (la zona lleva area_type 2 y 1 respectivamente)."""
    za = 1 if top_area_type == 3 else 2
    vw = [_zone(z["points"], z.get("type", AREA_ONE), z.get("name", ""),
               z.get("id", 0), area_type=za) for z in zones]
    return {"control": "set_area", "VirwallCount": len(vw), "clean_plan_id": 0,
            "virwallList": vw, "map_head_id": int(map_head_id),
            "area_type": top_area_type}


# ---------------- horarios (setOrder6090) ----------------
def _daytime(hhmm: str) -> int:
    h, m = str(hhmm).split(":")
    return int(h) * 60 + int(m)


def _weekday(days) -> int:
    mask = 0
    for d in days:
        mask |= WEEKDAY_BITS.get(str(d).strip().lower()[:3]
                                 .replace("á", "a").replace("é", "e"), 0)
    return mask


def _order_id(plan) -> int:
    if plan.get("orderid"):
        return int(plan["orderid"])
    h = int(hashlib.md5(str(plan.get("id", plan.get("name", ""))).encode()).hexdigest()[:8], 16)
    return 1700000000 + (h % 89999999)


def build_order(plan, map_head_id, rooms_meta=None, enable=None):
    """plan: {id,name,time,days,rooms:[{room,fan,water,mop,twice}]}."""
    rooms_meta = rooms_meta or {}
    room_per = []
    for r in plan.get("rooms", []):
        rid = int(r["room"])
        meta = rooms_meta.get(rid, {})
        room_per.append({
            "material_type": meta.get("material", 2),
            "room_id": rid, "sweep_mode": 0, "room_name": meta.get("name", ""),
            "waterlevel": _lvl(WATER, r.get("water", "Medio")),
            "windpower": _lvl(FAN, r.get("fan", "Normal")),
            "carpet": 0, "twiceclean": 1 if r.get("twice") else 0,
            "shake_shift": _lvl(MOP, r.get("mop", "Estándar")),
            "cleanmode": 0, "room_type": meta.get("type", 0),
        })
    en = plan.get("enable", True) if enable is None else enable
    return {"control": "setOrder6090", "order": {
        "orderid": _order_id(plan), "order_name": plan.get("name", "Plan"),
        "enable": 1 if en else 0, "repeat": 1,
        "weekday": _weekday(plan.get("days", [])),
        "day_time": _daytime(plan.get("time", "0:00")),
        "mapid": int(map_head_id), "mapName": "Interior",
        "is_global": 0, "clean_type": 0, "arealist": [], "virwallList": [],
        "roomPer": room_per}}


def delete_order(orderid): return {"control": "deleteOrder6090", "orderid": int(orderid)}


# ---------------- config de habitaciones: nombre, categoría y tipo de suelo ----------------
def set_plan_data(map_head_id, rooms, map_name="Interior"):
    """Guarda la config de habitaciones (setPlanData6090). Reemplazo de lista completa.
    rooms: [{room_id, room_name, room_type, material}]. material acepta nombre
    ('Madera') o número (1-4)."""
    info = [{"roomID": int(r["room_id"]), "roomName": r.get("room_name", ""),
             "roomTypeId": int(r.get("room_type") or 0),
             "roomMaterialId": _lvl(MATERIALS, r.get("material", 1)),
             "cleanStatus": int(r.get("clean_status") or 0)}
            for r in rooms]
    return {"control": "setPlanData6090", "mapid": int(map_head_id),
            "mapName": map_name, "roomInfo": info}
