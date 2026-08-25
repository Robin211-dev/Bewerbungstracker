# Career Tracker & Application Manager (CTAM)

Eine **grundsätzlich offline** laufende Desktop-Anwendung zur Verwaltung von
Bewerbungen mit Duplikat-Prävention, Kanban-Board, Follow-up-Tracking,
Anhang-Verwaltung, CSV-Export, Statistik-Dashboard und optionalem
Job-Link-Import.

> **Hinweis zur Offline-Architektur:** CTAM funktioniert vollständig ohne
> Internetverbindung. Einzige Ausnahme ist der *optionale* Job-Import
> (`job_import.py`) – der stellt nur dann eine Verbindung her, wenn
> aktiv auf „⬇ Aus Link importieren“ geklickt wird. Ohne diesen Klick
> bleibt die Anwendung zu 100 % offline.

- **Sprache:** Python 3
- **GUI:** PyQt6
- **Datenbank:** SQLite3 (Standardbibliothek). Optional verschlüsselt via
  `sqlcipher3`, falls installiert.
- **Statistik-Charts:** matplotlib (eingebettet in Qt)
- **Job-Import (optional):** requests + BeautifulSoup

## Installation

```bash
pip install -r requirements.txt
```

## Starten

```bash
python main.py
```

## Projektstruktur

| Datei                 | Zweck                                                                 |
|------------------------|------------------------------------------------------------------------|
| `database_manager.py` | `ApplicationManager` – SQLite-Zugriff, Geschäftslogik, `DuplicateError`, Sortierung, CSV-Export, Statistik-Abfragen |
| `theme.py`              | Zentrale Farb-Paletten (Hell/Dunkel) + Stylesheet-Bausteine            |
| `widgets.py`           | `ApplicationCardWidget`, `KanbanColumn` (inkl. Kontextmenü), `DetailPanel` (inkl. Anhang) |
| `profile_manager.py`   | Verwaltung mehrerer unabhängiger `.db`-Profile (z. B. je Bewerbungsjahr) |
| `stats_dialog.py`       | Statistik-Dashboard (separates Fenster mit matplotlib-Charts)          |
| `job_import.py`         | **Optional.** Lädt eine Stellenausschreibung per URL und extrahiert Firma/Rolle/Standort per Text-Heuristik |
| `main_window.py`       | `MainWindow`, `ApplicationFormDialog` – Layout, Shortcuts, Event-Steuerung |
| `main.py`               | Einstiegspunkt (`QApplication`)                                        |

## Funktionsübersicht

### Kernfunktionen
- **Kanban-Board** mit einer Spalte je Status (Beworben, Interview, Angebot,
  Abgelehnt, Erledigt/Archiviert). Spalten-Header zeigen die Anzahl der
  Karten an (z. B. „Interview (3)“).
- **Duplikat-Prävention:** Beim Anlegen/Bearbeiten wird geprüft, ob bereits
  ein *aktiver* Eintrag (Status ≠ „Abgelehnt“ / „Erledigt/Archiviert“) für
  dieselbe Firma+Rolle existiert. Erscheint als klares, nicht-blockierendes
  Warnfenster; das Formular bleibt geöffnet.
- **Follow-up-Erinnerungen:** Banner + Sidebar-Liste für fällige Follow-ups
  (nächste 7 Tage).

### Sortierung
Über die Sidebar wählbar: Bewerbungsdatum (neueste/älteste zuerst),
Follow-up-Dringlichkeit (fehlende Follow-ups zuletzt) oder Firma A–Z.
Die Sortierung wirkt innerhalb jeder Kanban-Spalte.

### Kontextmenü & Shortcuts
- **Rechtsklick auf eine Karte** → Bearbeiten/Löschen ohne das Detail-Panel
  zu öffnen.
- **Strg+N** – neue Bewerbung anlegen.
- **Strg+E** – CSV-Export starten.
- **Strg+F** – Suchfeld fokussieren.
- **Entf** – löscht die aktuell ausgewählte Karte in der fokussierten Spalte
  (mit Sicherheitsabfrage).

### Export
„⬇ Export“-Button bzw. Strg+E exportiert alle Bewerbungen als
Semikolon-getrennte CSV-Datei (Excel-kompatibel, deutsche Locale) – z. B.
für die Steuererklärung oder Nachweise beim Jobcenter.

### Anhänge/Dokumente
Im Detail-Panel lässt sich pro Bewerbung ein Dateipfad (Anschreiben/CV-
Version) hinterlegen. CTAM speichert nur die **Referenz** auf die Datei
(`anhang_pfad`-Spalte), nicht den Dateiinhalt selbst. Karten mit Anhang
zeigen ein 📎-Symbol.

### Statistik-Dashboard
„Statistik“ öffnet ein separates Fenster mit:
- Bewerbungen pro Monat (Balkendiagramm)
- Status-Verteilung (Balkendiagramm)
- Kennzahlen: Interview-Quote, Angebots-Quote (Interview → Angebot)

Die Berechnung basiert auf dem Interaktions-Log, nicht nur dem aktuellen
Status – eine Bewerbung, die später wieder abgelehnt wurde, zählt weiterhin
korrekt als „hatte ein Interview“.

### Mehrere Profile
Über die Sidebar lassen sich mehrere unabhängige Profile (je eine eigene
`.db`-Datei) anlegen und wechseln – z. B. „Bewerbung 2026“, „Werkstudent“.
Konfiguration liegt in `~/.ctam/profiles.json`. Das zuletzt aktive Profil
wird beim nächsten Start automatisch geöffnet.

### Theme-Umschalter
Der „☀ Hell / 🌙 Dunkel“-Button in der Sidebar wechselt zur Laufzeit
zwischen den in `theme.py` definierten Paletten, ohne Neustart. Alle Farben
sind zentral in `theme.py` gepflegt.

### Job-Import aus Link
Im Formular „Neue Bewerbung“ / „Bearbeiten“ gibt es neben dem Job-Link-Feld
einen Button „⬇ Aus Link importieren“.

Einschränkungen:
- Funktioniert nur bei Seiten, deren Inhalt direkt im HTML steht. 
- Manche Plattformen blockieren automatisierte Abrufe oder
  verlangen ein Login -> Import schlägt fehl.

**Interaktion**: `id, bewerbung_id (FK), datum, art, details`
