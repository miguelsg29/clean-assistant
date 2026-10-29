"""LegacyRobot — "nube local" para la generación 3irobotix 3xxx/4xxx (Conga 4090…).

Escucha en 4010 (comandos), 4030 (mapa) y 4050 (hora). El robot conecta por TCP en
claro, se registra (DEVICE_REGISTER_REQ), entra (CLIENT_ONLINE_REQ), manda latidos y
empuja su estado. Misma interfaz que RealRobot/MockRobot (`.state`, `command(control)`,
`tick()`, `start()` + callbacks), así el backend no distingue uno de otro.

Protocolo portado de @agnoc/core (cloud-server.emitter.ts + robot.emitter.ts). Los
`control` que manda la interfaz son los de la generación nueva (8090); aquí se traducen
a los opcodes legacy equivalentes (ver `command`). Lo no soportado aún se registra y se
ignora sin romper nada.
"""
from __future__ import annotations
import random
import socket
import struct
import threading
import time

import json

from .. import commands as cmd
from .. import map as cmap
from ..state import RobotState, _warn_message, _is_error_fault
from . import mapdecode
from . import protobuf as pb
from .packet import Packet, respond, send

MAX_PACKET = 1 << 20          # igual que @agnoc: tramas de más de 1 MiB = basura
CTRL_STOP, CTRL_START, CTRL_PAUSE = 0, 1, 2
CLEAN_TYPE_AUTO = 2
MANUAL_STOP, MANUAL_INIT = 5, 10
# payloads con formato binario propio (decoders de @agnoc), no Protobuf
BINARY_OPS = {"DEVICE_MAPID_PUSH_MAP_INFO", "DEVICE_MAPID_GET_GLOBAL_INFO_RSP",
              "DEVICE_MAPID_PUSH_POSITION_INFO", "DEVICE_MAPID_PUSH_CHARGE_POSITION_INFO",
              "DEVICE_MAPID_PUSH_ALL_MEMORY_MAP_INFO"}

# workMode -> estado (tabla de @agnoc, device-state.mapper.ts; capturada en un Conga 5090)
_RETURNING = {5, 10, 12, 27, 32, 38}
# 9 = segunda pasada de "ir a un punto" (limpiando), no pausa como en @agnoc (captura de la app
# oficial del 4090, @mactron254, ronda 2)
_PAUSED = {4, 26, 31, 37}
_CLEANING = {1, 6, 7, 9, 11, 20, 25, 30, 36}
_MANUAL = {2}
_ZONE_MODES = {30, 31, 32, 35}  # workMode en modo zona (device-mode.mapper)
_SPOT_MODES = {7, 9, 12, 14}    # workMode en modo punto
ROOM_PLAN_ID = 2                # plan que usan @agnoc y la app para limpiar por habitaciones
# DEVICE_SET_CLEAN_PREFERENCE (0x10D9) lleva succión Y agua en el mismo campo, por rangos:
#   succión 0 silencio, 1 estándar, 2 turbo, 3 máximo  |  agua 10 off, 11 bajo, 12 medio, 13 alto
# (como @agnoc). Comprobado por @mactron254 en un 4090 (#12, 29-oct): el robot devuelve 0-3 en su
# campo de turbina y 10-13 en el de agua, y DE OÍDO solo el 0-3 cambia la turbina. La v0.27.1 lo
# había invertido por una anotación equivocada de la captura del 25-oct.
# CA (commands.FAN): Off(=«Máx» en la UI)=0, Eco=1, Normal=2, Turbo=3
FAN_TO_ROBOT = {0: 3, 1: 0, 2: 1, 3: 2}
# vida (horas) de cada consumible, la MISMA que usa la interfaz (index.html, CONS): el robot legacy
# da el % de uso y CA trabaja en horas de uso
CONSUMABLE_LIFE_H = {"main_brush": 300, "side_brush": 220, "filter": 100, "dishcloth": 160}
# modos de limpieza con orden propia (captura de la app oficial, ronda 2): fregado 0x107D (workMode
# 36), bordes 0x107F (workMode 25) y espiral 0x1081 (workMode 20; no está en @agnoc). Mismo patrón
# que el automático: {1: 1 empezar / 2 pausa}. Para PARAR bordes la app usa 0x1121 {1: 4}.
OP_MOP, OP_EDGE, OP_SPIRAL = "DEVICE_MOP_FLOOR_CLEAN_REQ", "DEVICE_BORDER_CLEAN_REQ", 0x1081
MODE_OPS = {2: OP_MOP, 1: OP_EDGE, 5: OP_SPIRAL}   # commands.CLEAN_MODES: Fregado=2, Bordes=1, Espiral=5
_MOP_MODES = {36, 37, 38, 40}
_EDGE_MODES = {25, 26, 27, 29}
_SPIRAL_MODES = {20, 23}
LOCK_EVERY_S = 60                      # la nube real retoma el control (0x1079) cada ~1 min


def _zone_points(control: dict) -> list:
    """Zonas de un control set_area/set_virwall de CA -> [[(x, y)…]] en metros."""
    return [[(float(p["PointX"]), float(p["PointY"])) for p in z.get("PointList", [])]
            for z in control.get("virwallList") or [] if z.get("PointList")]


def legacy_state(typ, mode, charging: bool, fault) -> str:
    """Estado de CA a partir del status legacy (mismo orden de reglas que @agnoc)."""
    if typ not in (0, 3, None) or _is_error_fault(fault):
        return "error"
    if mode in _MANUAL:
        return "idle"            # control manual: el robot se mueve pero no está limpiando
    if mode in _RETURNING:
        return "returning"
    if mode in _PAUSED:
        return "paused"
    if mode in _CLEANING:
        return "cleaning"
    if charging:
        return "docked"
    return "idle"


def battery_pct(raw) -> int:
    """La gen. legacy reporta la batería ×2 (200 = 100 %), en el estado 0x10FE y en 0x146F.
    Confirmado por la app oficial (decompilada) y su captura (@mactron254). OJO: @agnoc lo
    interpreta como 100..200 -> 0..100 %, que da unos puntos de menos."""
    return max(0, min(100, int(raw) // 2))


# horario "de fábrica" que el robot trae siempre (01-01-2018, desactivado): no es del usuario
BUILTIN_ORDER_ID = 1514736000


def parse_orders(f: dict) -> list[dict]:
    """DEVICE_ORDERLIST_GETTING_RSP (0x10CE) -> horarios con el formato de getOrder6090 de la gen.
    nueva, para mostrarlos igual. Estructura de las capturas de @mactron254 (#12):
      3 (repetido) = orden {1 orderId (epoch), 2 activo, 3 ?, 4 días (bits, 0x7F = todos),
                            5 minutos desde medianoche, 6 {1 mapId, 2 planId, 3, 4, 5 agua?, 6}}
      4 (repetido) = mapa {1 mapId, 2 nombre, 3 {1 planId, 2 nombre del plan}}"""
    plans = {}
    for m in f.get(4, []):
        md = pb.decode(m)
        for p in md.get(3, []):
            pd = pb.decode(p)
            plans[(pb.first(md, 1, 0), pb.first(pd, 1, 0))] = pb.as_str(pb.first(pd, 2, b"")).strip()
    out = []
    for o in f.get(3, []):
        od = pb.decode(o)
        oid = int(pb.first(od, 1, 0))
        if oid == BUILTIN_ORDER_ID:
            continue
        sub = pb.decode(pb.first(od, 6, b""))
        mid, pid = int(pb.first(sub, 1, 0)), int(pb.first(sub, 2, 0))
        out.append({"orderid": oid, "enable": int(pb.first(od, 2, 0)), "repeat": 1,
                    "weekday": int(pb.first(od, 4, 0)), "day_time": int(pb.first(od, 5, 0)),
                    "mapid": mid, "plan_id": pid, "roomPer": [],
                    "order_name": plans.get((mid, pid)) or "Horario de la app"})
    return out


def _recv_exact(sock, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("conexión cerrada")
        buf += chunk
    return bytes(buf)


class LegacyRobot:
    legacy = True                      # para que el resto (p. ej. el nombre en HA) lo distinga

    def __init__(self, cfg, logger=print, host: str = "0.0.0.0", ports: dict | None = None):
        self.cfg = cfg                 # RobotConfig (se reutiliza userid y apply_identity)
        self.state = RobotState()
        self.map = None
        self.map_empty = False
        self.reconnected = False
        self.pose = None
        self.trail = []
        self.orders = []
        self.on_update = None
        self.on_map = None
        self.on_pose = None
        self.on_orders = None
        self.on_provision = None
        self.captured = {}             # identidad del robot (sn, mac, versiones…) del registro
        self.link = "local"            # la gen. legacy no tiene pasarela a la nube (aún)
        self.ota_enforce = 0
        self.log = logger
        self.host = host
        self.ports = ports or {"cmd": 4010, "map": 4030, "rtc": 4050}
        self._lock = threading.Lock()
        self._wlock = threading.Lock()
        self._conns = []               # sockets del robot registrado, en orden de llegada
        self._device_id = None         # id que le asignamos en DEVICE_REGISTER_RSP
        self._user_id = random.randint(1, 2**31 - 1)
        self._handshaken = False
        self._manual = False
        self._unhandled = set()        # opcodes ya avisados (para no llenar el log)
        self._lmap = {}                # última sección conocida de cada parte del mapa legacy
        self._last_cells = None        # rejilla del último mapa emitido (para detectar cambios)
        self._last_zones = None
        self._trail_last = None
        self._trail_map = None
        self._diag = {"quiet": 0, "info": 0, "orders": 0}
        self._listeners = []
        self._waiters = {}             # opname de respuesta -> [Event] (para _send_recv)
        self._kind = {}                # socket -> "cmd" | "map" (puerto por el que entró)
        self._mode = 0                 # modo elegido en la interfaz (commands.CLEAN_MODES): 0 = auto
        self._last_lock = 0.0          # último DEVICE_CONTROL_LOCK_REQ enviado

    # ---------------- interfaz común (como RealRobot) ----------------
    def start(self):
        for name, port in self.ports.items():
            srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind((self.host, port))
            srv.listen(4)
            self._listeners.append(srv)
            threading.Thread(target=self._accept_loop, args=(name, srv), daemon=True).start()
        self.log(f"[legacy] escuchando cmd:{self.ports['cmd']} map:{self.ports['map']} "
                 f"rtc:{self.ports['rtc']} (generación 3xxx/4xxx)")

    def stop(self):
        for s in self._listeners + list(self._conns):
            try:
                s.close()
            except Exception:
                pass

    def tick(self) -> RobotState:
        return self.state

    def set_link(self, mode):
        if str(mode).lower() == "cloud":
            self.log("  [legacy] el modo cloud no está disponible en la generación legacy")

    def reconnect(self):
        """Cierra las conexiones para que el robot vuelva a registrarse."""
        with self._lock:
            conns = list(self._conns)
        for s in conns:
            try:
                s.close()
            except Exception:
                pass

    def query_orders(self):
        """Pide los horarios guardados en el robot (p. ej. creados con la app oficial)."""
        self._send("DEVICE_ORDERLIST_GETTING_REQ", {})

    def command(self, control: dict) -> dict:
        """Traduce un `control` de la gen. nueva al opcode legacy equivalente."""
        c = control.get("control")
        if c == "set_mode":
            typ, val = control.get("type"), control.get("value")
            if typ == 3:                                   # volver a la base / cancelarlo
                if val:
                    return self._send("DEVICE_CHARGE_REQ", {1: 1})
                return self._run_mode(CTRL_STOP, starting=False)   # parar en el modo en curso
            if val == 4:                                   # elegir modo (Auto/Fregado/Bordes…)
                self._mode = int(typ)
                return {"result": 0}
            if typ in (0, 2) and val in (1, 2):            # iniciar / reanudar / pausar
                self._manual = False
                return self._run_mode(CTRL_PAUSE if val == 2 else CTRL_START, starting=(typ == 0))
        elif c == "device_ctrl" and control.get("ctrltype") == 3:   # localizar
            return self._send("DEVICE_SEEK_LOCATION_REQ", {})
        elif c == "set_preference" and control.get("ctrltype") == 1:   # succión -> 0..3
            return self._send("DEVICE_SET_CLEAN_PREFERENCE_REQ",
                              {1: FAN_TO_ROBOT.get(int(control["value"]), 1)})
        elif c == "set_preference" and control.get("ctrltype") == 2:   # agua -> 10..13
            v = int(control["value"])                      # CA (commands.WATER): Off..Alto = 10..13
            return self._send("DEVICE_SET_CLEAN_PREFERENCE_REQ", {1: 10 + max(0, min(3, v - 10 if v >= 10 else v))})
        elif c == "set_upgrade_config":                    # actualizaciones automáticas (0x10F3)
            on = bool(control.get("auto_upgrade"))
            self.state.auto_upgrade = int(on)
            return self._send("DEVICE_UPGRADE_SET_AUTO_INSTALL_REQ", {1: on})
        elif c == "set_direct":                            # mando manual
            d = int(control.get("direction", 0))
            if not self._manual:
                self._send("DEVICE_MANUAL_CTRL_REQ", {1: MANUAL_INIT})
                self._manual = True
            # gen. nueva 0=parar; legacy 1=adelante 2=izq 3=der 4=atrás 5=parar
            return self._send("DEVICE_MANUAL_CTRL_REQ", {1: d if d in (1, 2, 3, 4) else MANUAL_STOP})
        elif c == "set_preference" and control.get("ctrltype") == 3:   # doble pasada
            return self._send("USER_SET_DEVICE_CLEANPREFERENCE_REQ", {2: bool(control["value"])})
        elif c == "set_preference" and control.get("ctrltype") == 5:   # turbo en alfombras
            return self._send("USER_SET_DEVICE_CLEANPREFERENCE_REQ", {4: bool(control["value"])})
        elif c == "setRoomClean":
            ids = [int(r) for r in control.get("roomsID") or []]
            return self._in_background(self._clean_rooms, ids, bool(control.get("clean_type")))
        elif c == "set_area":
            if control.get("area_type") == 3:              # limpiar estas zonas ahora
                return self._in_background(self._clean_zones, _zone_points(control))
            return {"result": 0}       # zonas guardadas: la gen. legacy no las guarda en el robot
        elif c == "set_virwall":
            return self._in_background(self._set_walls, control)
        elif c == "set_voice":
            vol = max(0, min(10, int(control.get("volume", 10))))
            on = bool(control.get("voiceMode"))
            self.state.voice = {"voiceMode": int(on), "volume": vol}
            return self._send("USER_SET_DEVICE_CTRL_SETTING_REQ", {1: on, 2: vol + 1})   # robot 1..11
        elif c == "set_quiet":
            q = (control.get("quiet_list") or [{}])[0]
            is_open, begin, end = int(q.get("is_open", 0)), int(q.get("begin_time", 1320)), int(q.get("end_time", 420))
            self.state.quiet = {"is_open": is_open, "begin_time": begin, "end_time": end}
            return self._send("USER_SET_DEVICE_QUIETHOURS_REQ", {1: bool(is_open), 2: begin, 3: end})
        elif c == "get_consumables":
            return self._send("DEVICE_MAPID_GET_CONSUMABLES_PARAM_REQ", {})
        elif c == "set_consumables":                       # resetType 1..4 = itemId de @agnoc
            r = self._send("DEVICE_MAPID_SET_CONSUMABLES_PARAM_REQ", {1: int(control["resetType"])})
            self._send("DEVICE_MAPID_GET_CONSUMABLES_PARAM_REQ", {})
            return r
        elif c in ("get_map", "getMapAll"):
            return self._request_map()
        elif c == "lock_device":
            return self._send("DEVICE_CONTROL_LOCK_REQ", {})
        elif c == "setSaveMap":                            # guardar/descartar el mapa nuevo pendiente
            self.state.pending_map = False
            self._notify()
            return self._send("DEVICE_MAPID_SET_SAVEWAITINGMAP_INFO_REQ",
                              {1: 1 if control.get("isSave", 1) else 0})
        elif c == "legacy_goto":                           # ir a un punto (GoToLocation de Congatudo)
            return self._in_background(self._goto, float(control["x"]), float(control["y"]))
        elif c == "legacy_reset_map":                      # reiniciar el mapa (MapReset de Congatudo)
            return self._in_background(self._reset_map)
        elif c == "legacy_persistent_map":                 # mapa persistente (historyMap)
            on = bool(control["value"])
            self.state.persistent_map = on
            r = self._send("USER_SET_DEVICE_CLEANPREFERENCE_REQ", {5: on})
            self._request_map()
            return r
        elif c == "mergeRoom":                             # unir habitaciones (joinRooms)
            ids = [int(r) for r in control.get("roomsId") or []]
            data = bytes([1, len(ids)] + ids)
            return self._in_background(self._arrange_rooms, 0, data, 0)
        elif c == "splitRoom":                             # dividir con una línea (splitRoom)
            data = bytes([1, 1, 2]) + struct.pack(
                "<ffff", float(control["startX"]), float(control["startY"]),
                float(control["endX"]), float(control["endY"]))
            return self._in_background(self._arrange_rooms, 1, data, int(control["roomId"]))
        elif c == "setPlanData6090":                       # renombrar habitaciones (updateRoom)
            names = {int(r["roomID"]): r.get("roomName") or "" for r in control.get("roomInfo") or []}
            return self._in_background(self._rename_rooms, names)
        elif c == "selectMapPlan":
            if int(control.get("type", 1)) == 1:           # activar un mapa
                return self._send("DEVICE_MAPID_SELECT_MAP_PLAN_REQ",
                                  {1: int(control["mapid"]), 2: ROOM_PLAN_ID, 3: 1})
        elif c in ("setOrder6090", "deleteOrder6090"):
            # gen. legacy: los horarios los ejecuta Clean Assistant a su hora (ver app.py,
            # _run_due_schedules_legacy). El robot liga cada horario a un "plan" de habitaciones
            # compartido, que no encaja con los horarios por habitación de CA.
            return {"result": 0}
        self.log(f"  [legacy] comando '{c}' aún no soportado en la generación legacy")
        return {"ok": False, "error": f"'{c}' no soportado (legacy)"}

    # ---------------- secuencias de varios pasos (portadas de @agnoc) ----------------
    def _in_background(self, fn, *args) -> dict:
        """Las secuencias esperan respuesta entre pasos: no bloquear al llamador (la API)."""
        with self._lock:
            connected = bool(self._conns)
        if not connected:
            return {"ok": False, "error": "robot no conectado"}
        threading.Thread(target=fn, args=args, daemon=True).start()
        return {"result": 0}

    def _walls_raw(self) -> list:
        """Paredes virtuales del robot tal cual las manda: [(id, [(x, y)…])] en metros."""
        return [(a["id"], a["points"]) for a in (self._lmap.get("walls") or {}).get("areas", [])]

    @staticmethod
    def _area_info(mid: int, plan: int, areas: list) -> dict:
        """DEVICE_MAPID_SET_AREA_*_INFO_REQ: [(id, [(x, y)…])] -> mensaje."""
        return {1: mid, 2: plan, 3: len(areas),
                4: [{1: aid, 2: 0, 3: len(pts), 4: [{1: float(x), 2: float(y)} for x, y in pts]}
                    for aid, pts in areas]}

    def _clean_rooms(self, ids: list, twice: bool):
        """Como cleanRooms de @agnoc (y la captura real): plan con las habitaciones activadas,
        seleccionarlo, refrescar el mapa y arrancar."""
        L, head = self._lmap, self._lmap.get("head")
        if not head or not L.get("rooms"):
            self.log("  [legacy] limpiar habitaciones: aún no hay mapa con habitaciones")
            return
        mid = head["map_head_id"]
        self._send("USER_SET_DEVICE_CLEANPREFERENCE_REQ", {2: twice})
        self._send_recv("DEVICE_MAPID_SET_PLAN_PARAMS_REQ",
                        self._plan_rooms_req(mid, lambda rid: rid in ids),
                        "DEVICE_MAPID_SET_PLAN_PARAMS_RSP")
        self._send_recv("DEVICE_MAPID_SELECT_MAP_PLAN_REQ", {1: mid, 2: ROOM_PLAN_ID, 3: 1},
                        "DEVICE_MAPID_SELECT_MAP_PLAN_RSP")
        self._send_recv("DEVICE_MAPID_GET_GLOBAL_INFO_REQ", {1: 0x78FF},
                        "DEVICE_MAPID_GET_GLOBAL_INFO_RSP")
        self._auto_clean(CTRL_START)

    def _clean_all(self):
        """Limpieza completa. El automático (0x106D) limpia el plan de habitaciones seleccionado, y
        tras limpiar habitaciones ese plan solo tiene esas activadas: el robot repetía la última
        (captura de @mactron254, #12). Se reactivan todas antes de arrancar."""
        L, head = self._lmap, self._lmap.get("head")
        if head and L.get("rooms"):
            mid = head["map_head_id"]
            self._send_recv("DEVICE_MAPID_SET_PLAN_PARAMS_REQ",
                            self._plan_rooms_req(mid, lambda rid: True),
                            "DEVICE_MAPID_SET_PLAN_PARAMS_RSP")
            self._send_recv("DEVICE_MAPID_SELECT_MAP_PLAN_REQ", {1: mid, 2: ROOM_PLAN_ID, 3: 1},
                            "DEVICE_MAPID_SELECT_MAP_PLAN_RSP")
        self._auto_clean(CTRL_START)

    def _plan_rooms_req(self, mid: int, enable, names: dict | None = None) -> dict:
        """DEVICE_MAPID_SET_PLAN_PARAMS_REQ del plan de habitaciones (mismo mensaje que manda
        Congatudo, validado byte a byte). enable(room_id) -> bool; names: {id: nombre nuevo}."""
        L = self._lmap
        plan = next((p for p in L.get("plans") or [] if p["id"] == ROOM_PLAN_ID), {})
        names = names or {}
        return {
            1: mid, 2: ROOM_PLAN_ID, 3: self.state.map_name or "Default",
            4: plan.get("name") or "Default",
            5: [{1: r["id"], 3: names.get(r["id"], r["name"]), 4: bool(enable(r["id"]))}
                for r in L["rooms"]],
            6: self._area_info(mid, ROOM_PLAN_ID, self._walls_raw()),
        }

    def _rename_rooms(self, names: dict):
        """Como updateRoom de @agnoc: reescribe el plan con los nombres nuevos."""
        head = self._lmap.get("head")
        if not head or not self._lmap.get("rooms"):
            return
        self._send_recv("DEVICE_MAPID_SET_PLAN_PARAMS_REQ",
                        self._plan_rooms_req(head["map_head_id"], lambda rid: True, names),
                        "DEVICE_MAPID_SET_PLAN_PARAMS_RSP")
        self._request_map()

    def _arrange_rooms(self, typ: int, data: bytes, room_id: int):
        """Unir (type 0) / dividir (type 1) habitaciones, como joinRooms/splitRoom de @agnoc."""
        head = self._lmap.get("head")
        if not head:
            return
        self._send_recv("DEVICE_MAPID_SET_ARRANGEROOM_INFO_REQ",
                        {1: head["map_head_id"], 2: typ, 3: len(data), 4: data, 5: room_id},
                        "DEVICE_MAPID_SET_ARRANGEROOM_INFO_RSP")
        self._request_map()

    def _goto(self, x: float, y: float):
        """Como cleanPosition de @agnoc (GoToLocation de Congatudo): pasar a modo punto y
        mandar el destino en metros. El robot va y limpia esa zona."""
        head = self._lmap.get("head")
        if not head:
            self.log("  [legacy] ir a un punto: aún no hay mapa")
            return
        if self.state.work_mode not in _SPOT_MODES:          # setMode(SPOT)
            self._send_recv("DEVICE_MAPID_GET_GLOBAL_INFO_REQ", {1: 0x78FF | 0x200},
                            "DEVICE_MAPID_GET_GLOBAL_INFO_RSP")
            self._wait_for(lambda: self.state.work_mode in _SPOT_MODES, 5.0)
        self._send_recv("DEVICE_MAPID_SET_NAVIGATION_REQ",
                        {1: head["map_head_id"], 2: x, 3: y, 4: 0.0, 5: CTRL_START},
                        "DEVICE_MAPID_SET_NAVIGATION_RSP")

    def _reset_map(self):
        """Como resetMap de @agnoc (MapReset de Congatudo): borra el mapa del robot; hará uno
        nuevo en la siguiente limpieza y avisará para guardarlo (pending_map)."""
        self._send_recv("DEVICE_MAPID_SET_HISTORY_MAP_ENABLE_REQ", {},
                        "DEVICE_MAPID_SET_HISTORY_MAP_ENABLE_RSP")
        self._request_map()

    def _clean_zones(self, zones: list):
        """Como cleanAreas de @agnoc: pasar a modo zona, mandar las zonas y arrancar."""
        head = self._lmap.get("head")
        if not head or not zones:
            return
        mid = head["map_head_id"]
        if self.state.work_mode not in _ZONE_MODES:          # setMode(ZONE)
            self._send_recv("DEVICE_AREA_CLEAN_REQ", {1: CTRL_STOP}, "DEVICE_AREA_CLEAN_RSP")
            self._send_recv("DEVICE_MAPID_GET_GLOBAL_INFO_REQ", {1: 0x78FF | 0x100},
                            "DEVICE_MAPID_GET_GLOBAL_INFO_RSP")
            self._wait_for(lambda: self.state.work_mode in _ZONE_MODES, 5.0)
        areas = [(random.randint(1, 65535), pts) for pts in zones]
        self._send_recv("DEVICE_MAPID_SET_AREA_CLEAN_INFO_REQ", self._area_info(mid, 0, areas),
                        "DEVICE_MAPID_SET_AREA_CLEAN_INFO_RSP")
        self._send("DEVICE_AREA_CLEAN_REQ", {1: CTRL_START})

    def _set_walls(self, control: dict):
        """Como setRestrictedZones de @agnoc: las nuevas + las del robot SIN coordenadas
        (así se borran las antiguas). La gen. legacy no tiene zonas 'sin fregona' (301)."""
        head = self._lmap.get("head")
        if not head:
            return
        new = []
        for z in control.get("virwallList") or []:
            if int(z.get("Type", 200)) != 200:
                self.log("  [legacy] las zonas 'sin fregona' no existen en la generación legacy: se omite")
                continue
            pts = [(float(p["PointX"]), float(p["PointY"])) for p in z.get("PointList", [])]
            if len(pts) == 2:
                pts = pts * 2                      # pared: el robot la guarda como A,B,A,B
            if pts:
                new.append((random.randint(1, 65535), pts))
        if not new:
            new = [(random.randint(1, 65535), [])]
        areas = new + [(aid, []) for aid, _ in self._walls_raw()]
        self._send_recv("DEVICE_MAPID_SET_AREA_RESTRICTED_INFO_REQ",
                        self._area_info(head["map_head_id"], 0, areas),
                        "DEVICE_MAPID_SET_AREA_RESTRICTED_INFO_RSP")
        self._request_map()

    def _send_recv(self, opname: str, fields: dict, rsp: str, timeout: float = 8.0) -> bool:
        """Envía y espera la respuesta `rsp` (como sendRecv de @agnoc)."""
        ev = threading.Event()
        with self._lock:
            self._waiters.setdefault(rsp, []).append(ev)
        if self._send(opname, fields).get("ok") is False:
            return False
        if ev.wait(timeout):
            return True
        with self._lock:
            if ev in self._waiters.get(rsp, []):
                self._waiters[rsp].remove(ev)
        self.log(f"  [legacy] sin respuesta {rsp} en {timeout:.0f}s (sigo)")
        return False

    def _wake(self, rsp: str):
        with self._lock:
            evs = self._waiters.pop(rsp, [])
        for ev in evs:
            ev.set()

    @staticmethod
    def _wait_for(cond, timeout: float):
        end = time.time() + timeout
        while time.time() < end and not cond():
            time.sleep(0.2)

    # ---------------- envío ----------------
    def _auto_clean(self, ctrl: int) -> dict:
        return self._send("DEVICE_AUTO_CLEAN_REQ", {1: ctrl, 2: CLEAN_TYPE_AUTO})

    def _send(self, opname: str, fields: dict) -> dict:
        """Trama iniciada por nosotros, por la conexión de COMANDOS (4010), como hace Congatudo en
        la captura real. Si aún no existe, por la primera que haya. (@agnoc usa siempre la primera
        registrada, pero 4010 y 4030 llegan en paralelo y podría ganar la del mapa.)"""
        with self._lock:
            sock = next((s for s in self._conns if self._kind.get(s) == "cmd"),
                        self._conns[0] if self._conns else None)
            dev = self._device_id
        if not sock or dev is None:
            return {"ok": False, "error": "robot no conectado"}
        pkt = send(opname, pb.encode(fields), device_id=dev, user_id=self._user_id)
        try:
            self._write(sock, pkt)
            self.log(f"  --> robot: {opname}")
            return {"result": 0}
        except Exception as e:
            self.log(f"  [!] error enviando al robot: {e}")
            return {"ok": False, "error": str(e)}

    def _write(self, sock, pkt: Packet):
        with self._wlock:
            sock.sendall(pkt.to_bytes())

    def _reply(self, sock, req: Packet, opname: str, fields: dict | None = None):
        self._write(sock, respond(req, opname, pb.encode(fields or {})))

    # ---------------- servidor ----------------
    def _accept_loop(self, name: str, srv):
        while True:
            try:
                sock, addr = srv.accept()
            except OSError:
                return
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            if name == "rtc":
                threading.Thread(target=self._serve_rtc, args=(sock,), daemon=True).start()
            else:
                self.log(f"[legacy] conexión {name} desde {addr[0]}")
                with self._lock:
                    self._kind[sock] = name
                threading.Thread(target=self._serve, args=(name, sock), daemon=True).start()

    def _serve_rtc(self, sock):
        """4050: al conectar se le manda la hora y se cierra (handleRTPConnection)."""
        try:
            body = {1: 0, 3: {1: int(time.time())}}
            self._write(sock, Packet("DEVICE_TIME_SYNC_RSP", pb.encode(body)))
        except Exception:
            pass
        finally:
            try:
                sock.close()
            except Exception:
                pass

    def _serve(self, name: str, sock):
        try:
            while True:
                head = _recv_exact(sock, 4)
                size = int.from_bytes(head, "little")
                if size < 24 or size > MAX_PACKET:
                    raise ValueError(f"tamaño de trama inválido: {size}")
                pkt = Packet.from_bytes(head + _recv_exact(sock, size - 4))
                try:
                    self._handle(sock, pkt)
                except Exception as e:
                    self.log(f"  [legacy] error procesando {pkt.opname}: {e}")
        except Exception as e:
            self.log(f"[legacy] conexión {name} cerrada ({e})")
        finally:
            self._drop(sock)

    def _attach(self, sock):
        with self._lock:
            if sock in self._conns:
                return
            self._conns.append(sock)
            n = len(self._conns)
        # @agnoc lanza el handshake al tener las 2 conexiones (cmd + map); por si un
        # firmware abre solo una, se lanza igualmente a los pocos segundos.
        if n >= 2:
            self._start_handshake()
        else:
            threading.Timer(5.0, self._start_handshake).start()

    def _drop(self, sock):
        try:
            sock.close()
        except Exception:
            pass
        with self._lock:
            if sock in self._conns:
                self._conns.remove(sock)
            self._kind.pop(sock, None)
            empty = not self._conns
        if empty and self.state.online:
            self.state.online = False
            self._handshaken = False
            self._manual = False
            self._notify()

    def _start_handshake(self):
        with self._lock:
            if self._handshaken or not self._conns:
                return
            self._handshaken = True
        self.reconnected = True
        threading.Thread(target=self._handshake, daemon=True).start()

    def _run_mode(self, ctrl: int, starting: bool) -> dict:
        """Iniciar/pausar/reanudar en el modo que toca. Al iniciar, el elegido en la interfaz;
        al pausar/reanudar, el que el robot está haciendo (por su workMode). Fregado y bordes
        tienen orden propia; el resto, el automático."""
        if ctrl == CTRL_STOP and self.state.work_mode in _EDGE_MODES:
            return self._send("DEVICE_MAPID_INTO_MODEIDLE_INFO_REQ", {1: 4})   # parar bordes (app)
        if starting:
            op = MODE_OPS.get(self._mode)
        elif self.state.work_mode in _MOP_MODES:
            op = OP_MOP
        elif self.state.work_mode in _EDGE_MODES:
            op = OP_EDGE
        elif self.state.work_mode in _SPIRAL_MODES:
            op = OP_SPIRAL
        else:
            op = None
        if op is None:
            if ctrl == CTRL_START and starting and self.state.state not in ("paused", "cleaning"):
                return self._in_background(self._clean_all)
            return self._auto_clean(ctrl)
        return self._send(op, {1: ctrl})

    def _handshake(self):
        self._last_lock = time.time()
        self._send("DEVICE_CONTROL_LOCK_REQ", {})
        # actualizaciones automáticas: como la nube real, se le manda el valor al conectar. CA las
        # deja SIEMPRE apagadas salvo que el usuario las active (ota_enforce, lo fija app.py).
        self._send("DEVICE_UPGRADE_SET_AUTO_INSTALL_REQ", {1: bool(self.ota_enforce)})
        self._send("DEVICE_UPGRADE_GET_AUTO_INSTALL_REQ", {})
        self._send("DEVICE_STATUS_GETTING_REQ", {})
        self._send("DEVICE_GET_ALL_GLOBAL_MAP_INFO_REQ", {1: 0, 2: ""})
        self._send("DEVICE_GETTIME_REQ", {})
        self._request_map()
        self._send("DEVICE_MAPID_GET_CONSUMABLES_PARAM_REQ", {})
        self._send("DEVICE_WLAN_INFO_GETTING_REQ", {})
        self.query_orders()

    def _request_map(self) -> dict:
        """Pide el mapa completo (llega por 4030 como GET_GLOBAL_INFO_RSP), con la misma
        máscara que Congatudo en la captura real: todas las secciones (0x78FF)."""
        return self._send("DEVICE_MAPID_GET_GLOBAL_INFO_REQ", {1: 0x78FF})

    # ---------------- mensajes del robot ----------------
    def _handle(self, sock, pkt: Packet):
        op = pkt.opname
        f = {}
        if pkt.payload and op not in BINARY_OPS:   # mapa/posiciones: binario propio, no Protobuf
            try:
                f = pb.decode(pkt.payload)
            except (ValueError, IndexError):
                f = {}

        if op == "DEVICE_REGISTER_REQ":
            self._on_register(sock, pkt, f)
            return
        # Un robot que ya estuvo en otra nube (Congatudo) NO se vuelve a registrar: entra
        # directo con su deviceId (y el userId de esa nube) guardados (captura real de un
        # 4090, @mactron254). CA gestiona un solo robot, así que se ADOPTAN esos ids en vez
        # de rechazarlo con 12002 como hace @agnoc (que obligaría a un registro que no llega).
        if not self._adopt_ids(pkt):
            sn = pb.as_str(pb.first(f, 1, b""))
            self._reply(sock, pkt, "CLIENT_ONLINE_RSP" if op == "CLIENT_ONLINE_REQ"
                        else "COMMON_ERROR_REPLY",
                        {1: 12002, 2: f"Device not registered(devsn: {sn})"}
                        if op == "CLIENT_ONLINE_REQ"
                        else {1: 1, 2: "Device not registered", 3: pkt.opcode})
            return
        if op == "CLIENT_ONLINE_REQ":
            self.captured.setdefault("sn", pb.as_str(pb.first(f, 1, b"")))
            self._reply(sock, pkt, "CLIENT_ONLINE_RSP", {1: 0})
            self._attach(sock)
            return
        self._attach(sock)
        if op.endswith("_RSP"):
            self._wake(op)                 # respuesta a un _send_recv en curso

        if op == "CLIENT_HEARTBEAT_REQ":
            self._reply(sock, pkt, "CLIENT_HEARTBEAT_RSP")
            # como la nube real: retomar el control cada ~1 min (si no, el robot se da por libre)
            if self._handshaken and time.time() - self._last_lock > LOCK_EVERY_S:
                self._last_lock = time.time()
                self._send("DEVICE_CONTROL_LOCK_REQ", {})
        elif op == "DEVICE_UPGRADE_GET_AUTO_INSTALL_RSP":
            self.state.auto_upgrade = int(bool(pb.first(f, 1, 0)))
            if self.ota_enforce is not None and self.state.auto_upgrade != int(bool(self.ota_enforce)):
                self.log("  [legacy] el robot tenía otra preferencia de actualizaciones: se reaplica")
                self.command({"control": "set_upgrade_config", "auto_upgrade": bool(self.ota_enforce)})
            self._notify()
        elif op == "DEVICE_MAPID_WORK_STATUS_PUSH_REQ":
            self._apply_status(f)
        elif op == "PUSH_DEVICE_BATTERY_INFO_REQ":
            self._reply(sock, pkt, "PUSH_DEVICE_BATTERY_INFO_RSP", {1: 0})
            lvl = pb.first(pb.decode(pb.first(f, 1, b"")), 1)
            if lvl is not None:
                self.state.battery = battery_pct(lvl)
                self._notify()
        elif op == "DEVICE_VERSION_INFO_UPDATE_REQ":
            self.captured["software"] = pb.as_str(pb.first(f, 1, b""))
            self.captured["hardware"] = pb.as_str(pb.first(f, 2, b""))
            self._reply(sock, pkt, "DEVICE_VERSION_INFO_UPDATE_RSP", {1: 0})
        elif op == "PUSH_DEVICE_AGENT_SETTING_REQ":     # ajustes del robot (voz, silencio…)
            self._reply(sock, pkt, "PUSH_DEVICE_AGENT_SETTING_RSP", {1: 0})
            self._apply_agent_setting(f)
        elif op in ("PUSH_DEVICE_PACKAGE_UPGRADE_INFO_REQ", "DEVICE_WORKSTATUS_REPORT_REQ"):
            self._reply(sock, pkt, op.replace("_REQ", "_RSP"), {1: 0})
        elif op == "DEVICE_MAPID_GET_CONSUMABLES_PARAM_RSP":
            # el robot da el % de USO de cada pieza (app oficial); CA trabaja en horas de uso
            keys = ("main_brush", "side_brush", "filter", "dishcloth")
            self.state.consumables = {
                k: round(int(pb.first(f, i + 1, 0)) * CONSUMABLE_LIFE_H[k] / 100)
                for i, k in enumerate(keys)}
            self._notify()
        elif op == "DEVICE_EVENT_REPORT_CLEANTASK":
            self._reply(sock, pkt, "UNK_11A4", {1: 0})
        elif op == "DEVICE_EVENT_REPORT_CLEANMAP":
            self._reply(sock, pkt, "DEVICE_EVENT_REPORT_RSP",
                        {1: 0, 3: {1: pb.first(f, 1, 0)}})
        elif op == "DEVICE_CLEANMAP_BINDATA_REPORT_REQ":
            self._reply(sock, pkt, "DEVICE_CLEANMAP_BINDATA_REPORT_RSP",
                        {1: 0, 3: pb.first(f, 1, 0)})
        elif op == "DEVICE_EVENT_REPORT_REQ":
            self._reply(sock, pkt, "UNK_11A7", {1: 0})
        elif op == "DEVICE_SETTIME_REQ":
            self._reply(sock, pkt, "DEVICE_SETTIME_RSP",
                        {1: int(time.time()), 2: cmd.tz_offset_min() * 60})
        elif op in ("DEVICE_MAPID_PUSH_MAP_INFO", "DEVICE_MAPID_GET_GLOBAL_INFO_RSP"):
            self._on_map(pkt.payload)
        elif op == "DEVICE_MAPID_PUSH_POSITION_INFO":
            p = mapdecode.decode_robot_position(pkt.payload)
            if p["update"]:
                self._on_pose(p)
        elif op == "DEVICE_MAPID_PUSH_CHARGE_POSITION_INFO":
            self._lmap["charger"] = mapdecode.decode_charge_position(pkt.payload)
        elif op == "DEVICE_MAPID_PUSH_HAS_WAITING_BE_SAVED":
            self.log("  [legacy] el robot tiene un mapa nuevo pendiente de guardar")
            self.state.pending_map = True
            self._notify()
        elif op == "DEVICE_ORDERLIST_GETTING_RSP":       # horarios guardados en el robot
            self.orders = parse_orders(f)
            self.log(f"  [legacy] horarios guardados en el robot: {len(self.orders)}")
            self._fire(self.on_orders)
        elif op == "DEVICE_WLAN_INFO_GETTING_RSP":       # red del robot (solo lectura)
            body = pb.decode(pb.first(f, 3, b""))
            self.state.wifi = {"ssid": pb.as_str(pb.first(body, 2, b"")),
                               "ip": pb.as_str(pb.first(body, 1, b""))}
            self._notify()
        elif op.endswith("_RSP"):
            pass                       # respuestas a nuestras peticiones
        elif op not in self._unhandled:
            self._unhandled.add(op)
            self.log(f"  [legacy] opcode sin tratar aún: {op} ({len(pkt.payload)} B)")

    def _adopt_ids(self, pkt: Packet) -> bool:
        """Adopta el deviceId del robot (y el userId de la nube que recuerda). False si la
        trama no trae deviceId (robot sin registrar: debe mandar DEVICE_REGISTER_REQ)."""
        if not pkt.device_id:
            return False
        if pkt.device_id != self._device_id:
            if self._device_id is not None:
                self.log(f"  [legacy] el robot cambia de id {self._device_id} -> {pkt.device_id}")
            self._device_id = pkt.device_id
        if pkt.user_id and pkt.user_id != self._user_id and not pkt.opname.endswith("_RSP"):
            self.log(f"  [legacy] uso el userId que recuerda el robot ({pkt.user_id})")
            self._user_id = pkt.user_id
        return True

    def _on_register(self, sock, pkt: Packet, f: dict):
        g = lambda n: pb.as_str(pb.first(f, n, b""))
        self.captured.update({
            "software": g(1), "hardware": g(2), "sn": g(3), "mac": g(4),
            "device_type": pb.first(f, 5), "factory_id": str(pb.first(f, 6, "")),
            "ctrl_version": g(7),
        })
        if self._device_id is None:
            self._device_id = random.randint(1, 2**31 - 1)
        self.log(f"[legacy] robot registrado: fw {g(1)} hw {g(2)} tipo {pb.first(f, 5)} "
                 f"ctrl {g(7)}")
        self._reply(sock, pkt, "DEVICE_REGISTER_RSP", {1: 0, 3: {1: self._device_id}})
        self._attach(sock)

    def _apply_agent_setting(self, f: dict):
        """PUSH_DEVICE_AGENT_SETTING_REQ: voz (campo 2) y horario silencioso (campo 7)."""
        voice = pb.decode(pb.first(f, 2, b""))
        quiet = pb.decode(pb.first(f, 7, b""))
        pref = pb.decode(pb.first(f, 3, b""))           # cleanPreference: 5 = historyMap
        if 5 in pref:
            self.state.persistent_map = bool(pb.first(pref, 5))
        if voice:
            self.state.voice = {"voiceMode": int(pb.first(voice, 1, 1)),
                                "volume": max(0, int(pb.first(voice, 2, 11)) - 1)}   # 1..11 -> 0..10
        if quiet:
            self.state.quiet = {"is_open": int(pb.first(quiet, 1, 0)),
                                "begin_time": pb.first(quiet, 2, 1320),
                                "end_time": pb.first(quiet, 3, 420)}
        if voice or quiet:
            self._notify()

    def _apply_status(self, f: dict):
        g = lambda n, d=None: pb.first(f, n, d)
        s = self.state
        mode, charging, fault = g(3), bool(g(5, 0)), g(7, 0)
        s.online = True
        s.work_mode = mode
        s.charging = charging
        s.fault = fault
        s.warning = _warn_message(fault)
        s.state = legacy_state(g(6, 0), mode, charging, fault)
        if g(4) is not None:
            s.battery = battery_pct(g(4))
        # TODO(legacy): confirmar unidades con un log real (aquí se asume como en la gen.
        # nueva: cleanSize en centésimas de m², cleanTime en minutos).
        if g(11) is not None:
            s.area = round(g(11) / 100.0, 2)
        if g(10) is not None:
            s.clean_time = g(10)
        if g(9) is not None:
            s.repeat_clean = g(9)
        if g(1):
            s.map_head_id = g(1)
        self._notify()

    # ---------------- mapa ----------------
    def _on_map(self, payload: bytes):
        try:
            d = mapdecode.decode_map(payload)
        except Exception as e:
            self.log(f"  [legacy] mapa no decodificable ({len(payload)} B): {e}")
            return
        # no todos los pushes traen todas las secciones (mask): se conserva la última de cada una
        for k in ("head", "grid", "rooms", "charger", "robot", "walls", "maps", "plans"):
            if d.get(k) is not None:
                self._lmap[k] = d[k]
        head = self._lmap.get("head")
        if not head or not self._lmap.get("grid"):
            return
        mid = head["map_head_id"]
        name = next((m["name"] for m in self._lmap.get("maps", []) if m["map_head_id"] == mid), "")
        self.state.map_head_id = mid
        if name:
            self.state.map_name = name
        try:
            self.map = cmap.build_map(self._legacy_info(name), head["size_x"], head["size_y"])
        except ValueError as e:
            self.log(f"  [legacy] mapa vacío o incompleto: {e}")
            return
        self.map_empty = False
        self.pose = self.map.get("robot")
        self._accumulate_trail()
        zsig = json.dumps(self.map.get("stored_zones", []), sort_keys=True)
        if self.map["cells_b64"] != self._last_cells or zsig != self._last_zones:
            self._last_cells, self._last_zones = self.map["cells_b64"], zsig
            self._fire(self.on_map)
        else:
            self._fire(self.on_pose)

    def _legacy_info(self, name: str) -> dict:
        """Mapa legacy -> `info` común de cmap.build_map (misma rejilla y valores que la gen.
        nueva: 0 desconocido, 1/255 pared, 10+ habitación)."""
        L, head = self._lmap, self._lmap["head"]
        pose = lambda p: {"x": p["x"], "y": p["y"], "angle": p["phi"]} if p else None
        zones = []
        for w in (L.get("walls") or {}).get("areas", []):
            pts = list(dict.fromkeys(w["points"]))       # el robot repite los puntos (A,B,A,B)
            if pts:
                zones.append({"type": 200, "name": "", "points": pts})   # pared virtual
        return {
            "grid": L["grid"],
            "rooms": [(r["id"], r["name"], None, None) for r in L.get("rooms", [])],
            "map_name": name,
            "params": {"min_x": head["min_x"], "min_y": head["min_y"], "res": head["resolution"]},
            "pose": pose(L.get("charger")),
            "robot": pose(L.get("robot")),
            "zones": zones,
            # mapas guardados en el robot (sección de planes): CA los lista como la "casa"
            "house": {"id": None, "name": "",
                      "maps": [{"id": m["map_head_id"], "name": m["name"]}
                               for m in L.get("maps") or []]},
        }

    def _on_pose(self, p: dict):
        """Pose suelta (0x1166, ~1/s): mundo -> celda del último mapa emitido."""
        self._lmap["robot"] = p
        m = self.map
        if not m:
            return
        w, b = m["world"], m["bbox"]
        cell = {"x": round((p["x"] - w["min_x"]) / w["res"] - b[0], 1),
                "y": round((p["y"] - w["min_y"]) / w["res"] - b[1], 1), "angle": p["phi"]}
        m["robot"] = self.pose = cell
        m["robot_world"] = {"x": p["x"], "y": p["y"]}
        self._accumulate_trail()
        self._fire(self.on_pose)

    def _accumulate_trail(self):
        """Traza del recorrido en METROS mientras limpia (mismo criterio que RealRobot)."""
        mh = self.state.map_head_id
        if mh != self._trail_map:
            self._trail_map, self.trail, self._trail_last = mh, [], None
        rw = (self.map or {}).get("robot_world")
        if not rw or rw.get("x") is None or self.state.state not in ("cleaning", "mapping"):
            return
        pt = [round(rw["x"], 2), round(rw["y"], 2)]
        last = self._trail_last
        if last is not None and abs(pt[0] - last[0]) + abs(pt[1] - last[1]) < 0.08:
            return
        self.trail.append(pt)
        self._trail_last = pt
        if len(self.trail) > 1000:
            self.trail = self.trail[::2]

    def _fire(self, cb):
        if cb:
            try:
                cb()
            except Exception:
                pass

    def _notify(self):
        self._fire(self.on_update)
