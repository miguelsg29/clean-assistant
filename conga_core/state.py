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


# faultCode -> mensaje entendible (en español; el frontend los traduce por su texto). Lista
# capturada de la app de Cecotec del Conga 4690 (issue #6, gracias @teosoft0) + 510 de @serra410.
WARN_MESSAGES = {
    500: "Láser bloqueado: retira lo que lo obstruya",
    501: "Rueda en el aire: coloca el robot en el suelo",
    502: "Batería baja: carga el robot",
    503: "Coloca el depósito de suciedad y el filtro HEPA",
    504: "Campo magnético fuerte: cambia el robot de sitio",
    505: "Quita obstáculos junto a la base e inténtalo de nuevo",
    506: "Limpia los sensores anticolisión e inténtalo de nuevo",
    507: "Reubicación fallida: elige un recorrido más corto",
    508: "Coloca el robot en el suelo e inícialo",
    509: "Limpia los sensores anticaída y reubica el robot",
    510: "Parachoques atascado o bloqueado",
    511: "No pudo llegar a la base: quita obstáculos alrededor",
    512: "Error al volver a la base",
    514: "Atascado: colócalo en la base de carga",
    515: "Base bloqueada: retira los obstáculos de alrededor",
    516: "Temperatura fuera de rango: espera a que se normalice",
    517: "Actualizando el sistema: inténtalo más tarde",
    518: "Batería baja: espera a que termine de cargar",
    519: "Cepillo central bloqueado: retíralo y límpialo",
    520: "Cepillo lateral bloqueado: quita los obstáculos",
    521: "Coloca bien el depósito de agua",
    522: "Falta la mopa: colócala",
    523: "Revisa el filtro: límpialo y sécalo",
    525: "Depósito de agua bajo",
    526: "La mopa puede necesitar limpieza",
    527: "Depósito de polvo lleno",
    530: "Temperatura de la batería anormal",
    531: "Temperatura de la batería normalizada",
    2003: "Batería demasiado baja para la programación",
}


def _warn_message(fault):
    try:
        return WARN_MESSAGES.get(int(fault))
    except (TypeError, ValueError):
        return None


@dataclass
class RobotState:
    online: bool = False
    state: str = "unknown"          # docked/cleaning/paused/returning/idle/error
    battery: int | None = None      # 0-100 (%)
    charging: bool = False
    fault: int | None = None
    warning: str | None = None      # aviso entendible (p. ej. "Depósito de agua bajo"), o None
    area: float | None = None       # m² limpiados
    clean_time: int | None = None   # minutos
    cleaning_room: int | None = None
    repeat_clean: int | None = None   # repeatClean del report_data: 1 = segunda pasada
    work_mode: int | None = None      # workMode crudo (45 = modo automático de mapa nuevo)
    map_head_id: int | None = None
    map_name: str | None = None
    # ajustes reflejados (lo que sabemos del robot)
    quiet: dict | None = None       # {is_open, begin_time, end_time}
    voice: dict | None = None       # {voiceMode, volume}
    consumables: dict | None = None
    auto_upgrade: int | None = None
    collect_freq: int | None = None   # frecuencia autovaciado: -1=Nunca, 0=tras cada limpieza, N=min
    base_type: str | None = None      # "Base de carga" | "Colector automático" (preferencia local)

    def update_from_report(self, data: dict[str, Any]) -> "RobotState":
        """Actualiza desde el `data` de un report_data."""
        self.online = True
        mode = data.get("workMode")
        charge = data.get("chargeStatus")
        fault = data.get("faultCode")
        self.charging = charge == 1
        self.fault = fault
        self.warning = _warn_message(fault)
        self.work_mode = mode

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
        elif mode in (36, 2, 1):
            st = "cleaning"
        else:
            st = "idle"
        if _is_error_fault(fault):
            st = "error"
        self.state = st

        bat = data.get("battary")
        if isinstance(bat, int):
            self.battery = int(bat / 2)           # escala 0-200 -> 0-100
        cs = data.get("cleanSize")                # cleanSize viene en centésimas de m² (1506 = 15,06 m²)
        if cs is not None:
            self.area = round(cs / 100.0, 2)
        self.clean_time = data.get("cleanTime", self.clean_time)   # cleanTime ya está en minutos
        self.cleaning_room = data.get("cleaning_roomId", self.cleaning_room)
        self.repeat_clean = data.get("repeatClean", self.repeat_clean)
        if data.get("map_head_id"):
            self.map_head_id = data["map_head_id"]
        if data.get("current_map_name"):
            self.map_name = data["current_map_name"]
        return self

    def to_dict(self) -> dict:
        return asdict(self)
