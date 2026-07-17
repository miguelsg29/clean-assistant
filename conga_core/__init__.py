"""conga_core — núcleo reutilizable del protocolo Conga 8090.

Comandos (`commands`), estado (`state`) y mapa (`map`). Este paquete es la
"fuente de la verdad" del protocolo, compartible con el puente MQTT.
"""
from . import commands, state, map  # noqa: F401

__all__ = ["commands", "state", "map"]
