"""Modelo de estado del robot, derivado del report_data crudo."""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any


def _is_error_fault(fault) -> bool:
    """faultCode fuera de los avisos de estación (21xx) y consumibles (5xx)."""
    try:
        f = int(fault)
    except (TypeError, ValueError):
        return False
    return f != 0 and not (2100 <= f <= 2199) and not (500 <= f <= 599)


@dataclass
class RobotState:
    online: bool = False
    state: str = "unknown"          # docked/cleaning/paused/returning/idle/error
    battery: int | None = None      # 0-100 (%)
    charging: bool = False
    fault: int | None = None
    area: float | None = None       # m² limpiados
    clean_time: int | None = None   # minutos
    cleaning_room: int | None = None
    repeat_clean: int | None = None   # repeatClean del report_data: 1 = segunda pasada
    map_head_id: int | None = None
    map_name: str | None = None
    # ajustes reflejados (lo que sabemos del robot)
    quiet: dict | None = None       # {is_open, begin_time, end_time}
    voice: dict | None = None       # {voiceMode, volume}
    consumables: dict | None = None
    auto_upgrade: int | None = None

    def update_from_report(self, data: dict[str, Any]) -> "RobotState":
        """Actualiza desde el `data` de un report_data."""
        self.online = True
        mode = data.get("workMode")
        charge = data.get("chargeStatus")
        fault = data.get("faultCode")
        self.charging = charge == 1
        self.fault = fault

        if charge == 1:
            st = "docked"
        elif mode == 5:
            st = "returning"
        elif mode == 37:
            st = "paused"
        elif mode == 45:
            # modo automático de mapa nuevo: usa el MISMO workMode para mapear y para la
            # primera limpieza. Si ya está sobre una habitación, está limpiando; si no, mapeando.
            st = "cleaning" if data.get("cleaning_roomId", self.cleaning_room) else "mapping"
        elif mode in (36, 2):
            st = "cleaning"
        else:
            st = "idle"
        if _is_error_fault(fault):
            st = "error"
        self.state = st

        bat = data.get("battary")
        if isinstance(bat, int):
            self.battery = int(bat / 2)           # escala 0-200 -> 0-100
        self.area = data.get("cleanSize", self.area)
        self.clean_time = data.get("cleanTime", self.clean_time)
        self.cleaning_room = data.get("cleaning_roomId", self.cleaning_room)
        self.repeat_clean = data.get("repeatClean", self.repeat_clean)
        if data.get("map_head_id"):
            self.map_head_id = data["map_head_id"]
        if data.get("current_map_name"):
            self.map_name = data["current_map_name"]
        return self

    def to_dict(self) -> dict:
        return asdict(self)
