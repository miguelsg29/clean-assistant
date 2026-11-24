"""Native snapshots with a fake transport: these tests never contact a robot."""
import base64
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from fastapi import FastAPI, HTTPException, Request
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.native_maps import NativeMaps, register_native_maps
from backend.native_map_io import NativeMapIO


class FakeIO:
    def __init__(self, _):
        self.files = {"scheme_data.info42": b"native-map", "customer_map_list_path.plan": b"plans"}
        self.writes = 0
        self.device = {"mac": "00:11:22:33:44:55", "sysProduct": "CECOTECCRL300", "sysVersion": "S3.3.8"}
        self.registration = {"sn": "robot-1", "software": "S3.3.8.23.42R"}

    def verify_identity(self, expected_mac, expected_ip=None):
        return self.device.copy()

    def read_pair(self, mid):
        return self.files.copy()

    def read_registration_identity(self):
        return self.registration.copy()

    def restore_pair(self, mid, files, before_write):
        before_write()
        self.writes += 1
        self.files = files.copy()


class NativeMapsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.config = Path(self.tmp.name) / "ssh-config"
        self.config.write_text("fake-test-config")
        self.io = FakeIO(None)
        self.robot = types.SimpleNamespace(
            state=types.SimpleNamespace(online=True, state="docked", charging=True, map_head_id=42),
            captured={"sn": "robot-1", "software": "S3.3.8.23.42R", "mac": "00:11:22:33:44:55"},
            native_live_sn="robot-1", native_session_id="session-1", native_map_session_id="session-1",
            native_state_session_id="session-1", native_peer_ip="192.0.2.1", native_live_software="S3.3.8.23.42R",
            map_empty=False,
            map={"bbox": [0, 0, 2, 2], "cells_b64": base64.b64encode(bytes([13, 13, 0, 255])).decode(),
                 "map_head_id": 42, "rooms": [{"id": 13, "center": [0, 0]}]})
        self.legacy = True
        self.service = NativeMaps(self.tmp.name, lambda: self.robot, lambda: self.legacy,
                                  lambda: str(self.config), lambda _: self.io)

    def test_backup_restart_integrity_and_private_listing(self):
        saved = self.service.backup()
        self.assertEqual(set(saved), {"id", "created_at", "map_id"})
        self.assertEqual(self.service.listing()["backups"], [saved])
        path = self.service.root / (saved["id"] + ".json")
        item = json.loads(path.read_text())
        item["files"]["scheme_data.info42"]["sha256"] = "wrong"
        path.write_text(json.dumps(item))
        with self.assertRaises(ValueError):
            self.service.restore(saved["id"], True)
        self.assertEqual(self.io.writes, 0)

    def test_optional_empty_files_and_metadata_only_bounded_listing(self):
        self.io.files["first_hardware_unbunding_flag.ini"] = b""
        saved = self.service.backup()
        with patch.object(self.service, "_load", side_effect=AssertionError("Blob opened by listing")):
            self.assertEqual(self.service.listing()["backups"], [saved])
            self.assertEqual(self.service.status()["backups"], [saved])
        self.service.restore(saved["id"], True)
        self.assertEqual(self.io.files["first_hardware_unbunding_flag.ini"], b"")
        self.service.MAX_BACKUPS = 1
        with self.assertRaises(HTTPException):
            self.service.backup()

    def test_session_continuity_and_pending_receipt_after_disconnect(self):
        original_read = self.io.read_pair
        def reconnect(mid):
            self.robot.native_session_id = "session-2"
            self.robot.native_map_session_id = "session-2"
            self.robot.native_state_session_id = "session-2"
            return original_read(mid)
        with patch.object(self.io, "read_pair", side_effect=reconnect):
            with self.assertRaises(HTTPException):
                self.service.backup()
        saved = self.service.backup()
        original_verify = self.io.verify_identity
        def reconnect_before_write(*args, **kwargs):
            self.robot.native_session_id = "session-3"
            self.robot.native_state_session_id = "session-3"
            return original_verify(*args, **kwargs)
        with patch.object(self.io, "verify_identity", side_effect=reconnect_before_write):
            with self.assertRaises(HTTPException):
                self.service.restore(saved["id"], True)
        self.assertEqual(self.io.writes, 0)
        original_restore = self.io.restore_pair
        def disconnect(mid, files, before_write):
            original_restore(mid, files, before_write)
            self.robot.state.online = False
            self.robot.native_session_id = None
        with patch.object(self.io, "restore_pair", side_effect=disconnect):
            self.service.restore(saved["id"], True)
        pending = json.loads(self.service.pending_path.read_text())
        self.assertEqual(pending["session_id"], "session-3")
        self.assertEqual(self.service.verification()["status"], "pending_reload")

    def test_restore_lost_map_requires_confirmation_and_identity(self):
        saved = self.service.backup()
        self.robot.map = None
        self.robot.state.map_head_id = None
        self.assertFalse(self.service.status()["backup_available"])
        self.assertTrue(self.service.status()["available"])
        with self.assertRaises(HTTPException):
            self.service.restore(saved["id"], False)
        self.robot.native_live_sn = "other-robot"
        with self.assertRaises(HTTPException):
            self.service.restore(saved["id"], True)
        self.robot.native_live_sn = "robot-1"
        self.assertEqual(self.service.restore(saved["id"], True)["status"], "disk_verified_pending_reload")
        self.assertEqual(self.io.writes, 1)

    def test_model_binding_dock_and_fresh_status_fail_closed(self):
        saved = self.service.backup()
        for change, value, original in (("state", "idle", "docked"), ("charging", False, True), ("online", False, True)):
            setattr(self.robot.state, change, value)
            with self.assertRaises(HTTPException):
                self.service.restore(saved["id"], True)
            setattr(self.robot.state, change, original)
        self.robot.native_state_session_id = "stale"
        with self.assertRaises(HTTPException):
            self.service.restore(saved["id"], True)
        self.robot.native_state_session_id = "session-1"
        self.io.device["mac"] = "different"
        with self.assertRaises(HTTPException):
            self.service.restore(saved["id"], True)
        self.assertEqual(self.io.writes, 0)

    def test_new_session_live_geometry_verification(self):
        saved = self.service.backup()
        self.service.restore(saved["id"], True)
        self.assertEqual(self.service.verification()["status"], "pending_reload")
        self.robot.native_session_id = "session-2"
        self.assertEqual(self.service.verification()["status"], "pending_reload")
        self.robot.native_map_session_id = "session-2"
        self.robot.map["cells_b64"] = base64.b64encode(bytes([63, 13, 0, 255])).decode()
        self.assertEqual(self.service.verification()["status"], "verified")
        self.robot.map["cells_b64"] = base64.b64encode(bytes([13, 13, 13, 255])).decode()
        self.assertEqual(self.service.verification()["status"], "different")

    def test_refresh_with_complete_registration_keeps_status_passive(self):
        with patch.object(self.io, "read_registration_identity") as read:
            self.assertTrue(self.service.refresh()["backup_available"])
            read.assert_not_called()

    def test_refresh_recovers_missing_identity_and_backup_preserves_it(self):
        self.robot.native_live_software = None
        with patch.object(self.io, "verify_identity", wraps=self.io.verify_identity) as verify:
            self.assertFalse(self.service.status()["backup_available"])
            verify.assert_not_called()
            self.assertTrue(self.service.refresh()["backup_available"])
            verify.assert_called_once_with("00:11:22:33:44:55", expected_ip="192.0.2.1")
        self.assertIsNone(self.robot.native_live_software)
        saved = self.service.backup()
        self.assertEqual(self.service._load(saved["id"])["identity"], self.io.registration)
        self.assertEqual(self.service.restore(saved["id"], True)["status"], "disk_verified_pending_reload")

    def test_refresh_allows_idle_but_backup_still_requires_dock(self):
        self.robot.native_live_sn = self.robot.native_live_software = None
        self.robot.state.state = "idle"
        self.robot.state.charging = False
        self.assertFalse(self.service.refresh()["backup_available"])
        with self.assertRaises(HTTPException):
            self.service.backup()
        self.robot.state.state = "docked"
        self.robot.state.charging = True
        self.assertTrue(self.service.status()["backup_available"])

    def test_refresh_rejects_identity_conflicts_and_does_not_publish(self):
        self.robot.native_live_software = None
        self.io.registration["sn"] = "another-robot"
        with self.assertRaises(HTTPException):
            self.service.refresh()
        self.assertFalse(self.service.status()["backup_available"])
        self.assertEqual(self.service.listing()["backups"], [])

    def test_refreshed_identity_is_bound_to_session_peer_and_configuration(self):
        self.robot.native_live_sn = self.robot.native_live_software = None
        for name, changed in (("native_session_id", "session-2"),
                              ("native_peer_ip", "192.0.2.20")):
            self.service.refresh()
            previous = getattr(self.robot, name)
            setattr(self.robot, name, changed)
            self.assertFalse(self.service.status()["backup_available"])
            setattr(self.robot, name, previous)
        self.service.refresh()
        self.config.write_text("changed-test-configuration")
        self.assertFalse(self.service.status()["backup_available"])

    def test_refresh_rejects_reconnect_while_ssh_is_reading(self):
        self.robot.native_live_software = None
        def reconnect():
            self.robot.native_session_id = self.robot.native_state_session_id = "new-session"
            return self.io.registration.copy()
        with patch.object(self.io, "read_registration_identity", side_effect=reconnect):
            with self.assertRaises(HTTPException):
                self.service.refresh()
        self.assertFalse(self.service.status()["backup_available"])

    def test_refresh_rejects_offline_and_concurrent_operations_before_ssh(self):
        with patch.object(self.io, "verify_identity", wraps=self.io.verify_identity) as verify:
            self.robot.state.online = False
            with self.assertRaises(HTTPException):
                self.service.refresh()
            self.robot.state.online = True
            self.service.lock.acquire()
            try:
                with self.assertRaises(HTTPException):
                    self.service.refresh()
            finally:
                self.service.lock.release()
            verify.assert_not_called()

    def test_backup_rechecks_ssh_identity_after_refresh(self):
        self.robot.native_live_software = None
        self.service.refresh()
        self.io.registration["software"] = "changed-firmware"
        with self.assertRaises(HTTPException):
            self.service.backup()
        self.assertEqual(self.service.listing()["backups"], [])
        self.assertFalse(self.service.status()["backup_available"])

    def test_round_trip_through_real_shell_on_a_synthetic_robot_filesystem(self):
        git_bash = Path("C:/Program Files/Git/bin/bash.exe")
        shell = str(git_bash) if git_bash.is_file() else shutil.which("sh")
        if not shell:
            self.skipTest("Requires a POSIX shell")
        sandbox = Path(self.tmp.name)
        log = sandbox / "robot-log"
        log.mkdir()
        files = {**self.io.files, "scheme_data.info43": b"second map",
                 "first_hardware_unbunding_flag.ini": b"", "carto_slam.data": b"navigation\x00"}
        for name, data in files.items():
            (log / name).write_bytes(data)

        class LocalTransport(NativeMapIO):
            ROOT = "./robot-log"

            @classmethod
            def _guard(cls):
                return "test -d ./robot-log && test ! -L ./robot-log || exit 1"

            def _run(self, command, payload=None):
                if "/etc/sysconf/sysVersion.ini" in command:
                    return (b"00:11:22:33:44:55\n192.0.2.2 1024 192.0.2.1 22\n"
                            b"sysProduct=CECOTECCRL300\nsysVersion=S3.3.8\n")
                args = [shell, "-s"] if payload is not None else [shell, "-c", command]
                return subprocess.run(args, cwd=sandbox, input=payload, capture_output=True,
                                      timeout=15, check=True).stdout

        self.service.io_factory = LocalTransport
        saved = self.service.backup()
        for name in files:
            if name != "first_hardware_unbunding_flag.ini":
                (log / name).unlink()
        self.robot.state.map_head_id = None
        self.robot.native_map_session_id = None
        restored = self.service.restore(saved["id"], True)
        self.assertEqual(restored["status"], "disk_verified_pending_reload")
        self.assertEqual({n: (log / n).read_bytes() for n in files}, files)
        self.assertEqual(self.service.verification()["status"], "pending_reload")
        self.robot.state.map_head_id = 42
        self.robot.native_session_id = self.robot.native_map_session_id = "reconnected"
        self.assertEqual(self.service.verification()["status"], "verified")

    def test_concurrency_and_route_security(self):
        self.service.lock.acquire()
        with self.assertRaises(HTTPException):
            self.service.backup()
        self.service.lock.release()
        app = FastAPI()
        register_native_maps(app, self.service)
        endpoints = {route.path: route.endpoint for route in app.routes}
        def request(host="127.0.0.1", headers=(), authority=b"127.0.0.1:8080"):
            return Request({"type": "http", "client": (host, 1234), "headers": [(b"host", authority), *headers],
                            "method": "POST", "path": "/api/maps/native/backup"})
        for req in (request(), request(headers=[(b"x-native-map-action", b"1"),
                                               (b"sec-fetch-site", b"cross-site")])):
            with self.assertRaises(HTTPException) as failure:
                endpoints["/api/maps/native/backup"](req)
            self.assertEqual(failure.exception.status_code, 403)
            with self.assertRaises(HTTPException) as failure:
                endpoints["/api/maps/native/refresh"](req)
            self.assertEqual(failure.exception.status_code, 403)
        saved = endpoints["/api/maps/native/backup"](request(headers=[(b"x-native-map-action", b"1"),
                                                                      (b"sec-fetch-site", b"same-origin")]))
        self.assertEqual(saved["map_id"], 42)
        self.robot.native_live_software = None
        refreshed = endpoints["/api/maps/native/refresh"](request(headers=[(b"x-native-map-action", b"1"),
                                                                         (b"sec-fetch-site", b"same-origin")]))
        self.assertTrue(refreshed["backup_available"])
        self.assertNotIn("identity", refreshed)
        self.assertEqual(self.io.writes, 0)
        with self.assertRaises(HTTPException):
            endpoints["/api/maps/native/backups"](request("192.0.2.9"))
        for authority in (b"rebinding.example:8080", b"localhost@evil.example", b"localhost/path"):
            with self.assertRaises(HTTPException):
                endpoints["/api/maps/native/status"](request(authority=authority))
        for authority in (b"localhost:8080", b"[::1]:8080", b"127.0.0.2:8080"):
            self.assertIn("available", endpoints["/api/maps/native/status"](request(authority=authority)))
        with patch.dict("os.environ", {"SUPERVISOR_TOKEN": ""}):
            with self.assertRaises(HTTPException):
                endpoints["/api/maps/native/status"](request("172.30.32.2", authority=b"ha.example"))
        with patch.dict("os.environ", {"SUPERVISOR_TOKEN": "test-supervisor"}):
            self.assertIn("available", endpoints["/api/maps/native/status"](request("172.30.32.2", authority=b"ha.example")))


if __name__ == "__main__":
    unittest.main()
