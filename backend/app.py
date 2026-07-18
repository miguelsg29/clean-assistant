"""Clean Assistant — backend FastAPI.

Expone el robot (real o simulado) como una API REST + WebSocket, y sirve el
frontend. En v0.1 usa el robot simulado (`MockRobot`); el robot real (servidor
TLS+WS que suplanta la nube) se enchufará aquí mismo con la misma interfaz.

Arrancar:  uvicorn backend.app:app --reload
"""
from __future__ import annotations
import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from conga_core import commands as cmd
from conga_core import map as cmap
from conga_core.config import load_env, save_identity
from backend.mock import MockRobot
from backend.zones import ZoneStore
from backend.schedules import ScheduleStore, suggested_plans
from backend.mqtt_bridge import MqttBridge

STATIC = Path(__file__).parent / "static"
env = load_env()

# Carpeta de datos persistentes (mapa, zonas, horarios, vista, enlace, identidad).
# Por defecto el directorio actual (desarrollo); en el add-on se apunta a /data.
DATA_DIR = os.environ.get("DATA_DIR", ".")
def _data(name: str) -> str:
    return os.path.join(DATA_DIR, name)

# CONGA_MODE=real -> servidor TLS+WS que habla con tu Conga (necesita datos en .env
# y certificados). Por defecto 'mock': robot simulado, para desarrollar sin robot.
MODE = (env("CONGA_MODE", "mock") or "mock").lower()
if MODE == "real":
    from conga_core.robot import RealRobot
    from conga_core.config import RobotConfig
    robot = RealRobot(RobotConfig.from_env())
else:
    robot = MockRobot()

clients: set[WebSocket] = set()
zones = ZoneStore(_data("zones.json"))       # zonas de Clean Assistant (persistentes)
schedules = ScheduleStore(_data("schedules.json"))   # horarios (persistentes)

# orientación del mapa (giro 0-3 x90° + espejo), persistente en view.json
VIEW_PATH = _data("view.json")


def _load_view() -> dict:
    try:
        with open(VIEW_PATH, encoding="utf-8") as f:
            v = json.load(f)
        return {"rot": int(v.get("rot", 0)) % 4, "flip": 1 if v.get("flip") else 0}
    except Exception:
        return {"rot": 0, "flip": 0}


view_settings = _load_view()


def _save_view():
    try:
        with open(VIEW_PATH, "w", encoding="utf-8") as f:
            json.dump(view_settings, f)
    except Exception:
        pass


# caché del último mapa: se muestra al arrancar (aunque el robot esté en la base) y se
# refresca cuando el robot envía uno nuevo (al empezar a limpiar y durante la limpieza).
MAP_CACHE = _data("map_cache.json")


def _save_map():
    m = getattr(robot, "map", None)
    if not m:
        return
    try:
        with open(MAP_CACHE, "w", encoding="utf-8") as f:
            json.dump(m, f)
    except Exception:
        pass


def _load_map():
    try:
        with open(MAP_CACHE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


# modo de enlace persistente: "local" (impersonador) o "cloud" (pasarela a la nube real)
LINK_PATH = _data("link.json")


def _load_link():
    try:
        with open(LINK_PATH, encoding="utf-8") as f:
            return "cloud" if json.load(f).get("mode") == "cloud" else "local"
    except Exception:
        return None


def _save_link(mode: str):
    try:
        with open(LINK_PATH, "w", encoding="utf-8") as f:
            json.dump({"mode": mode}, f)
    except Exception:
        pass


def _map_head_id() -> int:
    return getattr(robot.state, "map_head_id", None) or 1700000000


def _rooms_meta() -> dict:
    m = getattr(robot, "map", None)
    if m and m.get("rooms"):
        # solo habitaciones reales (con nombre); descarta segmentos temporales
        return {r["id"]: {"name": r["name"]} for r in m["rooms"] if r.get("named", True)}
    return {}


# Puente MQTT opcional para Home Assistant (montado sobre el mismo robot). Solo se
# activa si MQTT_HOST está definido; si no, todos sus métodos son no-ops.
mqtt = MqttBridge(robot, schedules, env, _map_head_id, _rooms_meta)


def _send_zone_group(group: str):
    """Reenvía al robot la lista COMPLETA del grupo (set_virwall o set_area)."""
    return robot.command(zones.build_command(group, _map_head_id()))


# ------- acción de la interfaz -> objeto `control` del robot -------
def build(action: str, p: dict):
    if action == "start":        return cmd.start()
    if action == "pause":        return cmd.pause()
    if action == "resume":       return cmd.resume()
    if action == "home":         return cmd.home()
    if action == "cancel_home":  return cmd.cancel_home()
    if action == "locate":       return cmd.locate()
    if action == "clean_rooms":  return cmd.clean_rooms(p["rooms"], p.get("twice", False))
    if action == "clean_all":    return cmd.start()
    if action == "mode":         return cmd.select_mode(p["value"])
    if action == "fan":          return cmd.fan(p["value"])
    if action == "water":        return cmd.water(p["value"])
    if action == "mop":          return cmd.mop(p["value"])
    if action == "twice":        return cmd.twice(p["value"])
    if action == "carpet_turbo": return cmd.carpet_turbo(p["value"])
    if action == "base_type":    return cmd.base_type(p["value"])
    if action == "dust":         return cmd.dust_action()
    if action == "voice":        return cmd.set_voice(p["on"], p["volume"])
    if action == "ota":          return cmd.set_upgrade(p["value"])
    if action == "quiet":        return cmd.set_quiet(p["is_open"], p["begin"], p["end"])
    raise ValueError(f"acción desconocida: {action}")


def _optimistic_state(action: str, p: dict):
    """Refleja en el estado local los ajustes que el robot NO reenvía en report_data,
    para que la interfaz no revierta el control al valor anterior (voz/OTA/no molestar)."""
    s = robot.state
    if action == "voice":
        vol = p.get("volume")
        s.voice = {"voiceMode": 1 if p.get("on") else 0,
                   "volume": int(vol if vol is not None else (s.voice or {}).get("volume", 10))}
    elif action == "ota":
        s.auto_upgrade = 1 if p.get("value") else 0
    elif action == "quiet":
        s.quiet = {"is_open": 1 if p.get("is_open") else 0,
                   "begin_time": int(p.get("begin", 1320)), "end_time": int(p.get("end", 420))}


async def broadcast():
    msg = json.dumps({"type": "state", "state": robot.state.to_dict()})
    for ws in list(clients):
        try:
            await ws.send_text(msg)
        except Exception:
            clients.discard(ws)


async def broadcast_map():
    if not robot.map:
        return
    msg = json.dumps({"type": "map", "map": robot.map})
    for ws in list(clients):
        try:
            await ws.send_text(msg)
        except Exception:
            clients.discard(ws)


async def broadcast_pose():
    pose = getattr(robot, "pose", None)
    if not pose:
        return
    msg = json.dumps({"type": "pose", "pose": pose})
    for ws in list(clients):
        try:
            await ws.send_text(msg)
        except Exception:
            clients.discard(ws)


async def broadcast_zones():
    msg = json.dumps({"type": "zones", "zones": zones.zones})
    for ws in list(clients):
        try:
            await ws.send_text(msg)
        except Exception:
            clients.discard(ws)


async def broadcast_schedules():
    msg = json.dumps({"type": "schedules", "schedules": schedules.plans})
    for ws in list(clients):
        try:
            await ws.send_text(msg)
        except Exception:
            clients.discard(ws)


async def broadcast_view():
    msg = json.dumps({"type": "view", "view": view_settings})
    for ws in list(clients):
        try:
            await ws.send_text(msg)
        except Exception:
            clients.discard(ws)


async def broadcast_orders():
    msg = json.dumps({"type": "orders", "orders": getattr(robot, "orders", [])})
    for ws in list(clients):
        try:
            await ws.send_text(msg)
        except Exception:
            clients.discard(ws)


async def broadcast_link():
    msg = json.dumps({"type": "link", "mode": getattr(robot, "link", "local")})
    for ws in list(clients):
        try:
            await ws.send_text(msg)
        except Exception:
            clients.discard(ws)


async def _loop():
    while True:
        await asyncio.sleep(2)
        robot.tick()
        await broadcast()
        mqtt.publish_state()


@asynccontextmanager
async def lifespan(app: FastAPI):
    loop = asyncio.get_running_loop()

    # push inmediato: cuando el robot cambia, retransmitimos a la web Y a Home Assistant.
    def on_update():
        asyncio.run_coroutine_threadsafe(broadcast(), loop)
        mqtt.publish_state()

    def on_map():
        _save_map()                # persiste el último mapa para verlo tras reiniciar
        asyncio.run_coroutine_threadsafe(broadcast_map(), loop)
        mqtt.publish_discovery()   # el mapa trae las habitaciones -> refresca botones HA

    # muestra el mapa guardado de la vez anterior aunque el robot aún no haya enviado uno
    if MODE == "real" and getattr(robot, "map", None) is None:
        cached = _load_map()
        if cached:
            robot.map = cached
    def on_provision():
        # primer arranque: captura la identidad del robot de la nube y pasa a local
        save_identity(robot.captured)
        robot.cfg.apply_identity(robot.captured)
        print(f"[provision] identidad guardada {robot.captured}; cambiando a modo local")
        robot.set_link("local")
        _save_link("local")
        asyncio.run_coroutine_threadsafe(broadcast_link(), loop)

    # sin identidad configurada -> auto-provisión: arrancar en cloud, capturar y pasar a local
    if MODE == "real" and not robot.cfg.configured:
        robot.link = "cloud"
        print("[provision] primer arranque: capturo la identidad del robot de la nube")
    else:
        saved_link = _load_link()      # respeta el último modo elegido (local/cloud)
        if saved_link:
            robot.link = saved_link

    robot.on_update = on_update
    robot.on_map = on_map
    robot.on_pose = lambda: asyncio.run_coroutine_threadsafe(broadcast_pose(), loop)
    robot.on_orders = lambda: asyncio.run_coroutine_threadsafe(broadcast_orders(), loop)
    robot.on_provision = on_provision
    try:
        robot.start()
    except Exception as e:
        print(f"[robot] no se pudo arrancar el servidor ({MODE}): {e}")
    mqtt.start()
    print(f"[Clean Assistant] modo={MODE}")
    task = asyncio.create_task(_loop())
    yield
    task.cancel()
    mqtt.stop()


app = FastAPI(title="Clean Assistant", version="0.10.0", lifespan=lifespan)


@app.get("/api/state")
def get_state():
    return robot.state.to_dict()


@app.get("/api/map")
def get_map():
    return robot.map or cmap.sample_map()


@app.post("/api/command")
async def post_command(payload: dict):
    action = payload.get("action")
    try:
        control = build(action, payload)
    except (KeyError, ValueError) as e:
        return {"ok": False, "error": str(e)}
    result = robot.command(control)
    _optimistic_state(action, payload)
    mqtt.note_web_command(action, payload)
    await broadcast()
    return {"ok": True, "sent": control, "result": result}


@app.get("/api/link")
def get_link():
    return {"mode": getattr(robot, "link", "local")}


@app.post("/api/link/set")
async def set_link(payload: dict):
    mode = "cloud" if str(payload.get("mode")).lower() == "cloud" else "local"
    robot.set_link(mode)
    _save_link(mode)
    await broadcast_link()
    return {"ok": True, "mode": mode}


@app.get("/api/view")
def get_view():
    return view_settings


@app.post("/api/view/set")
async def set_view(payload: dict):
    if "rot" in payload:
        view_settings["rot"] = int(payload["rot"]) % 4
    if "flip" in payload:
        view_settings["flip"] = 1 if payload["flip"] else 0
    _save_view()
    await broadcast_view()
    return {"ok": True, "view": view_settings}


@app.get("/api/zones")
def get_zones():
    return {"zones": zones.zones}


@app.post("/api/zones/add")
async def zone_add(payload: dict):
    try:
        z = zones.add(payload["kind"], payload["points"], payload.get("name", ""))
    except (KeyError, ValueError) as e:
        return {"ok": False, "error": str(e)}
    _send_zone_group(zones.group_of(z["kind"]))
    await broadcast_zones()
    return {"ok": True, "zone": z, "zones": zones.zones}


@app.post("/api/zones/delete")
async def zone_delete(payload: dict):
    zid = payload.get("id")
    z = next((x for x in zones.zones if x["id"] == int(zid)), None)
    zones.delete(zid)
    if z:
        _send_zone_group(zones.group_of(z["kind"]))
    await broadcast_zones()
    return {"ok": True, "zones": zones.zones}


@app.post("/api/zones/rename")
async def zone_rename(payload: dict):
    z = zones.rename(payload["id"], payload.get("name", ""))
    if z:
        _send_zone_group(zones.group_of(z["kind"]))   # el nombre viaja en el comando
    await broadcast_zones()
    return {"ok": True, "zones": zones.zones}


@app.post("/api/room/update")
async def room_update(payload: dict):
    """Cambia nombre y/o tipo de suelo de una habitación (setPlanData6090, lista completa)."""
    m = getattr(robot, "map", None)
    if not m or not m.get("rooms"):
        return {"ok": False, "error": "sin mapa"}
    rid = int(payload["room"])
    new_name = payload.get("name")
    new_material = payload.get("material")
    new_type = payload.get("type")
    rooms = []
    for r in m["rooms"]:
        if not r.get("named", True):
            continue
        name, material = r["name"], (r.get("material") or 1)
        rtype = r.get("type") or 0
        if r["id"] == rid:
            if new_name:
                name = new_name
            if new_material is not None:
                material = new_material
            if new_type is not None:
                rtype = int(new_type)
        rooms.append({"room_id": r["id"], "room_name": name,
                      "room_type": rtype, "material": material})
    robot.command(cmd.set_plan_data(_map_head_id(), rooms))
    # reflejo optimista en el mapa cacheado
    for r in m["rooms"]:
        if r["id"] == rid:
            if new_name:
                r["name"] = new_name
            if new_material is not None:
                r["material"] = cmd._lvl(cmd.MATERIALS, new_material)
            if new_type is not None:
                r["type"] = int(new_type)
    _save_map()
    return {"ok": True}


@app.get("/api/schedules")
def get_schedules():
    return {"schedules": schedules.plans}


@app.get("/api/schedules/suggested")
def get_suggested_schedules():
    """Planes sugeridos según el mapa (dormitorios / baños / limpieza profunda).
    Se omiten los que ya existen (por nombre)."""
    rooms = (getattr(robot, "map", None) or {}).get("rooms", [])
    existing = {(p.get("name") or "").lower() for p in schedules.plans}
    sug = [s for s in suggested_plans(rooms) if s["name"].lower() not in existing]
    return {"suggested": sug}


@app.post("/api/schedules/save")
async def schedule_save(payload: dict):
    plan = payload.get("plan") or payload
    p = schedules.upsert(plan)
    robot.command(schedules.order_command(p, _map_head_id(), _rooms_meta()))
    await broadcast_schedules()
    mqtt.publish_discovery()          # añade/refresca el switch del horario en HA
    return {"ok": True, "plan": p, "schedules": schedules.plans}


@app.post("/api/schedules/toggle")
async def schedule_toggle(payload: dict):
    p = schedules.toggle(payload["id"], payload.get("enable", True))
    if p:
        robot.command(schedules.order_command(p, _map_head_id(), _rooms_meta()))
        mqtt.reflect_schedule(p)
    await broadcast_schedules()
    return {"ok": True, "schedules": schedules.plans}


@app.post("/api/schedules/delete")
async def schedule_delete(payload: dict):
    p = schedules.delete(payload["id"])
    if p:
        robot.command(schedules.delete_command(p))
        mqtt.forget_schedule(p["id"])   # retira el switch del horario en HA
    await broadcast_schedules()
    return {"ok": True, "schedules": schedules.plans}


# ---- horarios REALES guardados en el robot (getOrder6090), incluidos los de la app Cecotec ----
@app.get("/api/robot/orders")
def get_robot_orders():
    return {"orders": getattr(robot, "orders", [])}


@app.post("/api/robot/orders/refresh")
async def refresh_robot_orders():
    robot.query_orders()             # respuesta asíncrona -> llega por WS (broadcast_orders)
    return {"ok": True}


@app.post("/api/robot/orders/delete")
async def delete_robot_order(payload: dict):
    robot.command(cmd.delete_order(payload["orderid"]))
    robot.query_orders()             # re-consulta para refrescar la lista
    return {"ok": True}


# ---- zonas guardadas en el robot (paredes virtuales del mapa): editar / borrar ----
def _robot_virwall_zones() -> list:
    m = getattr(robot, "map", None) or {}
    return [z for z in m.get("stored_zones", []) if z.get("kind") in ("nogo", "nomop")]


def _push_robot_zones(zlist):
    """Reescribe TODAS las paredes virtuales del robot (set_virwall reemplaza la lista)."""
    zones = [{"points": [tuple(p) for p in z.get("points_m", [])],
              "type": z.get("type") or cmd.VIRWALL_NOGO,
              "name": z.get("name", ""), "id": i + 1}
             for i, z in enumerate(zlist) if z.get("points_m")]
    robot.command(cmd.set_virwall(zones, _map_head_id()))


async def _reflect_robot_zones(zlist):
    """Actualiza el mapa cacheado (stored_zones solo virwall) y avisa a la web."""
    m = getattr(robot, "map", None)
    if m is not None:
        others = [z for z in m.get("stored_zones", []) if z.get("kind") not in ("nogo", "nomop")]
        m["stored_zones"] = zlist + others
        _save_map()
        await broadcast_map()


@app.post("/api/robot/zones/delete")
async def robot_zone_delete(payload: dict):
    idx = int(payload.get("index", -1))
    zs = _robot_virwall_zones()
    if not (0 <= idx < len(zs)):
        return {"ok": False, "error": "índice fuera de rango"}
    remaining = [z for i, z in enumerate(zs) if i != idx]
    _push_robot_zones(remaining)
    await _reflect_robot_zones(remaining)
    return {"ok": True}


@app.post("/api/robot/zones/update")
async def robot_zone_update(payload: dict):
    idx = int(payload.get("index", -1))
    zs = _robot_virwall_zones()
    if not (0 <= idx < len(zs)):
        return {"ok": False, "error": "índice fuera de rango"}
    if payload.get("name") is not None:
        zs[idx]["name"] = str(payload["name"])
    if payload.get("points_m"):
        zs[idx]["points_m"] = [list(p) for p in payload["points_m"]]
    _push_robot_zones(zs)
    await _reflect_robot_zones(zs)
    return {"ok": True}


# ---- reset de consumibles (set_consumables): pone a 0 las horas de uso de una pieza ----
@app.post("/api/consumable/reset")
async def consumable_reset(payload: dict):
    key = payload.get("key")
    if key not in cmd.CONSUMABLE_RESET:
        return {"ok": False, "error": "consumible desconocido"}
    robot.command(cmd.reset_consumable(key))
    # reflejo optimista (horas de uso -> 0) y re-consulta para confirmar
    try:
        cons = dict(getattr(robot.state, "consumables", None) or {})
        cons[key] = 0
        robot.state.consumables = cons
    except Exception:
        pass
    try:
        robot.command(cmd.query("get_consumables", getattr(robot.cfg, "userid", 0)))
    except Exception:
        pass
    await broadcast()
    mqtt.publish_state()
    return {"ok": True}


@app.websocket("/ws")
async def websocket(ws: WebSocket):
    await ws.accept()
    clients.add(ws)
    await ws.send_text(json.dumps({"type": "state", "state": robot.state.to_dict()}))
    await ws.send_text(json.dumps({"type": "view", "view": view_settings}))
    await ws.send_text(json.dumps({"type": "link", "mode": getattr(robot, "link", "local")}))
    if robot.map:
        await ws.send_text(json.dumps({"type": "map", "map": robot.map}))
    if zones.zones:
        await ws.send_text(json.dumps({"type": "zones", "zones": zones.zones}))
    if schedules.plans:
        await ws.send_text(json.dumps({"type": "schedules", "schedules": schedules.plans}))
    if getattr(robot, "orders", None):
        await ws.send_text(json.dumps({"type": "orders", "orders": robot.orders}))
    try:
        while True:
            await ws.receive_text()   # el cliente no envía; solo mantenemos abierto
    except WebSocketDisconnect:
        clients.discard(ws)
    except Exception:
        clients.discard(ws)


# El frontend (estático) se sirve en la raíz. Debe ir DESPUÉS de las rutas /api y /ws.
app.mount("/", StaticFiles(directory=str(STATIC), html=True), name="frontend")
