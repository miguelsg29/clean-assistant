"""RobEyeRobot — cliente HTTP de la API local de RobArt «RobEye» (Rowenta X-plorer Serie 80…).

Sin nube ni handshake: un hilo consulta `get/status`, `get/robot_flags` y `get/rob_pose` cada
pocos segundos, y el mapa (`get/areas` + `get/feature_map`) al arrancar, al cambiar de mapa y
de vez en cuando. El mapa es vectorial (polígonos de habitación + segmentos de pared); aquí se
rasteriza a la misma rejilla que la gen. nueva para reutilizar `cmap.build_map` y la interfaz.

Los `control` que manda la interfaz son los del 8090; `command` los traduce a `set/...`.
Los horarios los ejecuta Clean Assistant a su hora (como en la gen. legacy).
"""
from __future__ import annotations
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
import urllib.parse
import urllib.request

from .. import commands as cmd
from .. import map as cmap
from ..state import RobotState, WARN_MESSAGES

PORT = 8080
POLL_S = 2.0                 # estado + avisos
POSE_S = 2.0                 # pose (solo mientras se mueve; parado, cada MAP_S)
MAP_S = 60.0                 # mapa completo
OFFLINE_AFTER = 3            # fallos seguidos -> robot desconectado
# IP dinámica: si el robot deja de responder, se le busca por la subred (/24) y se le reconoce por
# su unique_id. Sin mDNS: el add-on no tiene red de host y no recibe multicast, pero sí llega por
# HTTP a toda la LAN.
PROBE_TIMEOUT = 1.0
REDISCOVER_S = 60.0
# Escala de las coordenadas del robot. Provisional (31-oct-2026): con 2 mm/unidad el piso de la
# captura sale de ~44 m², que cuadra con sus estadísticas (~38 m² por limpieza). Por confirmar.
UNIT_M = 0.002
RES = 0.05                   # metros por celda de la rejilla de CA
# el eje y del robot crece hacia arriba y la rejilla de CA hacia abajo: se invierte al leer, para que
# el mapa salga igual que en la app del robot (y el ángulo, con él)


def _flip_areas(areas):
    return [dict(a, points=[{"x": p["x"], "y": -p["y"]} for p in a.get("points") or []]) for a in areas]


def _flip_lines(lines):
    return [{"x1": l["x1"], "y1": -l["y1"], "x2": l["x2"], "y2": -l["y2"]} for l in lines]
MARGIN = 4                   # celdas libres alrededor del mapa

# succión de CA (commands.FAN: Off=«Máx» como en legacy, Eco, Normal, Turbo) -> cleaning_parameter_set
# del robot (0 Default, 1 Normal, 2 Silent, 3 Intensive, 4 Super Silent)
FAN_TO_ROBOT = {0: 3, 1: 2, 2: 1, 3: 3}
ROBOT_TO_FAN = {1: 2, 2: 1, 3: 3, 4: 1}
# estrategia (cleaning_strategy_mode): 4 Default, 1 Normal, 2 Paredes/esquinas, 3 A fondo
STRATEGY_DEFAULT, STRATEGY_EDGES, STRATEGY_DEEP = 4, 2, 3

# room_type del robot -> (nombre por defecto, roomTypeId de la interfaz)
ROOM_TYPES = {"living": ("Salón", 2106), "sleeping": ("Dormitorio", 2101), "bath": ("Baño", 2103),
              "corridor": ("Pasillo", 2104), "kitchen": ("Cocina", 2105), "dining": ("Comedor", 2102)}

# robot_flags -> faultCode de CA. Se reutilizan los códigos del Conga con el mismo significado
# (así ya tienen texto y traducción); los propios de RobEye van en el rango 9000.
FLAG_CODES = {
    "lifted": 501, "battery_low": 502, "battery_critical": 518, "dustbin_missing": 503,
    "dustbin_full": 527, "water_tank_empty": 525, "stuck_main_brush": 519,
    "stuck_side_brush": 520, "stuck_bumper": 510, "stuck_drop_sensor": 509,
    "battery_temp_critical": 530,
    "toplid_open": 9001, "main_brush_missing": 9002, "stuck_wheel": 9003, "stuck_fan": 9004,
    "stuck_behavior": 9005, "stuck_wheelswitch": 9006, "stuck_water_pump": 9007,
    "missing_water_pump": 9008, "stuck_wet_pad_agitator": 9009, "missing_wet_pad_agitator": 9010,
    "safety_supervisor_safety_stop": 9011, "safety_supervisor_eternal_stop": 9011,
    "missing_camera_data": 9012, "missing_imu_data": 9012, "layers_not_running": 9012,
}
WARN_MESSAGES.update({
    9001: "Tapa abierta: ciérrala para poder limpiar",
    9002: "Falta el cepillo central: colócalo",
    9003: "Rueda bloqueada: revisa las ruedas",
    9004: "Ventilador bloqueado: revisa el filtro y el depósito",
    9005: "Robot atascado: muévelo a una zona despejada",
    9006: "Rueda atascada: revisa que no esté enganchada",
    9007: "Bomba de agua bloqueada",
    9008: "Falta la bomba de agua",
    9009: "Agitador de la mopa bloqueado",
    9010: "Falta el agitador de la mopa",
    9011: "Parada de seguridad: reinicia el robot",
    9012: "Error interno del robot: reinícialo",
})
# avisos que NO son error (el robot sigue operativo)
_NOTICE_CODES = {502, 527, 525, 530}


def robot_state(mode: str, charging: str, flags: dict) -> str:
    """mode de get/status (+ charging, robot_flags) -> estado de CA."""
    m = (mode or "").lower()
    if (flags or {}).get("error"):
        return "error"
    if m in ("cleaning", "clean", "spot_cleaning", "area_cleaning") or m.startswith("clean"):
        return "cleaning"
    if m in ("exploring", "explore", "mapping") or m.startswith("explor"):
        return "mapping"
    if m in ("docking", "go_home", "returning", "homing"):
        return "returning"
    if m in ("pause", "paused", "interrupted"):
        return "paused"
    if m == "error":
        return "error"
    if charging in ("connected", "charging", "charged") or m in ("docked", "charging"):
        return "docked"
    return "idle"


def _pip(x, y, poly) -> bool:
    """¿Está (x, y) dentro del polígono? (par-impar)"""
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[i - 1]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def rasterize(areas: list, lines: list):
    """Habitaciones (polígonos) + paredes (segmentos), en unidades del robot -> (grid, W, H,
    params) con los valores de CA: 0 desconocido, 1 pared, id de habitación."""
    rooms = [a for a in areas if a.get("area_type") == "room" and a.get("area_state") != "inactive"]
    pts = [(p["x"], p["y"]) for a in rooms for p in a["points"]]
    pts += [(l["x1"], l["y1"]) for l in lines] + [(l["x2"], l["y2"]) for l in lines]
    if not pts:
        raise ValueError("mapa vacío")
    step = RES / UNIT_M
    min_x = min(p[0] for p in pts) - MARGIN * step
    min_y = min(p[1] for p in pts) - MARGIN * step
    W = int((max(p[0] for p in pts) - min_x) / step) + MARGIN + 1
    H = int((max(p[1] for p in pts) - min_y) / step) + MARGIN + 1
    grid = bytearray(W * H)
    cell = lambda x, y: (int((x - min_x) / step), int((y - min_y) / step))
    for a in rooms:
        rid = int(a["id"])
        if not 2 <= rid < cmap.CLEANED_OFFSET:      # 0/1 son desconocido/pared; +50 = «ya limpiado»
            continue
        poly = [(p["x"], p["y"]) for p in a["points"]]
        (cx0, cy0), (cx1, cy1) = cell(min(p[0] for p in poly), min(p[1] for p in poly)), \
            cell(max(p[0] for p in poly), max(p[1] for p in poly))
        for cy in range(cy0, cy1 + 1):
            wy = min_y + (cy + 0.5) * step
            for cx in range(cx0, cx1 + 1):
                if _pip(min_x + (cx + 0.5) * step, wy, poly):
                    grid[cy * W + cx] = rid
    for l in lines:                                  # paredes encima
        (x0, y0), (x1, y1) = cell(l["x1"], l["y1"]), cell(l["x2"], l["y2"])
        n = max(abs(x1 - x0), abs(y1 - y0), 1)
        for i in range(n + 1):
            x, y = round(x0 + (x1 - x0) * i / n), round(y0 + (y1 - y0) * i / n)
            if 0 <= x < W and 0 <= y < H:
                grid[y * W + x] = 1
    return grid, W, H, {"min_x": min_x * UNIT_M, "min_y": min_y * UNIT_M, "res": RES}


class RobEyeRobot:
    robeye = True

    def __init__(self, cfg, logger=print, host: str = "", names_path: str = "robeye_rooms.json",
                 http_get=None, subnet_hint=None):
        self.cfg = cfg
        self.host = host                 # IP del robot (opción ROBOT_IP; vacía = buscarlo)
        self._subnet_hint = subnet_hint  # () -> una IP de la LAN (la de HA) para buscar al robot
        self.state = RobotState()
        self.map = None
        self.map_empty = False
        self.reconnected = False
        self.pose = None
        self.trail = []
        self.orders = []
        self.on_update = self.on_map = self.on_pose = self.on_orders = self.on_provision = None
        self.captured = {}
        self.link = "local"
        self.ota_enforce = 0
        self.log = logger
        self._get = http_get or self._http_get
        self._names_path = names_path
        self._names = self._load_names()  # {area_id: nombre} puestos en Clean Assistant
        self._link_path = os.path.join(os.path.dirname(names_path) or ".", "robeye_link.json")
        self._link = self._load_json(self._link_path, {})   # última IP + unique_id del robot
        self._last_scan = 0.0
        self._fan = 1                      # cleaning_parameter_set para la próxima limpieza
        self._mode = 0                     # commands.CLEAN_MODES elegido en la interfaz
        self._twice = False
        self._paused = False               # parado con «pausa»: el robot dice 'ready', CA «paused»
        self._areas, self._lines, self._dock, self._map_id, self._maps = [], [], None, None, []
        self._map_ts = 0.0
        self._fails = 0
        self._seen_modes = set()
        self._stop = threading.Event()
        self._trail_last = None

    # ---------------- interfaz común ----------------
    def start(self):
        self.host = self.host or self._link.get("ip") or ""
        if self.host:
            try:                         # nombre y firmware (para el dispositivo en HA)
                self._adopt(self.host, self._get("get/robot_id") or {})
            except Exception as e:
                self.log(f"  [robeye] el robot no responde en {self.host}: {e}")
        threading.Thread(target=self._loop, daemon=True).start()
        self.log(f"[robeye] robot en {self.host or '(buscándolo en la red)'}")

    def stop(self):
        self._stop.set()

    def tick(self) -> RobotState:
        return self.state

    def set_link(self, mode):
        if str(mode).lower() == "cloud":
            self.log("  [robeye] este robot no usa nube: siempre es local")

    def reconnect(self):
        self._map_ts = 0.0

    def query_orders(self):
        pass                             # los horarios los guarda y lanza Clean Assistant

    def command(self, control: dict) -> dict:
        c = control.get("control")
        if c == "set_mode":
            typ, val = control.get("type"), control.get("value")
            if typ == 3:                                     # volver a la base / cancelarlo
                self._paused = False
                return self._set("go_home" if val else "stop")
            if val == 4:                                     # elegir modo
                self._mode = int(typ)
                return {"result": 0}
            if val == 2:                                     # pausa = parar (luego «continuar»)
                self._paused = True
                return self._set("stop")
            if typ == 2 and val == 1:
                self._paused = False
                return self._set("continue")
            if typ in (0, 14) and val == 1:                  # limpiar todo
                self._paused = False
                return self._set("clean_all", **self._clean_params())
        elif c == "setRoomClean":
            ids = [int(r) for r in control.get("roomsID") or []]
            if not ids or self._map_id is None:
                return {"ok": False, "error": "sin mapa o sin habitaciones"}
            self._twice, self._paused = bool(control.get("clean_type")), False
            return self._set("clean_map", map_id=self._map_id,
                             area_ids=",".join(str(i) for i in ids), **self._clean_params())
        elif c == "set_preference" and control.get("ctrltype") == 1:   # succión
            self._fan = FAN_TO_ROBOT.get(int(control["value"]), 1)
            if self.state.state == "cleaning":
                return self._set("switch_cleaning_parameter_set", cleaning_parameter_set=self._fan)
            return {"result": 0}
        elif c == "set_preference" and control.get("ctrltype") == 3:   # doble pasada -> a fondo
            self._twice = bool(control["value"])
            return {"result": 0}
        elif c == "set_preference":                          # agua/mopa/alfombras: no aplican
            return {"result": 0}
        elif c == "setPlanData6090":                         # renombrar habitaciones (solo en CA)
            for r in control.get("roomInfo") or []:
                name = (r.get("roomName") or "").strip()
                if name:
                    self._names[int(r["roomID"])] = name
            self._save_names()
            self._build_map(force=True)
            return {"result": 0}
        elif c in ("get_map", "getMapAll"):
            self._map_ts = 0.0
            return {"result": 0}
        elif c in ("setOrder6090", "deleteOrder6090", "lock_device", "set_time", "set_upgrade_config"):
            return {"result": 0}                             # horarios: los lanza Clean Assistant
        self.log(f"  [robeye] comando '{c}' no soportado en este robot")
        return {"ok": False, "error": f"'{c}' no soportado (robeye)"}

    # ---------------- HTTP ----------------
    def _http_get(self, path: str, params: dict | None = None):
        q = ("?" + urllib.parse.urlencode(params, safe=",")) if params else ""
        host = self.host if ":" in self.host else f"{self.host}:{PORT}"   # «ip:puerto» para pruebas
        with urllib.request.urlopen(f"http://{host}/{path}{q}", timeout=6) as r:
            return json.loads(r.read().decode("utf-8", "replace"))

    def _set(self, name: str, **params) -> dict:
        try:
            r = self._get(f"set/{name}", params or None)
        except Exception as e:
            self.log(f"  [!] robeye: error mandando {name}: {e}")
            return {"ok": False, "error": str(e)}
        self.log(f"  --> robot: {name}")
        self._poll_status()
        return {"result": 0, "cmd_id": (r or {}).get("cmd_id")}

    def _clean_params(self) -> dict:
        strategy = (STRATEGY_EDGES if self._mode == cmd.CLEAN_MODES.get("Bordes")
                    else STRATEGY_DEEP if self._twice else STRATEGY_DEFAULT)
        return {"cleaning_parameter_set": self._fan, "cleaning_strategy_mode": strategy}

    # ---------------- sondeo ----------------
    def _loop(self):
        while not self._stop.is_set():
            if (not self.host or self._fails >= OFFLINE_AFTER) and \
                    time.time() - self._last_scan > REDISCOVER_S:
                self._discover()
            if not self.host:
                self._stop.wait(POLL_S)
                continue
            self._poll_status()
            moving = self.state.state in ("cleaning", "mapping", "returning")
            if self.state.online and (moving or time.time() - self._map_ts > MAP_S):
                self._poll_pose()
            if self.state.online and time.time() - self._map_ts > MAP_S:
                self._build_map()
            self._stop.wait(POLL_S)

    def _poll_status(self):
        try:
            st = self._get("get/status")
            flags = self._get("get/robot_flags")
        except Exception as e:
            self._fails += 1
            if self._fails == OFFLINE_AFTER and self.state.online:
                self.log(f"  [robeye] el robot no responde: {e}")
                self.state.online = False
                self._fire(self.on_update)
            return
        self._fails = 0
        self._apply_status(st, flags)

    def _apply_status(self, st: dict, flags: dict):
        s = self.state
        was = (s.online, s.state, s.battery, s.fault)
        mode = st.get("mode")
        if mode not in self._seen_modes:
            self._seen_modes.add(mode)
            self.log(f"  [robeye] modo del robot: '{mode}' (cargando: {st.get('charging')})")
        s.online = True
        s.charging = st.get("charging") in ("connected", "charging", "charged")
        if isinstance(st.get("battery_level"), (int, float)):
            s.battery = int(st["battery_level"])
        if not was[0] and st.get("cleaning_parameter_set") in ROBOT_TO_FAN:
            self._fan = st["cleaning_parameter_set"]      # al conectar; luego manda la de CA
        codes = [FLAG_CODES[f] for k in ("error", "not_ready", "notification")
                 for f in (flags or {}).get(k) or [] if f in FLAG_CODES]
        s.fault = codes[0] if codes else 0
        s.warning = WARN_MESSAGES.get(s.fault) if s.fault else None
        real_err = {"error": [f for f in (flags or {}).get("error") or []
                              if FLAG_CODES.get(f) not in _NOTICE_CODES]}
        s.state = robot_state(mode, st.get("charging"), real_err)
        # el robot no tiene pausa: CA la hace con stop y el robot queda en 'ready' fuera de la base
        if s.state != "idle":
            self._paused = False
        elif self._paused:
            s.state = "paused"
        if (s.online, s.state, s.battery, s.fault) != was:
            self._fire(self.on_update)

    def _poll_pose(self):
        try:
            p = self._get("get/rob_pose")
        except Exception:
            return
        if not p or not p.get("valid") or self.map is None:
            return
        w, b = self.map["world"], self.map["bbox"]
        x, y = p["x1"] * UNIT_M, -p["y1"] * UNIT_M
        cellp = {"x": round((x - w["min_x"]) / w["res"] - b[0], 1),
                 "y": round((y - w["min_y"]) / w["res"] - b[1], 1),
                 "angle": -(p.get("heading") or 0) / 1000.0}
        if cellp == self.pose:
            return
        self.map["robot"] = self.pose = cellp
        self.map["robot_world"] = {"x": x, "y": y}
        self._accumulate_trail(x, y)
        self._fire(self.on_pose)

    def _build_map(self, force: bool = False):
        try:
            if not force:
                ms = self._get("get/map_status") or {}
                mid = ms.get("active_map_id")
                if mid is None or mid < 0:
                    self._map_ts = time.time()
                    self.map_empty = True
                    return
                areas = (self._get("get/areas", {"map_id": mid}) or {}).get("areas") or []
                fm = (self._get("get/feature_map", {"map_id": mid}) or {}).get("map") or {}
                maps = (self._get("get/maps") or {}).get("maps") or []
                self._map_id, self._areas = mid, _flip_areas(areas)
                self._lines = _flip_lines(fm.get("lines") or [])
                dock = fm.get("docking_pose")
                self._dock = dict(dock, y=-dock["y"], heading=-(dock.get("heading") or 0)) if dock else None
                self._maps = maps
            self._map_ts = time.time()
            if not self._areas:
                return
            self.map = self._map_from(self._areas, self._lines, self._dock)
        except Exception as e:
            self.log(f"  [robeye] no se pudo leer el mapa: {e}")
            self._map_ts = time.time()
            return
        self.map_empty = False
        self.state.map_head_id = self._map_id
        self.state.map_name = self.map.get("name")
        self._fire(self.on_map)

    def _map_from(self, areas, lines, dock) -> dict:
        grid, W, H, prm = rasterize(areas, lines)
        rooms, count = [], {}
        for a in areas:
            if a.get("area_type") != "room" or a.get("area_state") == "inactive":
                continue
            rid = int(a["id"])
            name, tid = ROOM_TYPES.get(a.get("room_type"), ("Habitación", None))
            count[name] = count.get(name, 0) + 1
            default = name if count[name] == 1 else f"{name} {count[name]}"
            rooms.append((rid, self._names.get(rid) or default, tid, None))
        zones = [{"type": 200, "name": "",
                  "points": [(p["x"] * UNIT_M, p["y"] * UNIT_M) for p in a["points"]]}
                 for a in areas if a.get("area_state") == "blocking"]
        maps = self._maps
        name = next((m.get("map_meta_data") for m in maps if m.get("map_id") == self._map_id), "")
        info = {"grid": grid, "rooms": rooms, "map_name": name or "Interior", "params": prm,
                "pose": ({"x": dock["x"] * UNIT_M, "y": dock["y"] * UNIT_M,
                          "angle": (dock.get("heading") or 0) / 1000.0} if dock else None),
                "robot": None, "zones": zones,
                "house": {"id": None, "name": "",
                          "maps": [{"id": m["map_id"], "name": m.get("map_meta_data") or ""}
                                   for m in maps if m.get("permanent_flag") in (True, "true")]}}
        m = cmap.build_map(info, W, H)
        if self.pose:                                  # conserva la última pose conocida
            m["robot"] = self.pose
        return m

    def _accumulate_trail(self, x: float, y: float):
        if self.state.state not in ("cleaning", "mapping"):
            return
        pt = [round(x, 2), round(y, 2)]
        last = self._trail_last
        if last is not None and abs(pt[0] - last[0]) + abs(pt[1] - last[1]) < 0.08:
            return
        self.trail.append(pt)
        self._trail_last = pt
        if len(self.trail) > 1000:
            self.trail = self.trail[::2]

    # ---------------- IP dinámica: buscar al robot por la subred ----------------
    def _adopt(self, host: str, rid: dict):
        self.captured = {"name": rid.get("name"), "firmware": rid.get("firmware")}
        uid = rid.get("unique_id") or rid.get("camlas_unique_id")
        if host != self._link.get("ip") or (uid and uid != self._link.get("unique_id")):
            self._link = {"ip": host, "unique_id": uid or self._link.get("unique_id")}
            self._save_json(self._link_path, self._link)

    def _identify(self, host: str):
        """robot_id de un RobEye en `host`, o None."""
        try:
            hp = host if ":" in host else f"{host}:{PORT}"
            with urllib.request.urlopen(f"http://{hp}/get/robot_id", timeout=PROBE_TIMEOUT) as r:
                rid = json.loads(r.read().decode("utf-8", "replace"))
            return rid if isinstance(rid, dict) and "firmware" in rid else None
        except Exception:
            return None

    def _candidates(self) -> list:
        base = self.host or self._link.get("ip") or ""
        if not base and self._subnet_hint:
            try:
                base = self._subnet_hint() or ""
            except Exception:
                base = ""
        parts = base.split(":")[0].split(".")
        if len(parts) != 4:
            return []
        net = ".".join(parts[:3])
        return [f"{net}.{i}" for i in range(1, 255)]

    def _discover(self) -> bool:
        self._last_scan = time.time()
        cands = self._candidates()
        if not cands:
            self.log("  [robeye] no sé en qué red buscar al robot: pon su IP en la opción ROBOT_IP")
            return False
        uid = self._link.get("unique_id")
        with ThreadPoolExecutor(32) as ex:
            found = [(h, r) for h, r in zip(cands, ex.map(self._identify, cands)) if r]
        for h, r in found:
            if not uid or (r.get("unique_id") or r.get("camlas_unique_id")) == uid:
                if h != self.host:
                    self.log(f"  [robeye] robot encontrado en {h}")
                self.host, self._fails = h, 0
                self._adopt(h, r)
                return True
        self.log(f"  [robeye] robot no encontrado en {cands[0].rsplit('.', 1)[0]}.0/24")
        return False

    # ---------------- nombres de habitación (el robot no los guarda) ----------------
    def _load_names(self) -> dict:
        return {int(k): v for k, v in self._load_json(self._names_path, {}).items()}

    def _save_names(self):
        self._save_json(self._names_path, self._names)

    @staticmethod
    def _load_json(path: str, default):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default

    def _save_json(self, path: str, data):
        try:
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            os.replace(tmp, path)
        except Exception as e:
            self.log(f"  [robeye] no se pudo guardar {os.path.basename(path)}: {e}")

    def _fire(self, cb):
        if cb:
            try:
                cb()
            except Exception:
                pass
