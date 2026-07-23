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
from . import map as cmap
from .config import WS_MAGIC, RobotConfig
from .state import RobotState


def _now_ms() -> str:
    return str(int(time.time() * 1000))


class RealRobot:
    def __init__(self, cfg: RobotConfig, logger=print):
        self.cfg = cfg
        self.state = RobotState()
        self.map = None                # último mapa decodificado (dict del frontend)
        self.map_empty = False         # el robot no tiene mapa (se han borrado todos)
        self.pose = None               # última pose del robot {x, y, angle} (celda recortada)
        self.orders = []               # horarios REALES guardados en el robot (getOrder6090)
        self.on_update = None          # callback opcional (estado -> push)
        self.on_map = None             # callback opcional (mapa -> push)
        self.on_pose = None            # callback opcional (solo pose -> push ligero)
        self.on_orders = None          # callback opcional (horarios del robot -> push)
        self.captured = {}             # identidad capturada de la nube (auto-provisión)
        self.on_provision = None       # callback cuando se captura la identidad completa
        # si ya hay identidad, NO auto-provisionar (evita que el modo cloud manual vuelva
        # a local): la auto-provisión es solo para el primer arranque sin configurar.
        self._provisioned = cfg.configured
        self.log = logger
        self.link = getattr(cfg, "link_mode", "local")   # "local" | "cloud" (pasarela a la nube)
        self._sock = None
        self._cloud = None
        self._lock = threading.Lock()
        self._wlock = threading.Lock()   # serializa escrituras al socket del robot
        self._diag = {"quiet": 0, "info": 0}
        self._last_cells = None        # rejilla del último mapa emitido (para detectar cambios)
        self._last_zones = None        # firma de las zonas del último mapa (paredes virtuales)
        self._got_map = False          # ya llegó un mapa real del robot en esta sesión

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
            with self._wlock:
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
            self._diag = {"quiet": 0, "info": 0}
            self._got_map = False
            self._last_zones = None
            if self.link == "cloud":
                cloud = None
                try:
                    cloud = self._connect_cloud()
                except Exception as e:
                    self.log(f"  [cloud] nube no accesible ({e}); sigo en LOCAL esta sesión")
                if cloud:
                    self._relay_cloud(tls, cloud)   # bloquea hasta cerrar; la app oficial funciona
                    return
                # si la nube falla, cae al impersonador local (abajo)
            with self._lock:
                self._sock = tls
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

    # ---------------- modo cloud (pasarela robot <-> nube real) ----------------
    _NOISE = ("heart-beat", "report_data", "info_report", "get_notice_config",
              "get_pets", "stuff/config", "status")

    def _connect_cloud(self):
        raw = socket.create_connection((self.cfg.cloud_ip, self.cfg.cloud_port), timeout=8)
        raw.settimeout(None)
        cctx = ssl.create_default_context()
        cctx.check_hostname = False
        cctx.verify_mode = ssl.CERT_NONE
        try:
            cctx.set_ciphers("ALL:@SECLEVEL=0")
        except Exception:
            pass
        tls = cctx.wrap_socket(raw, server_hostname=self.cfg.cloud_host)
        key = base64.b64encode(os.urandom(16)).decode()
        tls.sendall((f"GET / HTTP/1.1\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                     f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n"
                     f"Host: {self.cfg.cloud_host}:{self.cfg.cloud_port}\r\n\r\n").encode())
        ws.recv_http_headers(tls)
        self.log(f"  [cloud] conectado a la nube real {self.cfg.cloud_ip}")
        return tls

    def _relay_cloud(self, robot_tls, cloud):
        self.log("  [cloud] pasarela robot<->nube ACTIVA (la app oficial funciona)")
        with self._lock:
            self._sock = robot_tls
            self._cloud = cloud
        self.state.online = True
        self._notify()

        def cloud_to_robot():
            try:
                while True:
                    op, pl = ws.read_frame(cloud)
                    if op is None or op == 0x8:
                        break
                    with self._wlock:
                        ws.send(robot_tls, pl or b"", opcode=(0xA if op == 0x9 else (op or 0x1)))
                    if pl and op != 0x9:
                        self._observe("nube->robot", pl)
            except Exception:
                pass
            finally:
                for s in (robot_tls, cloud):
                    try: s.close()
                    except Exception: pass

        threading.Thread(target=cloud_to_robot, daemon=True).start()
        try:
            while True:
                op, pl = ws.read_frame(robot_tls)
                if op is None or op == 0x8:
                    break
                ws.send(cloud, pl or b"", opcode=(0xA if op == 0x9 else (op or 0x1)), mask=True)
                if pl and op != 0x9:
                    self._observe("robot->nube", pl)
        except Exception as e:
            self.log(f"  [cloud] fin de pasarela: {e}")
        finally:
            with self._lock:
                if self._sock is robot_tls:
                    self._sock = None
                self._cloud = None
            self.state.online = False
            self._notify()
            for s in (robot_tls, cloud):
                try: s.close()
                except Exception: pass

    def _set_no_map(self):
        """El robot ha devuelto un mapa vacío: no tiene mapa (se han borrado todos).
        Limpia la vista para no seguir mostrando el mapa anterior."""
        if self.map is None and self.map_empty:
            return
        self.map = None
        self.pose = None
        self.map_empty = True
        self._got_map = True
        self._last_cells = None
        self._last_zones = None
        self.log("  [robot] sin mapa (se han borrado todos)")
        self._notify_map()

    def _observe(self, direction, payload):
        """En modo cloud: alimenta estado/mapa desde el tráfico y registra los
        comandos de la app (para depurar funciones aún no integradas)."""
        if b"\x78\x9c" in payload and (b"syn_no_cache" in payload or b"sweeper-map" in payload):
            try:
                m = cmap.decode_map(payload)
                self.map = m
                self.map_empty = False
                self.pose = m.get("robot")
                zsig = json.dumps(m.get("stored_zones", []), sort_keys=True)
                if m.get("cells_b64") != self._last_cells or zsig != self._last_zones:
                    self._last_cells = m["cells_b64"]
                    self._last_zones = zsig
                    self._notify_map()
                elif self.pose:
                    self._notify_pose()
            except ValueError as e:
                if "vac" in str(e).lower():         # robot sin mapa: limpia la vista
                    self._set_no_map()
            except Exception:
                pass
            return
        try:
            msg = json.loads(payload.decode("utf-8"))
        except Exception:
            return
        service = str(msg.get("service") or msg.get("tag") or "")
        if not self._provisioned and service.endswith("auth/login"):
            self._capture_login(msg.get("result") or {})   # identidad del robot (nube->robot)
        content = msg.get("content")
        try:
            parsed = json.loads(content) if content else {}
        except Exception:
            parsed = {}
        if not isinstance(parsed, dict):
            return
        if service.endswith("device/report_data"):
            d = parsed.get("data", {})
            if isinstance(d, dict):
                try:
                    self.state.update_from_report(d)
                    self._notify()
                except Exception:
                    pass
            return
        # acuse del robot ({data:{control,...}}) o comando de la app ({control,...})
        d = parsed.get("data") if isinstance(parsed.get("data"), dict) else parsed
        ctrl = d.get("control") if isinstance(d, dict) else None
        if not self._provisioned and isinstance(d, dict):
            self._capture({"did": d.get("did"), "userid": d.get("userid")})
        if ctrl in ("get_quiet", "get_consumables", "get_upgrade_config",
                    "get_voice", "getOrder6090"):
            try:
                self._parse_ack(d)   # aprovecha para leer no molestar/consumibles/voz/horarios
            except Exception:
                pass
        if ctrl and ctrl not in self._NOISE:
            extras = {k: v for k, v in d.items() if k != "control"}
            self.log(f"  [cloud][{direction}] {ctrl} "
                     f"{json.dumps(extras, ensure_ascii=False)[:220]}")

    def _capture_login(self, result):
        """Extrae la identidad del robot de la respuesta de login de la nube."""
        if not isinstance(result, dict):
            return
        data = result.get("data") or {}
        upd = {"did": result.get("id"),
               "sn": data.get("SN") or data.get("USERNAME"),
               "mac": data.get("MAC"),
               "factory_id": data.get("FACTORY_ID"),
               "project_type": data.get("PROJECT_TYPE")}
        bl = data.get("BIND_LIST")
        if bl:
            try:
                upd["userid"] = json.loads(bl)[0]
            except Exception:
                pass
        self._capture(upd)

    def _capture(self, upd):
        """Acumula campos de identidad; cuando están los esenciales, provisiona."""
        changed = False
        for k, v in (upd or {}).items():
            if v in (None, "", 0, "0"):
                continue
            if not self.captured.get(k):
                self.captured[k] = v
                changed = True
        if changed:
            self.log(f"  [provision] identidad capturada: {self.captured}")
        if (not self._provisioned and self.captured.get("did")
                and self.captured.get("userid") and self.on_provision):
            self._provisioned = True
            try:
                self.on_provision()
            except Exception:
                pass

    def set_link(self, mode):
        """Cambia el modo de enlace ('local'/'cloud'); reinicia la conexión del robot."""
        mode = "cloud" if str(mode).lower() == "cloud" else "local"
        if mode == self.link:
            return
        self.link = mode
        self.log(f"  [link] modo -> {mode}; reconectando el robot...")
        with self._lock:
            s, c = self._sock, self._cloud
        for x in (s, c):
            try:
                if x:
                    x.close()   # fuerza al robot a reconectar en el nuevo modo
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

    def _notify_map(self):
        if self.on_map:
            try:
                self.on_map()
            except Exception:
                pass

    def _notify_pose(self):
        if self.on_pose:
            try:
                self.on_pose()
            except Exception:
                pass

    def _notify_orders(self):
        if self.on_orders:
            try:
                self.on_orders()
            except Exception:
                pass

    def query_orders(self):
        """Pide al robot la lista REAL de horarios guardados (getOrder6090)."""
        self.command(cmd.query("getOrder6090", self.cfg.userid))

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
        # el robot solo responde a getOrder6090 en reposo -> consultarlo al estar en base
        if (not self.orders and self._diag.get("orders", 0) < 4
                and self.state.state in ("docked", "idle")):
            self._diag["orders"] = self._diag.get("orders", 0) + 1
            self.command(cmd.query("getOrder6090", uid))
        # pedir el mapa guardado al arrancar (la app hace lock_device + get_map + getMapAll)
        # para no depender de que el robot lo empuje al limpiar. map_head_id llega en report_data.
        # lock_device = "tomar el control": sin él el robot no envía el mapa estando en base.
        # Se pide aunque map_head_id sea 0/None: si el robot NO tiene mapa (borrados todos),
        # map_head_id es 0 y aun así hay que pedirlo para recibir el "mapa vacío" y saberlo.
        if not self._got_map and self._diag.get("map", 0) < 8:
            self._diag["map"] = self._diag.get("map", 0) + 1
            self.command(cmd.lock_device(uid))
            self.command(cmd.get_map())
            if self.state.map_head_id:
                self.command(cmd.get_map_all(self.state.map_head_id))

    def _handle_msg(self, tls, payload: bytes):
        if payload.strip() == b"libuwsc":
            ws.send(tls, b"libuwsc")
            return
        # Frame de mapa (binario, no JSON): syn_no_cache con zlib comprimido.
        if b"\x78\x9c" in payload and (b"syn_no_cache" in payload
                                       or b"sweeper-map" in payload):
            try:
                m = cmap.decode_map(payload)
                self.map = m
                self.map_empty = False
                self._got_map = True
                self.pose = m.get("robot")
                cells = m.get("cells_b64")
                zsig = json.dumps(m.get("stored_zones", []), sort_keys=True)
                if cells != self._last_cells or zsig != self._last_zones:
                    # cambió la rejilla o las zonas guardadas: mapa completo
                    self._last_cells = cells
                    self._last_zones = zsig
                    self.log(f"  [robot] mapa: {m['name']} "
                             f"{m['bbox'][2]}x{m['bbox'][3]} ({len(m['rooms'])} hab.)")
                    self._notify_map()
                elif self.pose:
                    # misma rejilla y zonas, solo se movió el robot: push ligero de pose
                    self._notify_pose()
            except ValueError as e:
                if "vac" in str(e).lower():         # robot sin mapa (borrados todos): limpia
                    self._set_no_map()
                else:
                    self.log(f"  [!] mapa no decodificado: {e}")
            except Exception as e:
                self.log(f"  [!] mapa no decodificado: {e}")
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
                    wm = data.get("workMode")
                    self.log(f"  [robot] estado -> {self.state.state} "
                             f"(workMode={wm} charge={data.get('chargeStatus')} "
                             f"bat {self.state.battery})")
                    # workMode activo no reconocido (sale 'inactivo'): candidato a mapeando/etc.
                    if self.state.state == "idle" and wm not in (0, None):
                        self.log(f"  [robot] AVISO: workMode={wm} no reconocido -> 'inactivo'. "
                                 f"Si estás mapeando o limpiando, apúntalo para mapearlo.")
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
        elif ctrl == "getOrder6090":
            self.orders = data.get("orders", []) or []
            self.log(f"  [robot] horarios guardados en el robot: {len(self.orders)}")
            self._notify_orders()
        elif ctrl == "get_voice":
            self.state.voice = {"voiceMode": data.get("voiceMode", 1),
                                "volume": data.get("volume", 10)}
            changed = True
        if changed:
            self._notify()
