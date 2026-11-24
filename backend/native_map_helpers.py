"""Local validation and durable writes for private native snapshots."""
import base64
import binascii
import json
import math
import os
from pathlib import Path
import tempfile


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

