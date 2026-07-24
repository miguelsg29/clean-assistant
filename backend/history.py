"""Registro de actividad (historial de limpiezas) de Clean Assistant.

Cada entrada resume una sesión de limpieza: tipo (manual/programada), habitaciones,
m² limpiados, duración, fecha/hora y día de la semana. Se persiste en history.json.
"""
from __future__ import annotations
import json
import os


class HistoryStore:
    def __init__(self, path: str = "history.json", cap: int = 300):
        self.path = path
        self.cap = cap
        self.entries: list[dict] = []
        self._load()

    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, encoding="utf-8") as f:
                    self.entries = json.load(f).get("entries", [])
            except Exception:
                self.entries = []

    def _save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump({"entries": self.entries[-self.cap:]}, f, ensure_ascii=False, indent=1)
        except Exception:
            pass

    def add(self, entry: dict) -> dict:
        self.entries.append(entry)
        self.entries = self.entries[-self.cap:]
        self._save()
        return entry

    def list(self, limit: int = 120) -> list[dict]:
        return list(reversed(self.entries[-limit:]))     # más recientes primero

    def clear(self):
        self.entries = []
        self._save()
