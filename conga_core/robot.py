"""RealRobot — servidor local que suplanta la nube de Cecotec para el Conga 8090.

Termina el TLS 1.2, hace el handshake WebSocket, responde login/heart-beat, recibe
report_data (→ estado) y envía comandos. Misma interfaz que MockRobot
(`.state`, `command(control)`, `tick()`), así el backend no distingue uno de otro.

Portado del puente MQTT probado (conga_mqtt_bridge.py), encapsulado en una clase.
"""
from __future__ import annotations
import base64
import hashlib
import json
import os
import socket
import ssl
import subprocess
import threading
import time

from . import ws
from . import commands as cmd
from .config import WS_MAGIC, RobotConfig
from .state import RobotState


def _now_ms() -> str:
    return str(int(time.time() * 1000))


class RealRobot:
    def __init__(self, cfg: RobotConfig, logger=print):
        self.cfg = cfg
        self.state = RobotState()
        self.on_update = None          # callback opcional (para push inmediato)
        self.log = logger
        self._sock = None
        self._lock = threading.Lock()
        self._diag = {"quiet": 0, "info": 0}

    # ---------------- interfaz común (como MockRobot) ----------------
    def start(self):
        self._ensure_certs()
        threading.Thread(target=self._serve, daemon=True).start()

    def command(self, control: dict) -> dict:
        """Envía un objeto `control` al robot (envuelto en to_bind)."""
        with self._lock:
            sock = self._sock
        if not sock:
            return {"ok": False, "error": "robot no conectado"}
        msg = {"tag": "sweeper-transmit/to_bind", "content": json.dumps(control)}
        try:
            ws.send(sock, json.dumps(msg))
            self.log(f"  --> robot: {control.get('control')}")
            return {"result": 0}
        except Exception as e:
            self.log(f"  [!] error enviando al robot: {e}")
            return {"ok": False, "error": str(e)}

    def tick(self) -> RobotState:
        return self.state    # el estado real llega por report_data, no por tick

    # ---------------- servidor ----------------
    def _ensure_certs(self):
        cp, kp = self.cfg.cert_path, self.cfg.key_path
        if os.path.exists(cp) and os.path.exists(kp):
            return
        self.log(f"[cert] generando certificados autofirmados en {cp}/{kp}...")
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048",
                        "-keyout", kp, "-out", cp, "-days", "3650", "-nodes",
                        "-subj", "/CN=tcp-cecotec.3irobotix.net"],
                       check=True, capture_output=True)

    def _serve(self):
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(certfile=self.cfg.cert_path, keyfile=self.cfg.key_path)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        try:
            ctx.set_ciphers("ALL:@SECLEVEL=0")
        except Exception:
            pass
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("0.0.0.0", self.cfg.listen_port))
        s.listen(5)
        self.log(f"[robot] servidor escuchando en 0.0.0.0:{self.cfg.listen_port}")
        while True:
            raw, addr = s.accept()
            self.log(f"[robot] conexión desde {addr[0]}")
            try:
                tls = ctx.wrap_socket(raw, server_side=True)
            except Exception as e:
                self.log(f"  [robot] TLS error: {e}")
                raw.close()
                continue
            threading.Thread(target=self._handle_conn, args=(tls,), daemon=True).start()

    def _handle_conn(self, tls):
        try:
            if not self._handshake(tls):
                tls.close()
                return
            self.log("  [robot] conectado")
            with self._lock:
                self._sock = tls
            self._diag = {"quiet": 0, "info": 0}
            while True:
                opcode, payload = ws.read_frame(tls)
                if opcode is None or opcode == 0x8:
                    self.log("  [robot] desconectado")
                    break
                if opcode == 0x9:                       # ping -> pong
                    ws.send(tls, payload or b"", opcode=0xA)
                    continue
                if payload:
                    self._handle_msg(tls, payload)
        except Exception as e:
            self.log(f"  [robot] error: {e}")
        finally:
            with self._lock:
                if self._sock is tls:
                    self._sock = None
            self.state.online = False
            self._notify()
            try:
                tls.close()
            except Exception:
                pass

    def _handshake(self, tls) -> bool:
        req = ws.recv_http_headers(tls)
        key = None
        for l in req.split(b"\r\n"):
            if l.lower().startswith(b"sec-websocket-key:"):
                key = l.split(b":", 1)[1].strip().decode()
        if not key:
            return False
        accept = base64.b64encode(
            hashlib.sha1((key + WS_MAGIC).encode()).digest()).decode()
        tls.sendall(("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n"
                     "Connection: Upgrade\r\n"
                     f"Sec-WebSocket-Accept: {accept}\r\n\r\n").encode())
        return True

    def _notify(self):
        if self.on_update:
            try:
                self.on_update()
            except Exception:
                pass

    def _query_startup(self):
        """Pide no molestar / consumibles / OTA / voz (con reintentos)."""
        uid = self.cfg.userid
        if self.state.quiet is None and self._diag["quiet"] < 6:
            self._diag["quiet"] += 1
            self.command(cmd.query("get_quiet", uid))
        if self._diag["info"] < 4 and (self.state.consumables is None
                                       or self.state.auto_upgrade is None):
            self._diag["info"] += 1
            self.command(cmd.query("get_consumables", uid))
            self.command(cmd.query("get_upgrade_config", uid))
            self.command(cmd.query("get_voice", uid))

    def _handle_msg(self, tls, payload: bytes):
        if payload.strip() == b"libuwsc":
            ws.send(tls, b"libuwsc")
            return
        try:
            msg = json.loads(payload.decode("utf-8"))
        except Exception:
            return
        service = msg.get("service", "")
        trace = str(msg.get("traceId", ""))
        c = self.cfg

        if service.endswith("auth/login"):
            self.log("  [robot] LOGIN")
            resp = {"code": 0, "traceId": trace,
                    "service": "sweeper-robot-center/auth/login",
                    "result": {"data": {
                        "AUTH": c.jwt, "FACTORY_ID": c.factory_id,
                        "USERNAME": c.sn, "CONNECTION_TYPE": "sweeper",
                        "PROJECT_TYPE": c.project_type, "ROBOT_TYPE": "sweeper",
                        "SN": c.sn, "MAC": c.mac,
                        "BIND_LIST": f"[\"{c.userid}\"]"},
                        "clientType": "ROBOT", "id": str(c.did), "resetCode": 0}}
            ws.send(tls, json.dumps(resp))
            self.state.online = True
            self._notify()
            return

        if service == "heart-beat":
            ws.send(tls, json.dumps({"code": 0, "traceId": trace,
                                     "service": "heart-beat", "result": _now_ms()}))
            return

        if service.endswith("device/report_data"):
            try:
                data = json.loads(msg.get("content", "{}")).get("data", {})
                prev = self.state.state
                self.state.update_from_report(data)
                if self.state.state != prev:
                    self.log(f"  [robot] estado -> {self.state.state} "
                             f"(bat {self.state.battery})")
                self._query_startup()
                self._notify()
            except Exception:
                pass
            ws.send(tls, json.dumps({"code": 0, "traceId": trace,
                    "service": "sweeper-robot-center/device/report_data",
                    "result": True}))
            return

        if service.endswith("transmit/to_bind"):
            try:
                self._parse_ack(json.loads(msg.get("content", "{}")).get("data", {}))
            except Exception:
                pass
            ws.send(tls, json.dumps({"code": 0, "traceId": trace,
                    "service": "sweeper-transmit/transmit/to_bind", "result": True}))
            return

        # cualquier otro servicio: acuse genérico
        ws.send(tls, json.dumps({"code": 0, "traceId": trace,
                "service": service.split("?")[0], "result": True}))

    def _parse_ack(self, data: dict):
        """Respuestas de get_* que traen datos de estado."""
        ctrl = data.get("control")
        changed = False
        if ctrl == "get_quiet":
            q = (data.get("quiet_list") or [{}])[0]
            if q:
                self.state.quiet = {"is_open": q.get("is_open", 0),
                                    "begin_time": q.get("begin_time", 1320),
                                    "end_time": q.get("end_time", 420)}
                changed = True
        elif ctrl == "get_consumables":
            self.state.consumables = {k: data.get(k) for k in
                                      ("main_brush", "side_brush", "filter", "dishcloth")}
            changed = True
        elif ctrl == "get_upgrade_config":
            self.state.auto_upgrade = 1 if data.get("auto_upgrade") else 0
            changed = True
        elif ctrl == "get_voice":
            self.state.voice = {"voiceMode": data.get("voiceMode", 1),
                                "volume": data.get("volume", 10)}
            changed = True
        if changed:
            self._notify()
