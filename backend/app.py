"""Clean Assistant — backend FastAPI.

Expone el robot (real o simulado) como una API REST + WebSocket, y sirve el
frontend. En v0.1 usa el robot simulado (`MockRobot`); el robot real (servidor
TLS+WS que suplanta la nube) se enchufará aquí mismo con la misma interfaz.

Arrancar:  uvicorn backend.app:app --reload
"""
from __future__ import annotations
import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from conga_core import commands as cmd
from conga_core import map as cmap
from backend.mock import MockRobot

STATIC = Path(__file__).parent / "static"
robot = MockRobot()
clients: set[WebSocket] = set()


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


async def _loop():
    while True:
        await asyncio.sleep(2)
        robot.tick()
        await broadcast()


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_loop())
    yield
    task.cancel()


app = FastAPI(title="Clean Assistant", version="0.1.0", lifespan=lifespan)


@app.get("/api/state")
def get_state():
    return robot.state.to_dict()


@app.get("/api/map")
def get_map():
    return cmap.sample_map()


@app.post("/api/command")
async def post_command(payload: dict):
    action = payload.get("action")
    try:
        control = build(action, payload)
    except (KeyError, ValueError) as e:
        return {"ok": False, "error": str(e)}
    result = robot.command(control)
    await broadcast()
    return {"ok": True, "sent": control, "result": result}


@app.websocket("/ws")
async def websocket(ws: WebSocket):
    await ws.accept()
    clients.add(ws)
    await ws.send_text(json.dumps({"type": "state", "state": robot.state.to_dict()}))
    try:
        while True:
            await ws.receive_text()   # el cliente no envía; solo mantenemos abierto
    except WebSocketDisconnect:
        clients.discard(ws)
    except Exception:
        clients.discard(ws)


# El frontend (estático) se sirve en la raíz. Debe ir DESPUÉS de las rutas /api y /ws.
app.mount("/", StaticFiles(directory=str(STATIC), html=True), name="frontend")
