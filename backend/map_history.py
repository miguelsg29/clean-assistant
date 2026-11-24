"""Bounded local copies of decoded maps; these are not robot firmware backups."""
from __future__ import annotations

import base64
import binascii
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
import threading
import time
from datetime import datetime, timezone


def atomic_json(path: str | Path, data: dict) -> None:
    """Replace a JSON file only after its complete contents reach disk."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def valid_map(data: object) -> bool:
    """Require a real, complete, nonempty decoded grid before replacing a good copy."""
    if (not isinstance(data, dict) or data.get("sample") or data.get("no_map")
            or data.get("_cached")):
        return False
    bbox = data.get("bbox")
    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
        return False
    width, height = bbox[2:]
    if any(type(n) is not int or n <= 0 for n in (width, height)):
        return False
    if width * height > 4_000_000 or not isinstance(data.get("cells_b64"), str):
        return False
    if len(data["cells_b64"]) > ((width * height + 2) // 3) * 4:
        return False
    if any(type(n) not in (int, float) or not math.isfinite(n) for n in bbox[:2]):
        return False
    if not isinstance(data.get("rooms", []), list) or any(
            not isinstance(room, dict) for room in data.get("rooms", [])):
        return False
    if not isinstance(data.get("stored_zones", []), list) or any(
            not isinstance(zone, dict) for zone in data.get("stored_zones", [])):
        return False
    world = data.get("world")
    if world is not None and (not isinstance(world, dict) or any(
            type(world.get(key)) not in (int, float) or not math.isfinite(world[key])
            for key in ("min_x", "min_y", "res")) or world["res"] <= 0):
        return False
    try:
        cells = base64.b64decode(data["cells_b64"], validate=True)
    except (ValueError, binascii.Error):
        return False
    return len(cells) == width * height and any(cells)


def _metadata(data: dict) -> dict:
    """Persistent user settings, excluding grid-derived room geometry."""
    return {"name": data.get("name"), "world": data.get("world"),
            "stored_zones": data.get("stored_zones"), "house": data.get("house"),
            "rooms": [{k: v for k, v in room.items() if k not in ("center", "bbox")}
                      for room in data.get("rooms", []) if room.get("named", True)]}


def _fingerprint(data: dict) -> str:
    stable = {k: v for k, v in data.items() if k not in ("robot", "robot_world", "trail")}
    # The decoder represents already-cleaned room cells as room ID + 50.
    # Cleaning progress alone must not displace useful structural versions.
    ids = {r.get("id") for r in data.get("rooms", [])
           if type(r.get("id")) is int and r.get("named", True)}
    translation = bytes(v - 50 if v - 50 in ids and v not in ids and v != 255 else v
                        for v in range(256))
    cells = base64.b64decode(data["cells_b64"]).translate(translation)
    stable["cells_b64"] = base64.b64encode(cells).decode("ascii")
    stable["rooms"] = _metadata(data)["rooms"]
    content = json.dumps(stable, sort_keys=True, ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:20]


class MapHistory:
    """Keep the last distinct versions per map, independently of the live cache.

    Snapshots are written before their small atomic index. Startup reads only that
    index; pixel grids are loaded on demand. Pose and trail changes do not create
    versions. Oldest inactive map histories are evicted only at the map count limit.
    """

    def __init__(self, path: str, retention_per_map: int = 10, max_maps: int = 20):
        self.path = path
        self.directory = Path(path).with_suffix("")
        self.retention_per_map = max(1, retention_per_map)
        self.max_maps = max(1, max_maps)
        self._lock = threading.RLock()
        self._maps: dict[str, list[dict]] = {}
        self._grid_windows: dict[str, float | None] = {}
        try:
            with open(path, encoding="utf-8") as stream:
                saved = json.load(stream)
            if saved.get("schema_version") == 2 and isinstance(saved.get("maps"), dict):
                for key, versions in saved["maps"].items():
                    if not isinstance(versions, list):
                        continue
                    good = [v for v in versions if isinstance(v, dict)
                            and type(v.get("map_id")) is int and v["map_id"] > 0
                            and str(v["map_id"]) == key
                            and isinstance(v.get("version"), str)
                            and re.fullmatch(r"[0-9a-f]{20}", v["version"])
                            and isinstance(v.get("saved_at"), str)
                            and isinstance(v.get("settings"), dict)]
                    if good:
                        self._maps[key] = good[:self.retention_per_map]
                self._maps = dict(sorted(self._maps.items(), key=lambda p: p[1][0]["saved_at"],
                                         reverse=True)[:self.max_maps])
        except (OSError, ValueError, TypeError, AttributeError):
            pass

    def record(self, map_id: object, data: dict) -> bool:
        if type(map_id) is not int or map_id <= 0 or not valid_map(data):
            return False
        if data.get("map_head_id") not in (None, map_id):
            return False
        snapshot = copy.deepcopy(data)
        snapshot["map_head_id"] = map_id
        version = _fingerprint(snapshot)
        with self._lock:
            current = self._maps.get(str(map_id), [])
            if (current and current[0]["version"] == version
                    and self._snapshot_path(map_id, version).exists()):
                return False
            saved_at = datetime.now(timezone.utc).isoformat()
            envelope = {"schema_version": 1, "map_id": map_id, "version": version,
                        "saved_at": saved_at, "map": snapshot}
            entry = {"map_id": map_id, "version": version, "saved_at": saved_at,
                     "name": snapshot.get("name", ""), "room_count": len(_metadata(snapshot)["rooms"]),
                     "width": snapshot["bbox"][2], "height": snapshot["bbox"][3],
                     "settings": _metadata(snapshot)}
            # Build separately: failed persistence must preserve the in-memory last-good copy too.
            updated = dict(self._maps)
            grid_only = bool(current and current[0]["settings"] == entry["settings"])
            now = time.monotonic()
            start = self._grid_windows.get(str(map_id))
            coalesce = grid_only and start is not None and now - start < 300 and len(current) > 1
            previous = current[1:] if coalesce else current
            updated[str(map_id)] = ([entry] + [v for v in previous if v["version"] != version]
                                    )[:self.retention_per_map]
            updated = dict(sorted(updated.items(), key=lambda p: p[1][0]["saved_at"],
                                  reverse=True)[:self.max_maps])
            snapshot_path = self._snapshot_path(map_id, version)
            existed = snapshot_path.exists()
            # Write a new immutable payload first. Reusing an older version keeps
            # its original capture time rather than overwriting a referenced file.
            if not existed:
                atomic_json(snapshot_path, envelope)
            else:
                older = next((v for v in current if v["version"] == version), None)
                if older:
                    entry["saved_at"] = older["saved_at"]
            try:
                atomic_json(self.path, {"schema_version": 2, "maps": updated})
            except (OSError, ValueError, TypeError):
                if not existed:
                    snapshot_path.unlink(missing_ok=True)
                raise
            old_paths = {self._snapshot_path(v["map_id"], v["version"])
                         for entries in self._maps.values() for v in entries}
            kept = {self._snapshot_path(v["map_id"], v["version"])
                    for entries in updated.values() for v in entries}
            self._maps = updated
            self._grid_windows = {key: value for key, value in self._grid_windows.items()
                                  if key in updated}
            for obsolete in old_paths - kept:
                try:
                    obsolete.unlink(missing_ok=True)
                except OSError:
                    pass
            if not coalesce:
                self._grid_windows[str(map_id)] = now if grid_only else None
        return True

    def listing(self) -> dict:
        with self._lock:
            versions = []
            for entries in self._maps.values():
                for entry in entries:
                    versions.append({k: v for k, v in entry.items() if k != "settings"})
            return {"versions": sorted(versions, key=lambda v: v["saved_at"], reverse=True),
                    "retention_per_map": self.retention_per_map, "max_maps": self.max_maps}

    def get(self, map_id: int, version: str) -> dict | None:
        with self._lock:
            entry = next((v for v in self._maps.get(str(map_id), []) if v["version"] == version), None)
            if entry is None:
                return None
            try:
                with self._snapshot_path(map_id, version).open(encoding="utf-8") as stream:
                    snapshot = json.load(stream)
                if (snapshot.get("map_id") == map_id and snapshot.get("version") == version
                        and valid_map(snapshot.get("map")) and _fingerprint(snapshot["map"]) == version):
                    return snapshot
            except (OSError, ValueError, AttributeError):
                pass
            return None

    def _snapshot_path(self, map_id: int, version: str) -> Path:
        return self.directory / f"{map_id}-{version}.json"
