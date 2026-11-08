"""TuyaRobot — robots aspiradores sobre Tuya en local (Conga 8290 y otros «ThingClips»).

Habla con el robot directamente por la red local (protocolo Tuya 3.3/3.4, puerto 6668), con su
`local key`. Sin nube: el robot empuja cada cambio de sus DPs (data points) y aquí se traducen al
estado de Clean Assistant; los `control` del 8090 que manda la interfaz se traducen a DPs.

DPs del Conga 8290 (esquema y registros de @ftorrealbaa, issue #8). El mapa aún no: el robot no lo
manda por la red local en lo capturado hasta ahora (va por la nube de Tuya).
Los horarios no se usan todavía (sin mapa no hay habitaciones).
"""
from __future__ import annotations
import base64
import json
import os
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from .. import commands as cmd
from ..state import RobotState, WARN_MESSAGES
from .proto import PORT, HEARTBEAT_S, TuyaDevice, TuyaError

RETRY_S = 10.0               # reintento de conexión
OFFLINE_AFTER_S = 30.0       # sin conexión tanto tiempo -> robot desconectado
SILENT_S = 15.0              # conectado pero sin ningún dato del robot -> avisar en el registro
REDISCOVER_S = 120.0         # IP cambiada: buscar al robot por la subred
PROBE_TIMEOUT = 0.6
DIRECT_STOP_S = 0.6          # mando manual: sin pulsos -> parar
DIRECT_IDLE_S = 4.0          # y luego salir del modo manual

# DPs (códigos del esquema Tuya del robot)
DP_GO, DP_PAUSE, DP_CHARGE, DP_MODE, DP_STATUS = "1", "2", "3", "4", "5"
DP_TIME, DP_AREA, DP_BATTERY, DP_SUCTION, DP_WATER = "6", "7", "8", "9", "10"
DP_SEEK, DP_DIRECTION, DP_FRAME = "11", "12", "15"
DP_DND, DP_VOLUME, DP_FAULT = "25", "26", "28"
DP_TOT_AREA, DP_TOT_COUNT, DP_TOT_TIME = "29", "30", "31"
DP_DUST_NOW, DP_MOP_STATE, DP_WORK_MODE = "38", "40", "41"
DP_CARPET_BOOST, DP_CLEAN_WAY, DP_SOUND = "45", "105", "108"

# succión de CA (commands.FAN: Off, Eco, Normal, Turbo) <-> DP 9 (close, gentle, normal, strong, max)
FAN_TO_ROBOT = {0: "close", 1: "gentle", 2: "normal", 3: "strong"}
ROBOT_TO_FAN = {"close": 0, "gentle": 1, "normal": 2, "strong": 3, "max": 3}
# agua de CA (commands.WATER: 10 Off … 13 Alto) <-> DP 10 (close, low, middle, high)
WATER_TO_ROBOT = {10: "close", 11: "low", 12: "middle", 13: "high"}
# modo de CA (commands.CLEAN_MODES) -> DP 105 cleaning_way. «Bordes» es «acrubbing»: es lo que
# manda la app de Cecotec al elegir Bordes (registro con hora de @ftorrealbaa, 31-oct-2026)
MODE_TO_WAY = {0: "auto", 14: "clean_thoroughly", 1: "acrubbing", 5: "espiral", 15: "espiral_cuadrada",
               2: "auto"}
MODE_MOP = 2                 # «Fregado»: solo fregar (DP 41 only_mop)
CLEAN_MODES = ("Auto", "Limpieza completa", "Fregado", "Bordes", "Espiral", "Espiral cuadrada")

# DPs que cambian solos durante la limpieza (tiempo, área, batería, trama del mapa, vida de
# consumibles): no se registran
_QUIET_DPS = {DP_TIME, DP_AREA, DP_BATTERY, DP_FRAME, "17", "19", "21", "23", DP_TOT_AREA, DP_TOT_COUNT, DP_TOT_TIME}

# DP 5 -> estado de CA
_STATES = {"smart": "cleaning", "zone_clean": "cleaning", "select_room": "cleaning",
           "part_clean": "cleaning", "goto_pos": "cleaning", "game": "cleaning",
           "mapping": "mapping", "paused": "paused", "goto_charge": "returning",
           "charging": "docked", "charge_done": "docked", "collecting_dust": "docked"}
_CHARGING = ("charging", "charge_done", "collecting_dust")

# consumibles: DP de minutos restantes, vida total (min, del esquema) y DP de reinicio
CONSUMABLES = {"side_brush": ("17", 9000, "18"), "main_brush": ("19", 18000, "20"),
               "filter": ("21", 9000, "22"), "dishcloth": ("23", 9000, "24")}
# vida en horas que usa Clean Assistant para el % (mqtt_bridge.CONSUMABLE_LIFE_H)
CA_LIFE_H = {"main_brush": 300, "side_brush": 220, "filter": 100, "dishcloth": 160}

# DP 28 (bitmap de fallos, bit = posición en el esquema) -> faultCode de CA. Se reutilizan los del
# Conga con el mismo significado (ya traducidos); los nuevos van en el rango 9000.
FAULT_BITS = ["low_power", "poweroff", "wheel_trap", "cannot_upgrade", "collision_stuck",
              "dust_station_full", "tile_error", "lidar_speed_err", "lidar_cover", "lidar_point_err",
              "front_wall_dirty", "psd_dirty", "middle_sweep", "side_sweep", "fan_speed", "dustbox_out",
              "dustbox_full", "no_dust_box", "dustbox_fullout", "trapped", "pick_up", "no_dust_water_box",
              "water_box_empty", "forbid_area", "land_check", "findcharge_fail", "battery_err",
              "kit_wheel", "kit_lidar", "kit_water_pump"]
FAULT_CODES = {"low_power": 502, "poweroff": 533, "wheel_trap": 9003, "cannot_upgrade": 517,
               "collision_stuck": 510, "dust_station_full": 590, "tile_error": 509,
               "lidar_speed_err": 500, "lidar_cover": 565, "lidar_point_err": 500,
               "front_wall_dirty": 506, "psd_dirty": 506, "middle_sweep": 519, "side_sweep": 520,
               "fan_speed": 9004, "dustbox_out": 503, "dustbox_full": 527, "no_dust_box": 503,
               "dustbox_fullout": 527, "trapped": 9005, "pick_up": 501, "no_dust_water_box": 529,
               "water_box_empty": 525, "forbid_area": 9013, "land_check": 509,
               "findcharge_fail": 511, "battery_err": 530, "kit_wheel": 9003, "kit_lidar": 500,
               "kit_water_pump": 9007}
# avisos que no impiden seguir (el resto, si el robot está parado, cuentan como error)
_NOTICES = {"low_power", "dust_station_full", "dustbox_full", "dustbox_fullout", "water_box_empty",
            "cannot_upgrade", "front_wall_dirty", "psd_dirty"}
WARN_MESSAGES.setdefault(9003, "Rueda bloqueada: revisa las ruedas")
WARN_MESSAGES.setdefault(9004, "Ventilador bloqueado: revisa el filtro y el depósito")
WARN_MESSAGES.setdefault(9005, "Robot atascado: muévelo a una zona despejada")
WARN_MESSAGES.setdefault(9007, "Bomba de agua bloqueada")
WARN_MESSAGES.setdefault(9013, "En una zona prohibida: sácalo de ella")

DIRECTIONS = {1: "forward", 4: "backward", 2: "turn_left", 3: "turn_right", 0: "stop"}


def faults(bitmap) -> list:
    """DP 28 -> nombres de los fallos activos (en orden de bit)."""
    try:
        v = int(bitmap or 0)
    except (TypeError, ValueError):
        return []
    return [name for i, name in enumerate(FAULT_BITS) if v >> i & 1]


def parse_frame(b64: str):
    """DP 15 (trama «AA 01 longitud(4) orden datos suma») -> (orden, datos) o None."""
    try:
        b = base64.b64decode(b64)
    except Exception:
        return None
    if len(b) < 7 or b[0] != 0xAA:
        return None
    n = int.from_bytes(b[2:6], "big")
    body = b[6:6 + n]
    if len(body) != n or len(b) < 7 + n or sum(body) & 0xFF != b[6 + n]:
        return None
    return body[0], bytes(body[1:])


def robot_state(dps: dict) -> str:
    st = dps.get(DP_STATUS)
    s = _STATES.get(st, "idle")
    blocking = [f for f in faults(dps.get(DP_FAULT)) if f not in _NOTICES]
    if blocking and s not in ("cleaning", "returning", "docked"):
        return "error"
    return s


class TuyaRobot:
    tuya = True
    robeye = False
    manufacturer = "Cecotec"
    stats_keys = ("time_h", "area_m2", "runs")
    clean_modes = CLEAN_MODES
    # entidades de HA del Conga que este robot no tiene (sin mapa todavía)
    ha_skip = ("_sel_mop", "_sel_base_type", "_ota", "_dust_freq", "_quiet_begin", "_quiet_end",
               "_twice", "_map", "_pose", "_room_now")

    def __init__(self, cfg, logger=print, host: str = "", dev_id: str = "", local_key: str = "",
                 version: str = "3.3", data_dir: str = ".", subnet_hint=None, device_factory=None):
        self.cfg = cfg
        self.host = host
        self.dev_id, self.local_key, self.version = dev_id.strip(), local_key.strip(), str(version or "3.3")
        self._subnet_hint = subnet_hint
        self._factory = device_factory or TuyaDevice
        self.state = RobotState()
        self.map = None
        self.map_empty = True
        self.reconnected = False
        self.pose = None
        self.trail = []
        self.orders = []
        self.on_update = self.on_map = self.on_pose = self.on_orders = self.on_provision = None
        self.captured = {"name": "Conga", "firmware": f"Tuya {self.version}"}
        self.link = "local"
        self.ota_enforce = 0
        self.log = logger
        self.stats = None
        self.dps = {}
        self._dev = None
        self._fan = 2
        self._water = 12
        self._mode = 0
        self._link_path = os.path.join(data_dir, "tuya_link.json")
        self._link = self._load_json(self._link_path, {})
        self._down_since = None
        self._rx = False
        self._last_scan = 0.0
        self._direct_mode, self._direct_ts, self._direct_moving = False, 0.0, False
        self._stop = threading.Event()
        self._seen_status = set()
        self._logged_once = False      # el primer volcado (estado completo al conectar) no se registra

    # ---------------- interfaz común ----------------
    def start(self):
        if not self.dev_id or len(self.local_key) != 16:
            self.log("[tuya] faltan TUYA_DEVICE_ID y/o TUYA_LOCAL_KEY (16 caracteres) en la configuración")
        self.host = self.host or self._link.get("ip") or ""
        threading.Thread(target=self._loop, daemon=True).start()
        self.log(f"[tuya] robot en {self.host or '(buscándolo en la red)'} (protocolo {self.version})")

    def stop(self):
        self._stop.set()
        if self._dev:
            self._dev.close()

    def tick(self) -> RobotState:
        return self.state

    def set_link(self, mode):
        if str(mode).lower() == "cloud":
            self.log("  [tuya] Clean Assistant controla este robot en local (la app oficial sigue por la nube)")

    def reconnect(self):
        if self._dev:
            self._dev.close()

    def query_orders(self):
        pass

    def command(self, control: dict) -> dict:
        c = control.get("control")
        if c == "set_mode":
            typ, val = control.get("type"), control.get("value")
            st = self.dps.get(DP_STATUS)
            if typ == 3:                                     # volver a la base / cancelarlo
                return self._set({DP_CHARGE: True} if val else {DP_PAUSE: True})
            if val == 4:                                     # elegir modo (se aplica al empezar)
                self._mode = int(typ)
                return {"result": 0}
            if val == 2:
                return self._set({DP_PAUSE: True})
            if typ == 2 and val == 1:                        # continuar
                return self._set({DP_GO: True} if st == "goto_charge" else {DP_PAUSE: False})
            if typ in (0, 14) and val == 1:                  # limpiar toda la casa
                if st == "paused":
                    return self._set({DP_PAUSE: False})
                return self._set(self._start_dps(typ))
            if typ == 7:
                return {"ok": False, "error": "este robot crea el mapa solo en su primera limpieza"}
        elif c == "set_preference":
            ct, v = control.get("ctrltype"), control.get("value")
            if ct == 1:                                      # succión
                self._fan = int(v)
                return self._set({DP_SUCTION: FAN_TO_ROBOT.get(self._fan, "normal")})
            if ct == 2:                                      # agua
                self._water = int(v)
                return self._set({DP_WATER: WATER_TO_ROBOT.get(self._water, "middle")})
            if ct == 5:                                      # turbo en alfombras
                return self._set({DP_CARPET_BOOST: bool(v)})
            return {"result": 0}                             # mopa, doble pasada, base: no aplican
        elif c == "device_ctrl" and control.get("ctrltype") == 3:      # localizar
            return self._set({DP_SEEK: True})
        elif c == "set_direct":
            return self._direct(int(control.get("direction", 0)))
        elif c == "set_consumables":
            key = {v: k for k, v in cmd.CONSUMABLE_RESET.items()}.get(int(control.get("resetType", 0)))
            if key in CONSUMABLES:
                return self._set({CONSUMABLES[key][2]: True})
            return {"result": 0}
        elif c == "set_voice":
            return self._set({DP_SOUND: bool(control.get("voiceMode")),
                              DP_VOLUME: max(0, min(100, int(control.get("volume", 7)) * 10))})
        elif c == "set_quiet":
            q = (control.get("quiet_list") or [{}])[0]
            return self._set({DP_DND: bool(q.get("is_open"))})
        elif c == "set_dust_action":
            return self._set({DP_DUST_NOW: True})
        elif c in ("get_consumables", "get_map", "getMapAll", "get_preference", "get_quiet",
                   "get_voice"):
            if self._dev and self._dev.connected:
                try:
                    self._dev.query()
                except Exception:
                    pass
            return {"result": 0}
        elif c == "setRoomClean":
            return {"ok": False, "error": "este robot aún no tiene mapa en Clean Assistant"}
        elif c in ("setOrder6090", "deleteOrder6090", "lock_device", "set_time", "set_upgrade_config",
                   "setEditInfoBeforeHand", "set_virwall", "set_area", "setPlanData6090"):
            return {"result": 0}
        self.log(f"  [tuya] comando '{c}' no soportado en este robot")
        return {"ok": False, "error": f"'{c}' no soportado (tuya)"}

    def _start_dps(self, typ) -> dict:
        mode = self._mode if typ == 0 else typ
        dps = {DP_SUCTION: FAN_TO_ROBOT.get(self._fan, "normal"),
               DP_WATER: WATER_TO_ROBOT.get(self._water, "middle"),
               DP_CLEAN_WAY: MODE_TO_WAY.get(mode, "auto")}
        if mode == MODE_MOP:
            dps[DP_WORK_MODE] = "only_mop"
        elif self.dps.get(DP_WORK_MODE) == "only_mop":
            dps[DP_WORK_MODE] = "both_work" if self.dps.get(DP_MOP_STATE) == "installed" else "only_sweep"
        dps[DP_GO] = True
        return dps

    def _set(self, dps: dict, manual: bool = False) -> dict:
        if not manual and self._direct_mode:
            self._direct_exit()               # cualquier otra orden saca del modo manual
        dev = self._dev
        if not dev or not dev.connected:
            return {"ok": False, "error": "robot no conectado"}
        try:
            dev.set_dps(dps)
        except Exception as e:
            self.log(f"  [!] tuya: error mandando {dps}: {e}")
            dev.close()
            return {"ok": False, "error": str(e)}
        self.log(f"  --> robot: {json.dumps(dps, ensure_ascii=False)}")
        return {"result": 0}

    # ---------------- mando manual ----------------
    def _direct(self, d: int) -> dict:
        self._direct_ts = time.time()            # antes de nada: el hilo de conexión vigila el plazo
        if not self._direct_mode:
            self._direct_mode = True
            r = self._set({DP_MODE: "manual"}, manual=True)
            if r.get("ok") is False:
                self._direct_mode = False
                return r
        self._direct_ts = time.time()
        self._direct_moving = d != 0
        return self._set({DP_DIRECTION: DIRECTIONS.get(d, "stop")}, manual=True)

    def _direct_exit(self):
        self._direct_mode = self._direct_moving = False
        try:
            self._dev.set_dps({DP_DIRECTION: "exit"})
        except Exception:
            pass

    def _direct_watch(self):
        if not self._direct_mode:
            return
        idle = time.time() - self._direct_ts
        if self._direct_moving and idle > DIRECT_STOP_S:
            self._direct_moving = False
            self._set({DP_DIRECTION: "stop"}, manual=True)
        elif idle > DIRECT_IDLE_S:
            self._direct_exit()

    # ---------------- conexión ----------------
    def _loop(self):
        while not self._stop.is_set():
            if not self.host or (self._down_since and time.time() - self._down_since > RETRY_S * 3
                                 and time.time() - self._last_scan > REDISCOVER_S):
                self._discover()
            if not self.host or not self.dev_id or len(self.local_key) != 16:
                self._mark_down()
                self._stop.wait(RETRY_S)
                continue
            ip, _, port = self.host.partition(":")         # «ip:puerto» para pruebas
            dev = self._factory(self.dev_id, ip, self.local_key, self.version, port=int(port or PORT),
                                on_dps=self._on_dps, log=self.log)
            try:
                dev.connect()
                self._dev = dev
                self._down_since = None
                if self._link.get("ip") != self.host:
                    self._link["ip"] = self.host
                    self._save_json(self._link_path, self._link)
                self.log(f"[tuya] conectado con el robot ({self.host})")
                beat = since = time.time()
                self._rx = False
                while not self._stop.is_set():
                    dev.poll(0.3)
                    self._direct_watch()
                    if not self._rx and since and time.time() - since > SILENT_S:
                        since = 0
                        self.log("  [tuya] el robot acepta la conexión pero no contesta: revisa la local key y "
                                 "la versión (3.3/3.4), y que no haya otra integración local conectada a la vez "
                                 "(LocalTuya, tuya-local, tinytuya monitor)")
                    if time.time() - beat > HEARTBEAT_S:
                        dev.heartbeat()
                        beat = time.time()
            except (OSError, TuyaError) as e:
                if self._down_since is None:
                    self.log(f"  [tuya] sin conexión con el robot ({self.host}): {e}")
            finally:
                dev.close()
                self._dev = None
            self._mark_down()
            self._stop.wait(RETRY_S)

    def _mark_down(self):
        now = time.time()
        if self._down_since is None:
            self._down_since = now
        if self.state.online and now - self._down_since >= OFFLINE_AFTER_S:
            self.state.online = False
            self._fire(self.on_update)

    def _on_dps(self, dps: dict):
        self._rx = True
        # lo que cambia en el robot (sin los contadores que cambian solos): así se ve en el registro
        # qué manda la app oficial al elegir un modo o una función (DPs aún sin mapear, #8)
        changed = {k: v for k, v in dps.items() if k not in _QUIET_DPS and self.dps.get(k) != v}
        if changed and self._logged_once:
            self.log(f"  <-- robot: {json.dumps(changed, ensure_ascii=False)}")
        self._logged_once = True
        self.dps.update(dps)
        st = dps.get(DP_STATUS)
        if st and st not in self._seen_status:
            self._seen_status.add(st)
            self.log(f"  [tuya] estado del robot: '{st}'")
        if DP_FRAME in dps:
            fr = parse_frame(dps[DP_FRAME])
            if fr:
                self.log(f"  [tuya] trama 0x{fr[0]:02x}: {fr[1].hex(' ')}")
        if self.dps.get(DP_SUCTION) in ROBOT_TO_FAN and not self.state.online:
            self._fan = ROBOT_TO_FAN[self.dps[DP_SUCTION]]       # al conectar; luego manda la de CA
        self._apply()

    def _apply(self):
        d, s = self.dps, self.state
        s.online = True
        s.charging = d.get(DP_STATUS) in _CHARGING
        if isinstance(d.get(DP_BATTERY), int):
            s.battery = d[DP_BATTERY]
        s.state = robot_state(d)
        if s.state == "idle" and s.charging:
            s.state = "docked"
        active = faults(d.get(DP_FAULT))
        s.fault = FAULT_CODES.get(active[0], 0) if active else 0
        s.warning = WARN_MESSAGES.get(s.fault) if s.fault else None
        if isinstance(d.get(DP_AREA), int):
            s.area = float(d[DP_AREA])
        if isinstance(d.get(DP_TIME), int):
            s.clean_time = d[DP_TIME]
        s.quiet = {"is_open": 1 if d.get(DP_DND) else 0} if DP_DND in d else s.quiet
        if DP_SOUND in d or DP_VOLUME in d:
            s.voice = {"voiceMode": 1 if d.get(DP_SOUND, True) else 0,
                       "volume": round((d.get(DP_VOLUME) or 0) / 10)}
        cons = {}
        for key, (dp, life_min, _) in CONSUMABLES.items():
            if isinstance(d.get(dp), int):          # minutos que le quedan (negativo = pasada)
                cons[key] = round(CA_LIFE_H[key] * (1 - d[dp] / life_min), 1)
        if cons:
            s.consumables = cons
        if any(k in d for k in (DP_TOT_AREA, DP_TOT_COUNT, DP_TOT_TIME)):
            self.stats = {"time_h": round((d.get(DP_TOT_TIME) or 0) / 60, 1),
                          "area_m2": int(d.get(DP_TOT_AREA) or 0), "runs": int(d.get(DP_TOT_COUNT) or 0)}
        self._fire(self.on_update)           # también consumibles, totales, voz…

    # ---------------- IP dinámica: buscar al robot por la subred ----------------
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

    @staticmethod
    def _port_open(host: str) -> bool:
        try:
            with socket.create_connection((host, PORT), timeout=PROBE_TIMEOUT):
                return True
        except OSError:
            return False

    def _identify(self, host: str) -> bool:
        """¿Es nuestro robot? Se le pide su estado con la local key: solo el nuestro responde bien."""
        got = []
        dev = self._factory(self.dev_id, host, self.local_key, self.version,
                            on_dps=lambda d: got.append(d), log=lambda *a: None)
        try:
            dev.connect()
            for _ in range(5):
                if got:
                    break
                dev.poll(0.5)
        except Exception:
            return False
        finally:
            dev.close()
        return bool(got)

    def _discover(self) -> bool:
        self._last_scan = time.time()
        cands = self._candidates()
        if not cands or not self.dev_id or len(self.local_key) != 16:
            if not cands:
                self.log("  [tuya] no sé en qué red buscar al robot: pon su IP en la opción ROBOT_IP")
            return False
        with ThreadPoolExecutor(32) as ex:
            open_ = [h for h, ok in zip(cands, ex.map(self._port_open, cands)) if ok]
        for h in open_:
            if self._identify(h):
                if h != self.host:
                    self.log(f"  [tuya] robot encontrado en {h}")
                self.host = h
                return True
        self.log(f"  [tuya] robot no encontrado en {cands[0].rsplit('.', 1)[0]}.0/24 "
                 f"({len(open_)} dispositivos Tuya en la red)")
        return False

    # ---------------- utilidades ----------------
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
            self.log(f"  [tuya] no se pudo guardar {os.path.basename(path)}: {e}")

    def _fire(self, cb):
        if cb:
            try:
                cb()
            except Exception:
                pass
