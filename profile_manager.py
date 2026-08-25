"""
profile_manager.py
-------------------
Verwaltet mehrere unabhängige CTAM-"Profile" - jeweils eine eigene SQLite-
Datei, z. B. für verschiedene Bewerbungsrunden oder Jahre ("Bewerbung 2026",
"Werkstudentenjobs", ...). Welches Profil zuletzt aktiv war, wird in einer
kleinen JSON-Konfigurationsdatei im Nutzerverzeichnis gemerkt, damit CTAM
das Profil beim nächsten Start automatisch wieder öffnet.

Bewusst keine echte Mehrbenutzer-/Login-Verwaltung mit Passwörtern o. Ä. -
CTAM bleibt eine lokale Offline-Anwendung ohne Benutzerkonten. "Profile"
bezeichnet hier lediglich unterschiedliche Datendateien.
"""

from __future__ import annotations

import json
from pathlib import Path


CONFIG_DIR = Path.home() / ".ctam"
CONFIG_FILE = CONFIG_DIR / "profiles.json"
DEFAULT_PROFILE_NAME = "Standard"


class ProfileManager:
    """Liest/schreibt die Liste bekannter Profile (Name -> Pfad zur .db-Datei)
    sowie das zuletzt aktive Profil."""

    def __init__(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self._data = self._load()

    def _load(self) -> dict:
        if CONFIG_FILE.exists():
            try:
                return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        # Erststart: ein Standardprofil im aktuellen Arbeitsverzeichnis anlegen
        return {
            "profiles": {DEFAULT_PROFILE_NAME: "career_tracker.db"},
            "last_active": DEFAULT_PROFILE_NAME,
        }

    def _save(self) -> None:
        CONFIG_FILE.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    # -- Öffentliche API ------------------------------------------------

    def list_profiles(self) -> dict[str, str]:
        """Gibt {Profilname: Datenbankpfad} zurück."""
        return dict(self._data.get("profiles", {}))

    def get_last_active(self) -> str:
        last = self._data.get("last_active", DEFAULT_PROFILE_NAME)
        if last not in self._data.get("profiles", {}):
            last = next(iter(self._data.get("profiles", {})), DEFAULT_PROFILE_NAME)
        return last

    def get_path(self, profile_name: str) -> str:
        return self._data["profiles"].get(profile_name, "career_tracker.db")

    def add_profile(self, name: str, db_path: str) -> None:
        if not name.strip():
            raise ValueError("Profilname darf nicht leer sein.")
        self._data.setdefault("profiles", {})[name.strip()] = db_path
        self._save()

    def remove_profile(self, name: str) -> None:
        self._data.get("profiles", {}).pop(name, None)
        if self._data.get("last_active") == name:
            remaining = self._data.get("profiles", {})
            self._data["last_active"] = next(iter(remaining), DEFAULT_PROFILE_NAME)
        self._save()

    def set_last_active(self, name: str) -> None:
        self._data["last_active"] = name
        self._save()
