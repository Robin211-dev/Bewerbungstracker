"""
database_manager.py
--------------------
Kapselt den gesamten SQLite-Datenbankzugriff für den Career Tracker &
Application Manager (CTAM). Die gesamte Anwendung läuft komplett offline;
standardmäßig wird ausschließlich die Python-Standardbibliothek `sqlite3`
verwendet. Ist das optionale Paket `sqlcipher3` installiert, kann die
Datenbank stattdessen verschlüsselt geführt werden (siehe SQLCIPHER_AVAILABLE).

Enthält:
    - DuplicateError:      Exception für die Duplikat-Prävention.
    - ApplicationManager:  Kernklasse mit sämtlicher Geschäftslogik und
                            Datenbankzugriff (CRUD + Validierung + Reports).
"""

from __future__ import annotations

import csv
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

# -- Optionale SQLCipher-Unterstützung ---------------------------------------
# Falls das Paket `sqlcipher3` installiert ist, kann CTAM die Datenbank
# verschlüsselt führen (empfohlen bei gemeinsam genutzten Rechnern). Ist es
# nicht installiert, läuft CTAM automatisch mit normalem sqlite3 weiter,
# ohne Zusatzabhängigkeiten zu erzwingen.
try:
    import sqlcipher3  # type: ignore
    SQLCIPHER_AVAILABLE = True
except ImportError:  # pragma: no cover - Standardfall ohne SQLCipher
    sqlcipher3 = None
    SQLCIPHER_AVAILABLE = False


# ---------------------------------------------------------------------------
# Konstanten
# ---------------------------------------------------------------------------

STATUS_OPTIONS = [
    "Beworben",
    "Interview",
    "Angebot",
    "Abgelehnt",
    "Erledigt/Archiviert",
]

# Status-Werte, die eine Bewerbung als "abgeschlossen" markieren.
# Solche Einträge werden bei der Duplikat-Prüfung ignoriert.
INACTIVE_STATUSES = {"Abgelehnt", "Erledigt/Archiviert"}

DEFAULT_STATUS = "Beworben"

# Sortier-Optionen für das Kanban-Board (Anzeige-Label -> SQL-ORDER-BY-Klausel).
SORT_OPTIONS: dict[str, str] = {
    "Bewerbungsdatum (neueste zuerst)": "bewerbungsdatum DESC",
    "Bewerbungsdatum (älteste zuerst)": "bewerbungsdatum ASC",
    "Follow-up (dringend zuerst)": (
        "CASE WHEN followup_datum IS NULL OR followup_datum = '' THEN 1 ELSE 0 END ASC, "
        "followup_datum ASC"
    ),
    "Firma (A–Z)": "firmenname ASC",
}
DEFAULT_SORT = "Bewerbungsdatum (neueste zuerst)"

# Export-Spalten (Reihenfolge + Kopfzeilen für CSV/Excel-Export)
EXPORT_COLUMNS = [
    ("firmenname", "Firma"),
    ("rollenbezeichnung", "Rolle"),
    ("status", "Status"),
    ("bewerbungsdatum", "Bewerbungsdatum"),
    ("joblink", "Job-Link"),
    ("followup_datum", "Follow-up-Datum"),
    ("anhang_pfad", "Anhang"),
    ("anmerkungen", "Anmerkungen"),
]


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class DuplicateError(Exception):
    """Wird ausgelöst, wenn bereits eine aktive Bewerbung für dieselbe
    Firma/Rolle-Kombination existiert (Status nicht 'Abgelehnt' oder
    'Erledigt/Archiviert')."""
    pass


class ApplicationNotFoundError(Exception):
    """Wird ausgelöst, wenn eine referenzierte Bewerbung nicht existiert."""
    pass


# ---------------------------------------------------------------------------
# Kernklasse
# ---------------------------------------------------------------------------

class ApplicationManager:
    """Kapselt sämtliche Datenbankinteraktionen für Bewerbungen und deren
    Interaktions-Historie. Jede öffentliche Methode öffnet ihre eigene
    Connection, damit die Klasse problemlos aus verschiedenen Qt-Slots
    heraus aufgerufen werden kann.

    Args:
        db_path: Pfad zur SQLite-Datei. Über mehrere Pfade lassen sich
            unabhängige Profile führen (z. B. verschiedene Bewerbungsrunden
            oder Jahre) - siehe ProfileManager in main_window.py.
        encryption_key: Optionales Passwort. Wird nur verwendet, wenn
            `sqlcipher3` installiert ist (SQLCIPHER_AVAILABLE=True);
            andernfalls wird unverschlüsseltes sqlite3 genutzt.
    """

    def __init__(
        self,
        db_path: str = "career_tracker.db",
        encryption_key: Optional[str] = None,
    ) -> None:
        self.db_path = db_path
        self.encryption_key = encryption_key
        self.use_encryption = bool(encryption_key) and SQLCIPHER_AVAILABLE
        self._init_db()

    # -- Verbindungs-Helfer --------------------------------------------------

    def _get_connection(self):
        if self.use_encryption:
            conn = sqlcipher3.connect(self.db_path)  # type: ignore[union-attr]
            conn.execute(f"PRAGMA key = '{self.encryption_key}'")
        else:
            conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS Bewerbung (
                    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                    firmenname          TEXT NOT NULL,
                    rollenbezeichnung   TEXT NOT NULL,
                    status              TEXT NOT NULL DEFAULT 'Beworben',
                    bewerbungsdatum     TEXT NOT NULL,
                    joblink             TEXT,
                    followup_datum      TEXT,
                    anmerkungen         TEXT,
                    anhang_pfad         TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS Interaktion (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    bewerbung_id    INTEGER NOT NULL,
                    datum           TEXT NOT NULL,
                    art             TEXT NOT NULL,
                    details         TEXT,
                    FOREIGN KEY (bewerbung_id) REFERENCES Bewerbung(id)
                        ON DELETE CASCADE
                )
                """
            )
            # Migrations-Sicherheitsnetz: falls eine ältere DB-Datei ohne
            # anhang_pfad existiert, Spalte nachträglich ergänzen.
            existing_cols = {
                row["name"] for row in conn.execute("PRAGMA table_info(Bewerbung)")
            }
            if "anhang_pfad" not in existing_cols:
                conn.execute("ALTER TABLE Bewerbung ADD COLUMN anhang_pfad TEXT")
            conn.commit()

    # -- Validierung ----------------------------------------------------------

    def _validate_duplicate(
        self,
        firma: str,
        rolle: str,
        conn=None,
        exclude_id: Optional[int] = None,
    ) -> None:
        """Prüft, ob bereits eine AKTIVE Bewerbung (Status nicht 'Abgelehnt'
        oder 'Erledigt/Archiviert') mit derselben Firma+Rolle existiert.
        Wirft DuplicateError, falls ja. Läuft innerhalb einer laufenden
        Transaktion, falls `conn` übergeben wird (z. B. aus add_application)."""
        own_conn = conn is None
        if own_conn:
            conn = self._get_connection()
        try:
            query = (
                "SELECT id, status FROM Bewerbung "
                "WHERE lower(firmenname) = lower(?) "
                "AND lower(rollenbezeichnung) = lower(?)"
            )
            params: list = [firma.strip(), rolle.strip()]
            if exclude_id is not None:
                query += " AND id != ?"
                params.append(exclude_id)

            rows = conn.execute(query, params).fetchall()
            for row in rows:
                if row["status"] not in INACTIVE_STATUSES:
                    raise DuplicateError(
                        f"Es existiert bereits eine aktive Bewerbung für "
                        f"'{firma}' – '{rolle}' (Status: {row['status']})."
                    )
        finally:
            if own_conn:
                conn.close()

    # -- CRUD: Bewerbungen ------------------------------------------------

    def add_application(self, data: dict) -> int:
        """Erstellt einen neuen Bewerbungs-Eintrag. Nutzt zwingend
        `_validate_duplicate` innerhalb derselben Transaktion, bevor
        committed wird. Gibt die neue ID zurück."""
        conn = self._get_connection()
        try:
            conn.execute("BEGIN")
            self._validate_duplicate(
                data["firmenname"], data["rollenbezeichnung"], conn=conn
            )
            cursor = conn.execute(
                """
                INSERT INTO Bewerbung
                    (firmenname, rollenbezeichnung, status, bewerbungsdatum,
                     joblink, followup_datum, anmerkungen, anhang_pfad)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data["firmenname"].strip(),
                    data["rollenbezeichnung"].strip(),
                    data.get("status", DEFAULT_STATUS),
                    data.get("bewerbungsdatum") or date.today().isoformat(),
                    data.get("joblink", ""),
                    data.get("followup_datum", ""),
                    data.get("anmerkungen", ""),
                    data.get("anhang_pfad", ""),
                ),
            )
            app_id = cursor.lastrowid
            conn.execute(
                "INSERT INTO Interaktion (bewerbung_id, datum, art, details) "
                "VALUES (?, ?, ?, ?)",
                (app_id, datetime.now().isoformat(timespec="seconds"),
                 "Erstellt", "Bewerbung angelegt."),
            )
            conn.commit()
            return app_id
        except DuplicateError:
            conn.rollback()
            raise
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_all_applications(self, sort_by: str = DEFAULT_SORT) -> list[dict]:
        """Holt alle Bewerbungsdaten für die GUI (Kanban-Board).

        Args:
            sort_by: Anzeige-Label aus SORT_OPTIONS. Steuert die Reihenfolge
                der Karten innerhalb jeder Kanban-Spalte (z. B. nach
                Bewerbungsdatum oder Follow-up-Dringlichkeit statt nur `id`).
        """
        order_clause = SORT_OPTIONS.get(sort_by, SORT_OPTIONS[DEFAULT_SORT])
        with self._get_connection() as conn:
            rows = conn.execute(
                f"SELECT * FROM Bewerbung ORDER BY {order_clause}"
            ).fetchall()
            return [dict(r) for r in rows]

    def get_application(self, app_id: int) -> dict:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM Bewerbung WHERE id = ?", (app_id,)
            ).fetchone()
            if row is None:
                raise ApplicationNotFoundError(
                    f"Bewerbung mit ID {app_id} nicht gefunden."
                )
            return dict(row)

    def update_application(self, app_id: int, data: dict) -> None:
        """Aktualisiert Stammdaten einer Bewerbung (nicht den Status;
        dafür siehe update_status). Prüft erneut auf Duplikate, falls
        Firma/Rolle geändert wurden."""
        conn = self._get_connection()
        try:
            conn.execute("BEGIN")
            self._validate_duplicate(
                data["firmenname"], data["rollenbezeichnung"],
                conn=conn, exclude_id=app_id,
            )
            conn.execute(
                """
                UPDATE Bewerbung
                SET firmenname = ?, rollenbezeichnung = ?, bewerbungsdatum = ?,
                    joblink = ?, followup_datum = ?, anmerkungen = ?, anhang_pfad = ?
                WHERE id = ?
                """,
                (
                    data["firmenname"].strip(),
                    data["rollenbezeichnung"].strip(),
                    data.get("bewerbungsdatum", ""),
                    data.get("joblink", ""),
                    data.get("followup_datum", ""),
                    data.get("anmerkungen", ""),
                    data.get("anhang_pfad", ""),
                    app_id,
                ),
            )
            conn.commit()
        except DuplicateError:
            conn.rollback()
            raise
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def update_status(self, app_id: int, new_status: str) -> None:
        """Ändert den Status einer Bewerbung und protokolliert dies als
        Interaktion (z. B. für Drag & Drop im Kanban-Board)."""
        if new_status not in STATUS_OPTIONS:
            raise ValueError(f"Ungültiger Status: {new_status}")

        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT status FROM Bewerbung WHERE id = ?", (app_id,)
            ).fetchone()
            if row is None:
                raise ApplicationNotFoundError(
                    f"Bewerbung mit ID {app_id} nicht gefunden."
                )
            old_status = row["status"]
            if old_status == new_status:
                return

            conn.execute(
                "UPDATE Bewerbung SET status = ? WHERE id = ?",
                (new_status, app_id),
            )
            conn.execute(
                "INSERT INTO Interaktion (bewerbung_id, datum, art, details) "
                "VALUES (?, ?, ?, ?)",
                (
                    app_id,
                    datetime.now().isoformat(timespec="seconds"),
                    "Statusänderung",
                    f"{old_status} → {new_status}",
                ),
            )
            conn.commit()

    def delete_application(self, app_id: int) -> None:
        with self._get_connection() as conn:
            conn.execute("DELETE FROM Interaktion WHERE bewerbung_id = ?", (app_id,))
            conn.execute("DELETE FROM Bewerbung WHERE id = ?", (app_id,))
            conn.commit()

    # -- Anhänge/Dokumente ----------------------------------------------------

    def set_attachment(self, app_id: int, file_path: str) -> None:
        """Hinterlegt einen Dateipfad (Anschreiben/CV-Version) für eine
        Bewerbung und protokolliert dies als Interaktion. `file_path` wird
        unverändert gespeichert (keine Kopie der Datei) - CTAM speichert
        nur die Referenz, nicht den Dateiinhalt."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT id FROM Bewerbung WHERE id = ?", (app_id,)
            ).fetchone()
            if row is None:
                raise ApplicationNotFoundError(
                    f"Bewerbung mit ID {app_id} nicht gefunden."
                )
            conn.execute(
                "UPDATE Bewerbung SET anhang_pfad = ? WHERE id = ?",
                (file_path, app_id),
            )
            conn.execute(
                "INSERT INTO Interaktion (bewerbung_id, datum, art, details) "
                "VALUES (?, ?, ?, ?)",
                (app_id, datetime.now().isoformat(timespec="seconds"),
                 "Anhang", f"Datei hinterlegt: {Path(file_path).name}"),
            )
            conn.commit()

    def clear_attachment(self, app_id: int) -> None:
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE Bewerbung SET anhang_pfad = '' WHERE id = ?", (app_id,)
            )
            conn.commit()

    # -- Follow-ups ---------------------------------------------------------

    def get_followups_due(self, days: int = 7) -> list[dict]:
        """Filtert alle Einträge, deren followup_datum innerhalb der
        nächsten N Tage liegt (inkl. bereits überfälliger Follow-ups)."""
        cutoff = (date.today() + timedelta(days=days)).isoformat()
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM Bewerbung
                WHERE followup_datum IS NOT NULL
                  AND followup_datum != ''
                  AND followup_datum <= ?
                  AND status NOT IN (?, ?)
                ORDER BY followup_datum ASC
                """,
                (cutoff, *INACTIVE_STATUSES),
            ).fetchall()
            return [dict(r) for r in rows]

    # -- Interaktions-Log -----------------------------------------------------

    def get_interactions(self, app_id: int) -> list[dict]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM Interaktion WHERE bewerbung_id = ? "
                "ORDER BY datum DESC",
                (app_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def add_note(self, app_id: int, note_text: str) -> None:
        """Fügt eine manuelle Notiz als Interaktion hinzu (z. B. Telefonat,
        E-Mail-Verlauf) ohne die Anmerkungen des Stammdatensatzes zu ändern."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT id FROM Bewerbung WHERE id = ?", (app_id,)
            ).fetchone()
            if row is None:
                raise ApplicationNotFoundError(
                    f"Bewerbung mit ID {app_id} nicht gefunden."
                )
            conn.execute(
                "INSERT INTO Interaktion (bewerbung_id, datum, art, details) "
                "VALUES (?, ?, ?, ?)",
                (app_id, datetime.now().isoformat(timespec="seconds"),
                 "Notiz", note_text),
            )
            conn.commit()

    # -- Export ---------------------------------------------------------------

    def export_to_csv(self, target_path: str) -> int:
        """Exportiert alle Bewerbungen als CSV-Datei (z. B. für die
        Steuererklärung oder Nachweise beim Jobcenter). Nutzt Semikolon als
        Trennzeichen, da dies von Excel in deutscher Locale automatisch
        korrekt in Spalten interpretiert wird. Gibt die Anzahl der
        exportierten Zeilen zurück."""
        applications = self.get_all_applications()
        with open(target_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow([label for _, label in EXPORT_COLUMNS])
            for app in applications:
                writer.writerow([app.get(col, "") or "" for col, _ in EXPORT_COLUMNS])
        return len(applications)

    # -- Statistik --------------------------------------------------------

    def get_applications_per_month(self) -> list[tuple[str, int]]:
        """Anzahl Bewerbungen je Monat (Format 'YYYY-MM'), aufsteigend
        sortiert. Grundlage für das Statistik-Dashboard."""
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT substr(bewerbungsdatum, 1, 7) AS monat, COUNT(*) AS anzahl
                FROM Bewerbung
                WHERE bewerbungsdatum IS NOT NULL AND bewerbungsdatum != ''
                GROUP BY monat
                ORDER BY monat ASC
                """
            ).fetchall()
            return [(row["monat"], row["anzahl"]) for row in rows]

    def get_status_distribution(self) -> dict[str, int]:
        """Anzahl Bewerbungen je Status (für Kreis-/Balkendiagramm)."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) AS anzahl FROM Bewerbung GROUP BY status"
            ).fetchall()
            counts = {status: 0 for status in STATUS_OPTIONS}
            for row in rows:
                counts[row["status"]] = row["anzahl"]
            return counts

    def get_conversion_rates(self) -> dict:
        """Berechnet einfache Erfolgsquoten:
            - Interview-Quote: Anteil aller Bewerbungen, die mindestens
              einmal den Status 'Interview' oder weiter erreicht haben.
            - Angebots-Quote (Interview -> Angebot): Anteil der Bewerbungen
              im Interview-Prozess, die zu einem Angebot führten.

        Basierend auf dem Interaktions-Log (Statusänderungs-Einträgen),
        nicht nur dem aktuellen Status - so zählt auch eine Bewerbung, die
        später wieder abgelehnt wurde, korrekt als "hatte ein Interview".
        """
        with self._get_connection() as conn:
            total = conn.execute("SELECT COUNT(*) AS c FROM Bewerbung").fetchone()["c"]
            if total == 0:
                return {
                    "gesamt": 0,
                    "hatte_interview": 0,
                    "interview_quote": 0.0,
                    "hatte_angebot": 0,
                    "angebot_quote_von_interview": 0.0,
                }

            reached_interview = conn.execute(
                """
                SELECT COUNT(DISTINCT bewerbung_id) AS c FROM Interaktion
                WHERE (art = 'Statusänderung' AND details LIKE '%→ Interview%')
                   OR (art = 'Statusänderung' AND details LIKE '%→ Angebot%')
                """
            ).fetchone()["c"]

            reached_offer = conn.execute(
                """
                SELECT COUNT(DISTINCT bewerbung_id) AS c FROM Interaktion
                WHERE art = 'Statusänderung' AND details LIKE '%→ Angebot%'
                """
            ).fetchone()["c"]

            interview_quote = reached_interview / total if total else 0.0
            angebot_quote = (
                reached_offer / reached_interview if reached_interview else 0.0
            )

            return {
                "gesamt": total,
                "hatte_interview": reached_interview,
                "interview_quote": round(interview_quote * 100, 1),
                "hatte_angebot": reached_offer,
                "angebot_quote_von_interview": round(angebot_quote * 100, 1),
            }
