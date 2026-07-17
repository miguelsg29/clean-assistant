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
from conga_core.config import load_env
from backend.mock import MockRobot
from backend.zones import ZoneStore
from backend.schedules import ScheduleStore
from backend.mqtt_bridge import MqttBridge

STATIC = Path(__file__).parent / "static"
env = load_env()

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
zones = ZoneStore()               # zonas de Clean Assistant (persiste en zones.json)
schedules = ScheduleStore()       # horarios (persiste en schedules.json)


def _map_head_id() -> int:
    return getattr(robot.state, "map_head_id", None) or 1700000000


def _rooms_meta() -> dict:
    m = getattr(robot, "map", None)
    if m and m.get("rooms"):
        return {r["id"]: {"name": r["name"]} for r in m["rooms"]}
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
        asyncio.run_coroutine_threadsafe(broadcast_map(), loop)
        mqtt.publish_discovery()   # el mapa trae las habitaciones -> refresca botones HA

    robot.on_update = on_update
    robot.on_map = on_map
    robot.on_pose = lambda: asyncio.run_coroutine_threadsafe(broadcast_pose(), loop)
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


app = FastAPI(title="Clean Assistant", version="0.1.0", lifespan=lifespan)


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
    mqtt.note_web_command(action, payload)
    await broadcast()
    return {"ok": True, "sent": control, "result": result}


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


@app.get("/api/schedules")
def get_schedules():
    return {"schedules": schedules.plans}


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


@app.websocket("/ws")
async def websocket(ws: WebSocket):
    await ws.accept()
    clients.add(ws)
    await ws.send_text(json.dumps({"type": "state", "state": robot.state.to_dict()}))
    if robot.map:
        await ws.send_text(json.dumps({"type": "map", "map": robot.map}))
    if zones.zones:
        await ws.send_text(json.dumps({"type": "zones", "zones": zones.zones}))
    if schedules.plans:
        await ws.send_text(json.dumps({"type": "schedules", "schedules": schedules.plans}))
    try:
        while True:
            await ws.receive_text()   # el cliente no envía; solo mantenemos abierto
    except WebSocketDisconnect:
        clients.discard(ws)
    except Exception:
        clients.discard(ws)


# El frontend (estático) se sirve en la raíz. Debe ir DESPUÉS de las rutas /api y /ws.
app.mount("/", StaticFiles(directory=str(STATIC), html=True), name="frontend")
