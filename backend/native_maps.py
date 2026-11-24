"""Private native robot snapshots. Decoded map history is deliberately independent."""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import threading
from urllib.parse import urlsplit
import uuid

from fastapi import HTTPException, Request
from backend.native_map_helpers import atomic_json, valid_map
from backend.native_map_io import NativeMapError, NativeMapIO


class NativeMaps:
    MAX_BACKUPS = 20
    MAX_INDEX_BYTES = 16 * 1024

    def __init__(self, data_dir, robot_getter, legacy_getter, config_getter, io_factory=None):
        self.root = Path(data_dir) / "native-map-backups"
        self.robot_getter = robot_getter
        self.legacy_getter = legacy_getter
        self.config_getter = config_getter
        self.io_factory = io_factory
        self.lock = threading.Lock()
        self.pending_path = Path(data_dir) / "native-map-restore.json"
        self.index_path = self.root / "index.json"
        self._ssh_identity = None

    def _identity_context(self):
        robot = self.robot_getter()
        config = Path(self.config_getter()).resolve(strict=True)
        stat = config.stat()
        return (id(robot), getattr(robot, "native_session_id", None),
                getattr(robot, "native_peer_ip", None), str(config),
                stat.st_mtime_ns, stat.st_size, stat.st_ino)

    @staticmethod
    def _geometry(data):
        if not valid_map(data):
            raise ValueError("Invalid live map geometry")
        ids = {r.get("id") for r in data.get("rooms", []) if type(r.get("id")) is int}
        table = bytes(v - 50 if v - 50 in ids and v not in ids and v != 255 else v for v in range(256))
        cells = base64.b64decode(data["cells_b64"], validate=True).translate(table)
        geometry = json.dumps({"bbox": data["bbox"], "world": data.get("world")}, sort_keys=True).encode()
        return hashlib.sha256(geometry + b"\0" + cells).hexdigest()

    def verification(self):
        try:
            pending = json.loads(self.pending_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(pending, dict) or any(k not in pending for k in ("backup_id", "map_id", "identity", "geometry")):
            return None
        result = {k: pending[k] for k in ("backup_id", "map_id")}
        result.update(status="pending_reload", message="Reboot the robot manually, then wait for a fresh live map")
        robot = self.robot_getter()
        session = getattr(robot, "native_session_id", None)
        if (not robot.state.online or not session or session == pending.get("session_id")
                or getattr(robot, "native_map_session_id", None) != session):
            return result
        try:
            same = (self._identity() == pending["identity"]
                    and robot.state.map_head_id == pending["map_id"]
                    and self._geometry(robot.map) == pending["geometry"])
        except (HTTPException, ValueError, TypeError):
            return result
        result.update(status="verified" if same else "different",
                      message="Fresh robot map matches the backed-up geometry" if same else
                              "Fresh robot map differs from the backup; physical restoration is unverified")
        return result

    def _identity(self):
        # A previously registered robot can omit the optional registration fields on
        # reconnect. SSH separately binds the snapshot to MAC, product and system version.
        robot = self.robot_getter()
        identity = {"sn": getattr(robot, "native_live_sn", None),
                    "software": getattr(robot, "native_live_software", None)}
        if not all(identity.values()):
            cached = self._ssh_identity
            if cached and cached["context"] == self._identity_context():
                if any(value and value != cached["identity"][key] for key, value in identity.items()):
                    raise HTTPException(409, "SSH identity does not match the live robot registration")
                return cached["identity"].copy()
            raise HTTPException(409, "Robot registration identity is incomplete; refresh native map status to verify it over SSH")
        return identity

    def _preflight(self, require_map=False, require_identity=True, require_docked=True):
        if not self.legacy_getter():
            raise HTTPException(409, "Native maps require a real legacy robot")
        config = self.config_getter()
        if not config or not Path(config).is_file():
            raise HTTPException(409, "Configure NATIVE_MAP_SSH_CONFIG with a private SSH configuration file")
        robot = self.robot_getter()
        state = robot.state
        if not state.online:
            raise HTTPException(409, "Connect the robot before using native maps")
        if require_docked and (state.state != "docked" or not state.charging):
            raise HTTPException(409, "Place the robot on its charging base and wait until docked")
        session = getattr(robot, "native_session_id", None)
        if not session or getattr(robot, "native_state_session_id", None) != session:
            raise HTTPException(409, "Wait for a fresh robot status after reconnecting")
        identity = self._identity() if require_identity else None
        if require_map:
            mid = state.map_head_id
            live = getattr(robot, "map", None)
            if (type(mid) is not int or mid <= 0 or not valid_map(live)
                    or live.get("map_head_id") != mid or getattr(robot, "map_empty", False)
                    or getattr(robot, "native_map_session_id", None) != session):
                raise HTTPException(409, "Wait for a complete live robot map before creating a native backup")
        return identity

    def _io(self):
        factory = self.io_factory or NativeMapIO
        transport = factory(self.config_getter())
        robot = self.robot_getter()
        cap = getattr(robot, "captured", {}) or {}
        peer = getattr(robot, "native_peer_ip", None)
        if not peer:
            raise HTTPException(409, "Cannot identify one live robot network address")
        device = transport.verify_identity(cap.get("mac") or None, expected_ip=peer)
        if device.get("sysProduct") != "CECOTECCRL300" or device.get("sysVersion") != "S3.3.8":
            raise HTTPException(409, "Native maps require stock Conga 4090 product CECOTECCRL300 / S3.3.8")
        if self._ssh_identity and (not getattr(robot, "native_live_sn", None)
                                  or not getattr(robot, "native_live_software", None)):
            if transport.read_registration_identity() != self._identity():
                self._ssh_identity = None
                raise HTTPException(409, "SSH robot identity changed; refresh native map status")
        return transport, device

    def refresh(self):
        """Read missing registration data from the already verified SSH endpoint."""
        if not self.lock.acquire(blocking=False):
            raise HTTPException(409, "Another native map operation is running")
        try:
            self._ssh_identity = None
            self._preflight(require_identity=False, require_docked=False)
            robot = self.robot_getter()
            if robot.native_live_sn and robot.native_live_software:
                return self.status()
            context = self._identity_context()
            if not context[2]:
                raise HTTPException(409, "Cannot identify one live robot network address")
            transport, _ = self._io()
            identity = transport.read_registration_identity()
            self._preflight(require_identity=False, require_docked=False)
            if context != self._identity_context():
                raise HTTPException(409, "Robot connection or SSH configuration changed during refresh; retry")
            robot = self.robot_getter()
            live = {"sn": getattr(robot, "native_live_sn", None),
                    "software": getattr(robot, "native_live_software", None)}
            if any(value and value != identity[key] for key, value in live.items()):
                raise HTTPException(409, "SSH identity does not match the live robot registration")
            self._ssh_identity = {"context": context, "identity": identity.copy()}
            return self.status()
        finally:
            self.lock.release()

    @staticmethod
    def _summary(item):
        return {k: item[k] for k in ("id", "created_at", "map_id")}

    def listing(self):
        # Polling must never open or decode the potentially large native blobs.
        try:
            with self.index_path.open("rb") as stream:
                raw = stream.read(self.MAX_INDEX_BYTES + 1)
            if len(raw) > self.MAX_INDEX_BYTES:
                raise ValueError("Native index exceeds its limit")
            entries = json.loads(raw)["backups"]
            if not isinstance(entries, list) or len(entries) > self.MAX_BACKUPS:
                raise ValueError("Invalid native index")
            result = []
            for item in entries:
                if (not re.fullmatch(r"[0-9a-f]{32}", item["id"])
                        or type(item["map_id"]) is not int or item["map_id"] <= 0
                        or not isinstance(item["created_at"], str) or len(item["created_at"]) > 40):
                    raise ValueError("Invalid native index entry")
                if (self.root / (item["id"] + ".json")).is_file():
                    result.append(self._summary(item))
            return {"backups": sorted(result, key=lambda v: v["created_at"], reverse=True)}
        except FileNotFoundError:
            return {"backups": []}

    def status(self):
        result = {"configured": bool(self.config_getter() and Path(self.config_getter()).is_file()),
                  "available": False, "backup_available": False, **self.listing(),
                  "restore_verification": self.verification()}
        try:
            self._preflight()
            result.update(available=True, reason="Ready: connected and docked; SSH identity is checked during the operation")
            try:
                self._preflight(require_map=True)
                result["backup_available"] = True
            except HTTPException as exc:
                result["backup_reason"] = exc.detail
        except HTTPException as exc:
            result["reason"] = exc.detail
        return result

    def _save(self, mid, identity, files, geometry, device):
        if not files or any(not isinstance(v, bytes) for v in files.values()):
            raise ValueError("Native snapshot is empty")
        entries = self.listing()["backups"]
        if len(entries) >= self.MAX_BACKUPS:
            raise HTTPException(409, "Native backup limit reached (20); an administrator must remove old backup files before creating more")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.root, 0o700)
        ident = uuid.uuid4().hex
        item = {"id": ident, "created_at": datetime.now(timezone.utc).isoformat(),
                "map_id": mid, "identity": identity, "device": device, "geometry": geometry, "files": {}}
        for name, value in files.items():
            if not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
                raise ValueError("Invalid native filename")
            item["files"][name] = {"data": base64.b64encode(value).decode("ascii"),
                                    "sha256": hashlib.sha256(value).hexdigest()}
        atomic_json(self.root / (ident + ".json"), item)
        os.chmod(self.root / (ident + ".json"), 0o600)
        # Publish only after the complete private payload exists on disk.
        atomic_json(self.index_path, {"backups": [self._summary(item)] + entries})
        os.chmod(self.index_path, 0o600)
        return item

    def _load(self, ident):
        if not re.fullmatch(r"[0-9a-f]{32}", ident):
            raise HTTPException(404, "Native backup not found")
        try:
            item = json.loads((self.root / (ident + ".json")).read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise HTTPException(404, "Native backup not found") from None
        if item["id"] != ident or type(item["map_id"]) is not int or item["map_id"] <= 0:
            raise ValueError("Invalid native backup metadata")
        return item

    @staticmethod
    def _files(item):
        files = {}
        for name, entry in item["files"].items():
            if not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
                raise ValueError("Invalid native filename")
            value = base64.b64decode(entry["data"], validate=True)
            if hashlib.sha256(value).hexdigest() != entry["sha256"]:
                raise ValueError("Native backup integrity check failed")
            files[name] = value
        if not files:
            raise ValueError("Native backup is empty")
        return files

    def backup(self):
        if not self.lock.acquire(blocking=False):
            raise HTTPException(409, "Another native map operation is running")
        try:
            identity = self._preflight(require_map=True)
            if len(self.listing()["backups"]) >= self.MAX_BACKUPS:
                raise HTTPException(409, "Native backup limit reached (20); an administrator must remove old backup files before creating more")
            session = self.robot_getter().native_session_id
            mid = self.robot_getter().state.map_head_id
            geometry = self._geometry(self.robot_getter().map)
            io, device = self._io()
            files = io.read_pair(mid)
            if (self._preflight(require_map=True) != identity or self.robot_getter().state.map_head_id != mid
                    or self.robot_getter().native_session_id != session):
                raise HTTPException(409, "Robot or active map changed during backup; retry")
            if self._geometry(self.robot_getter().map) != geometry:
                raise HTTPException(409, "Live map geometry changed during backup; retry")
            return self._summary(self._save(mid, identity, files, geometry, device))
        finally:
            self.lock.release()

    def restore(self, ident, confirmed):
        if confirmed is not True:
            raise HTTPException(422, "Explicit confirmation is required")
        if not self.lock.acquire(blocking=False):
            raise HTTPException(409, "Another native map operation is running")
        try:
            identity = self._preflight()
            session = self.robot_getter().native_session_id
            item = self._load(ident)
            if item["identity"] != identity:
                raise HTTPException(409, "Backup belongs to another robot, model or firmware")
            files = self._files(item)
            io, device = self._io()
            if device != item["device"]:
                raise HTTPException(409, "Backup SSH device, product or firmware does not match")
            def require_same_docked_robot():
                if self._preflight() != identity or self.robot_getter().native_session_id != session:
                    raise HTTPException(409, "Robot changed before restore")

            require_same_docked_robot()
            io.restore_pair(item["map_id"], files, before_write=require_same_docked_robot)
            # Keep this durable receipt even if the robot disconnects after its
            # write. Verification is tied to the session that started the write.
            atomic_json(self.pending_path, {"backup_id": ident, "map_id": item["map_id"],
                        "geometry": item["geometry"], "identity": identity,
                        "session_id": session})
            os.chmod(self.pending_path, 0o600)
            if io.read_pair(item["map_id"]) != files:
                raise HTTPException(502, "Native restore read-back verification failed; reload verification remains pending")
            return {"status": "disk_verified_pending_reload", "map_id": item["map_id"], "backup_id": ident,
                    "message": "Native disk bytes verified. Robot map reload and physical verification are still pending."}
        finally:
            self.lock.release()


def register_native_maps(app, service):
    def private_client(request):
        host = request.client.host if request.client else ""
        try:
            loopback = ipaddress.ip_address(host).is_loopback
        except ValueError:
            loopback = False
        ingress = host == "172.30.32.2" and bool(os.environ.get("SUPERVISOR_TOKEN"))
        permitted = ingress
        if loopback:
            try:
                authority = urlsplit("//" + request.headers.get("host", ""))
                name = authority.hostname
                local_host = name == "localhost" or bool(name and ipaddress.ip_address(name).is_loopback)
                permitted = (local_host and not authority.username and not authority.password
                             and authority.path == "" and authority.query == "" and authority.fragment == ""
                             and (authority.port is None or 1 <= authority.port <= 65535))
            except ValueError:
                permitted = False
        if not permitted:
            raise HTTPException(403, "Native maps require Home Assistant ingress or a loopback connection (SSH forwarding)")

    def same_origin(request):
        private_client(request)
        if request.headers.get("x-native-map-action") != "1":
            raise HTTPException(403, "Native operation header required")
        site = request.headers.get("sec-fetch-site", "")
        if site and site not in ("same-origin", "none"):
            raise HTTPException(403, "Native operations require a same-origin request")
        origin = request.headers.get("origin")
        if origin and site != "same-origin" and urlsplit(origin).netloc != request.headers.get("host"):
            raise HTTPException(403, "Native operations require a same-origin request")

    def execute(operation):
        try:
            return operation()
        except HTTPException:
            raise
        except NativeMapError as exc:
            # The transport uses fixed diagnostic messages and discards SSH stderr.
            raise HTTPException(502, str(exc)) from None
        except (ValueError, KeyError, TypeError, OSError, RuntimeError):
            # Never expose SSH targets, credentials or private registration metadata.
            raise HTTPException(502, "Native operation failed; check server SSH configuration and private backup integrity") from None

    @app.get("/api/maps/native/status")
    def native_status(request: Request):
        private_client(request)
        return execute(service.status)

    @app.get("/api/maps/native/backups")
    def native_backups(request: Request):
        private_client(request)
        return execute(service.listing)

    @app.post("/api/maps/native/backup")
    def native_backup(request: Request):
        same_origin(request)
        return execute(service.backup)

    @app.post("/api/maps/native/refresh")
    def native_refresh(request: Request):
        same_origin(request)
        return execute(service.refresh)

    @app.post("/api/maps/native/backups/{backup_id}/restore")
    def native_restore(backup_id: str, request: Request, body: dict):
        same_origin(request)
        return execute(lambda: service.restore(backup_id, body.get("confirm")))
