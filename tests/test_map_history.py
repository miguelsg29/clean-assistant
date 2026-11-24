"""Local map history integrity and retention, using invented decoded grids."""
import base64
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.map_history import MapHistory, atomic_json, valid_map


def example(name="Home", cells=b"\x0d\x0d\x00\xff"):
    return {"name": name, "bbox": [0, 0, 2, 2], "sample": False,
            "cells_b64": base64.b64encode(cells).decode(),
            "rooms": [{"id": 13, "name": "Kitchen", "named": True, "center": [0, 0]}],
            "stored_zones": [], "robot": {"x": 0, "y": 0}}


class MapHistoryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "map_history.json"
        self.history = MapHistory(str(self.path))

    def test_legacy_metadata_changes_emit_map_and_new_head_clears_old_sections(self):
        from conga_core.config import RobotConfig
        from conga_core.legacy.robot import LegacyRobot

        robot = LegacyRobot(RobotConfig(), logger=lambda _: None)
        events = []
        robot.on_map = lambda: events.append("map")
        robot.on_pose = lambda: events.append("pose")
        head = {"map_head_id": 42, "size_x": 2, "size_y": 2}
        frame = {"head": head, "grid": {"pixels": 1}, "walls": {"areas": []}}
        renamed = example()
        renamed["rooms"][0]["name"] = "Renamed"
        with patch("conga_core.legacy.robot.mapdecode.decode_map", return_value=frame), \
             patch.object(robot, "_legacy_info", return_value={}), \
             patch.object(robot, "_accumulate_trail"), \
             patch("conga_core.legacy.robot.cmap.build_map", side_effect=[example(), renamed]):
            robot._on_map(b"")
            robot._on_map(b"")
        self.assertEqual(events, ["map", "map"])
        self.assertEqual(robot.map["map_head_id"], 42)
        with patch("conga_core.legacy.robot.mapdecode.decode_map", return_value={"head": {"map_head_id": 43}}):
            robot._on_map(b"")
        self.assertNotIn("grid", robot._lmap)
        self.assertNotIn("walls", robot._lmap)

    def test_separate_maps_and_restart(self):
        self.assertTrue(self.history.record(42, example()))
        self.assertTrue(self.history.record(43, example("Upstairs")))
        versions = MapHistory(str(self.path)).listing()["versions"]
        self.assertEqual({v["map_id"] for v in versions}, {42, 43})
        for version in versions:
            item = self.history.get(version["map_id"], version["version"])
            self.assertEqual(item["map"]["map_head_id"], version["map_id"])
            item["map"]["name"] = "External mutation"
            self.assertNotEqual(self.history.get(version["map_id"], version["version"])
                                ["map"]["name"], "External mutation")

    def test_invalid_frames_never_replace_last_good(self):
        self.history.record(42, example())
        original = self.path.read_bytes()
        invalid = [{}, example(cells=b""), example(cells=bytes(4)),
                   dict(example(), sample=True), dict(example(), no_map=True),
                   dict(example(), _cached=True),
                   dict(example(), cells_b64="!!!"), dict(example(), bbox=[0, 0, 3, 3]),
                   dict(example(), map_head_id=43)]
        for data in invalid:
            self.assertFalse(self.history.record(42, data))
        for map_id in (None, 0, False, "42", -1):
            self.assertFalse(self.history.record(map_id, example()))
        self.assertEqual(self.path.read_bytes(), original)

    def test_pose_trail_cleaning_progress_dedup(self):
        data = example()
        self.history.record(42, data)
        updated = copy.deepcopy(data)
        updated.update(robot={"x": 1, "y": 1}, robot_world={"x": 2, "y": 2}, trail=[[1, 1]])
        self.assertFalse(self.history.record(42, updated))
        updated["cells_b64"] = base64.b64encode(bytes([63, 13, 0, 255])).decode()
        updated["rooms"][0]["center"] = [1, 1]
        updated["rooms"].append({"id": 63, "name": "Temporary", "named": False})
        self.assertFalse(self.history.record(42, updated))
        self.assertEqual(len(self.history.listing()["versions"]), 1)

    def test_grid_noise_preserves_previous_checkpoint(self):
        baseline = example()
        self.history.record(42, baseline)
        first_version = self.history.listing()["versions"][0]["version"]
        for cell in range(1, 20):
            self.history.record(42, example(cells=bytes([13, 13, cell, 255])))
        versions = self.history.listing()["versions"]
        self.assertEqual(len(versions), 2)
        self.assertIsNotNone(self.history.get(42, first_version))
        self.assertEqual(base64.b64decode(self.history.get(42, versions[0]["version"])
                                         ["map"]["cells_b64"])[2], 19)

    def test_metadata_versions_and_bounded_retention(self):
        history = MapHistory(str(self.path), retention_per_map=3, max_maps=2)
        for index in range(6):
            history.record(42, example(name=f"Name {index}"))
        self.assertEqual(len(history.listing()["versions"]), 3)
        self.assertEqual(len(list(history.directory.glob("*.json"))), 3)
        history.record(43, example())
        history.record(44, example())
        self.assertEqual({v["map_id"] for v in history.listing()["versions"]}, {43, 44})
        self.assertEqual(len(MapHistory(str(self.path)).listing()["versions"]), 2)
        self.assertEqual(len(list(history.directory.glob("*.json"))), 2)

    def test_small_index_lazy_startup_and_new_snapshot_only(self):
        self.history.record(42, example())
        self.assertNotIn("cells_b64", self.path.read_text())
        self.assertNotIn('"map":', self.path.read_text())
        with patch("backend.map_history.atomic_json", wraps=atomic_json) as writes:
            self.history.record(42, example(name="Updated"))
        self.assertEqual(writes.call_count, 2)
        with patch("backend.map_history.valid_map", side_effect=AssertionError("eager grid read")):
            restored = MapHistory(str(self.path))
        self.assertEqual(len(restored.listing()["versions"]), 2)

    def test_index_write_failure_removes_unpublished_snapshot(self):
        self.history.record(42, example())
        original = self.path.read_bytes()
        snapshots = list(self.history.directory.glob("*.json"))

        def fail_index(path, data):
            if Path(path) == self.path:
                raise OSError("index failure")
            atomic_json(path, data)

        with patch("backend.map_history.atomic_json", side_effect=fail_index):
            with self.assertRaises(OSError):
                self.history.record(42, example(name="Unpublished"))
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(list(self.history.directory.glob("*.json")), snapshots)
        self.assertEqual(len(self.history.listing()["versions"]), 1)

    def test_atomic_write_failure_keeps_disk_and_memory(self):
        self.history.record(42, example())
        original = self.path.read_bytes()
        with patch("backend.map_history.os.replace", side_effect=OSError("full disk")):
            with self.assertRaises(OSError):
                self.history.record(42, example(name="Changed"))
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(len(self.history.listing()["versions"]), 1)
        self.assertEqual(list(self.path.parent.glob("*.tmp")), [])
        cache = self.path.parent / "cache.json"
        atomic_json(cache, example())
        self.assertTrue(valid_map(json.loads(cache.read_text())))

    def test_corrupt_file_is_tolerated(self):
        self.path.write_text("{truncated")
        self.assertEqual(MapHistory(str(self.path)).listing()["versions"], [])

    def test_read_only_api_preview_and_export(self):
        with patch.dict(os.environ, {"DATA_DIR": self.directory.name,
                                     "CONGA_MODE": "mock", "MQTT_HOST": ""}):
            from backend import app as backend
        from fastapi import HTTPException

        self.history.record(42, example())
        version = self.history.listing()["versions"][0]["version"]
        with patch.object(backend, "map_history", self.history), patch.object(
                backend, "view_settings", {"rot": 1, "flip": 1}):
            self.assertEqual(backend.get_map_history()["versions"][0]["map_id"], 42)
            image = backend.preview_map_version(42, version)
            self.assertEqual(image.status_code, 200)
            self.assertEqual(image.headers["content-type"], "image/png")
            from conga_core.mapimage import render_png
            expected, _ = render_png(self.history.get(42, version)["map"],
                                     view={"rot": 1, "flip": 1}, live=False)
            self.assertEqual(image.body, expected)
            downloaded = backend.export_map_version(42, version)
            self.assertEqual(json.loads(downloaded.body)["map_id"], 42)
            self.assertIn("attachment", downloaded.headers["content-disposition"])
            with self.assertRaises(HTTPException) as missing:
                backend.preview_map_version(99, "unknown")
            self.assertEqual(missing.exception.status_code, 404)
            routes = [r for r in backend.app.routes if getattr(r, "path", "").startswith("/api/maps/history")]
            self.assertEqual(len(routes), 4)
            self.assertTrue(all(r.methods == {"GET"} for r in routes))

    def test_cache_validation_dedup_and_cached_display_exclusion(self):
        with patch.dict(os.environ, {"DATA_DIR": self.directory.name, "CONGA_MODE": "mock"}):
            from backend import app as backend
        cache = Path(self.directory.name) / "map_cache.json"
        robot = types.SimpleNamespace(map=example(), map_empty=False,
                                      state=types.SimpleNamespace(map_head_id=42))
        with patch.object(backend, "robot", robot), patch.object(backend, "map_history", self.history), \
                patch.object(backend, "MAP_CACHE", str(cache)), \
                patch.object(backend, "_last_saved_map_id", None):
            backend._save_map()
            self.assertEqual(json.loads(cache.read_text())["map_head_id"], 42)
            with patch.object(backend, "atomic_json", wraps=atomic_json) as writes:
                robot.map["robot"]["x"] = 1
                backend._save_map()
            self.assertEqual(writes.call_count, 0)
            loaded = backend._load_map()
            robot.map = dict(loaded, _cached=True)
            robot.map["name"] = "Cached display edit"
            backend._save_map()
            self.assertEqual(len(self.history.listing()["versions"]), 1)
            self.assertEqual(json.loads(cache.read_text())["name"], "Home")
            cache.write_text("{broken")
            self.assertIsNone(backend._load_map())
            self.assertEqual(len(self.history.listing()["versions"]), 1)


if __name__ == "__main__":
    unittest.main()
