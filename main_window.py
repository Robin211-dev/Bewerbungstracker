"""
main_window.py
---------------
Das Hauptfenster der CTAM-Anwendung (PyQt6). Verbindet die GUI mit der
ApplicationManager-Geschäftslogik über Signal-/Slot-Verbindungen.

Layout:
    - Sidebar (links):   Filter (Suche, Status-Checkboxen), Sortierung,
                          Profil-Auswahl, Theme-Umschalter, "Neue Bewerbung".
    - Kanban-Board (Mitte): Eine Spalte je Status, Karten per Drag & Drop
      verschiebbar, Rechtsklick-Kontextmenü pro Karte.
    - Detail-Panel (rechts): Kontextuell, zeigt Details, Anhang und Verlauf
      der ausgewählten Bewerbung.

Zusätzliche Features:
    - Tastatur-Shortcuts (Strg+N neue Bewerbung, Entf löscht ausgewählte
      Karte, Strg+E Export, Strg+F Suche fokussieren).
    - CSV-Export der gesamten Bewerbungsliste.
    - Statistik-Dashboard (separates Fenster, siehe stats_dialog.py).
    - Mehrere Profile (unabhängige .db-Dateien, siehe profile_manager.py).
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, QDate, QThread, pyqtSignal
from PyQt6.QtGui import QAction, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from database_manager import (
    ApplicationManager,
    ApplicationNotFoundError,
    DEFAULT_SORT,
    DuplicateError,
    SORT_OPTIONS,
    STATUS_OPTIONS,
)
from job_import import JobImportError, JobImportResult, import_from_url
from profile_manager import ProfileManager
from stats_dialog import StatsDialog
from widgets import DetailPanel, KanbanColumn
import theme as th


# ---------------------------------------------------------------------------
# Hintergrund-Worker für den Job-Import (verhindert GUI-Freeze während des
# HTTP-Requests). Läuft nur, wenn der Nutzer aktiv "Aus Link importieren"
# klickt - siehe job_import.py für Details zur Netzwerk-Nutzung.
# ---------------------------------------------------------------------------

class JobImportWorker(QThread):
    succeeded = pyqtSignal(object)  # JobImportResult
    failed = pyqtSignal(str)

    def __init__(self, url: str, parent=None) -> None:
        super().__init__(parent)
        self.url = url

    def run(self) -> None:
        try:
            result = import_from_url(self.url)
            self.succeeded.emit(result)
        except JobImportError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001 - unerwartete Fehler abfangen
            self.failed.emit(f"Unerwarteter Fehler beim Import: {exc}")


# ---------------------------------------------------------------------------
# Dialog: Neue Bewerbung / Bewerbung bearbeiten
# ---------------------------------------------------------------------------

class ApplicationFormDialog(QDialog):
    """Formular zum Anlegen oder Bearbeiten einer Bewerbung."""

    def __init__(
        self,
        parent=None,
        existing_data: dict | None = None,
        palette: th.Palette | None = None,
    ) -> None:
        super().__init__(parent)
        self.existing_data = existing_data
        self._import_worker: JobImportWorker | None = None
        self.palette_ = palette or th.get_palette(th.ThemeName.DARK)
        self.setWindowTitle(
            "Bewerbung bearbeiten" if existing_data else "Neue Bewerbung"
        )
        self.setMinimumWidth(420)
        self._build_ui()

    def _build_ui(self) -> None:
        p = self.palette_
        self.setStyleSheet(f"""
            QDialog {{ background:{p.bg_root}; }}
            QLabel {{ color:{p.text_primary}; background:transparent; }}
            QLineEdit, QDateEdit, QTextEdit {{
                background:{p.bg_input}; color:{p.text_primary};
                border:1px solid {p.border_input}; border-radius:4px; padding:4px 6px;
            }}
            QCheckBox {{ color:{p.text_primary}; background:transparent; }}
            QDateEdit::drop-down {{ border:none; }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)
        form = QFormLayout()
        form.setSpacing(10)

        self.firma_input = QLineEdit()
        self.rolle_input = QLineEdit()
        self.datum_input = QDateEdit()
        self.datum_input.setCalendarPopup(True)
        self.datum_input.setDate(QDate.currentDate())

        # -- Job-Link + Import-Button ---------------------------------
        joblink_row = QHBoxLayout()
        joblink_row.setSpacing(8)
        self.joblink_input = QLineEdit()
        self.joblink_input.setPlaceholderText("https://...")
        joblink_row.addWidget(self.joblink_input, stretch=1)
        self.import_btn = QPushButton("⬇ Aus Link importieren")
        self.import_btn.setStyleSheet(th.secondary_button_stylesheet(p))
        self.import_btn.setToolTip(
            "Lädt die Stellenausschreibung und versucht, Firma und Rolle "
            "automatisch zu erkennen. Benötigt eine Internetverbindung – "
            "die einzige Stelle in CTAM, die das tut."
        )
        self.import_btn.clicked.connect(self._on_import_clicked)
        joblink_row.addWidget(self.import_btn)

        self.import_status_label = QLabel("")
        self.import_status_label.setStyleSheet(
            f"color:{p.text_muted}; font-size:11px; padding:2px 4px;"
        )
        self.import_status_label.setWordWrap(True)
        self.import_status_label.setVisible(False)

        self.followup_input = QDateEdit()
        self.followup_input.setCalendarPopup(True)
        self.followup_input.setSpecialValueText(" ")
        self.followup_input.setDate(QDate.currentDate())
        self.followup_checkbox = QCheckBox("Follow-up geplant")
        self.followup_checkbox.toggled.connect(self.followup_input.setEnabled)
        self.followup_input.setEnabled(False)
        self.anmerkungen_input = QTextEdit()
        self.anmerkungen_input.setFixedHeight(70)

        form.addRow("Firma*:", self.firma_input)
        form.addRow("Rolle*:", self.rolle_input)
        form.addRow("Bewerbungsdatum:", self.datum_input)
        form.addRow("Job-Link:", joblink_row)
        form.addRow("", self.import_status_label)
        form.addRow("", self.followup_checkbox)
        form.addRow("Follow-up-Datum:", self.followup_input)
        form.addRow("Anmerkungen:", self.anmerkungen_input)

        layout.addLayout(form)

        if self.existing_data:
            self.firma_input.setText(self.existing_data.get("firmenname", ""))
            self.rolle_input.setText(self.existing_data.get("rollenbezeichnung", ""))
            if self.existing_data.get("bewerbungsdatum"):
                self.datum_input.setDate(
                    QDate.fromString(self.existing_data["bewerbungsdatum"], "yyyy-MM-dd")
                )
            self.joblink_input.setText(self.existing_data.get("joblink", "") or "")
            fu = self.existing_data.get("followup_datum")
            if fu:
                self.followup_checkbox.setChecked(True)
                self.followup_input.setDate(QDate.fromString(fu, "yyyy-MM-dd"))
            self.anmerkungen_input.setPlainText(
                self.existing_data.get("anmerkungen", "") or ""
            )

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.setStyleSheet(f"""
            QPushButton {{
                background:{p.bg_input}; color:{p.text_primary};
                border:1px solid {p.border_input}; border-radius:5px;
                padding:6px 16px; min-width:70px;
            }}
            QPushButton:hover {{ background:{p.bg_history_entry}; }}
            QPushButton:default {{
                background:{p.accent}; color:{p.text_on_accent}; border:none;
            }}
            QPushButton:default:hover {{ background:{p.accent_hover}; }}
        """)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # -- Job-Import ---------------------------------------------------------

    def _on_import_clicked(self) -> None:
        url = self.joblink_input.text().strip()
        if not url:
            QMessageBox.information(
                self, "Job-Link fehlt",
                "Bitte zuerst einen Link zur Stellenausschreibung eintragen."
            )
            return

        self.import_btn.setEnabled(False)
        self.import_btn.setText("Lädt...")
        self.import_status_label.setVisible(True)
        self.import_status_label.setText("Rufe Stellenausschreibung ab...")

        self._import_worker = JobImportWorker(url, self)
        self._import_worker.succeeded.connect(self._on_import_succeeded)
        self._import_worker.failed.connect(self._on_import_failed)
        self._import_worker.finished.connect(self._on_import_finished)
        self._import_worker.start()

    def _on_import_succeeded(self, result: JobImportResult) -> None:
        applied = []
        if result.firmenname and not self.firma_input.text().strip():
            self.firma_input.setText(result.firmenname)
            applied.append("Firma")
        if result.rollenbezeichnung and not self.rolle_input.text().strip():
            self.rolle_input.setText(result.rollenbezeichnung)
            applied.append("Rolle")
        if result.standort:
            current_notes = self.anmerkungen_input.toPlainText().strip()
            location_note = f"Standort (importiert): {result.standort}"
            if location_note not in current_notes:
                new_notes = (
                    f"{current_notes}\n{location_note}".strip()
                    if current_notes else location_note
                )
                self.anmerkungen_input.setPlainText(new_notes)
                applied.append("Standort (als Notiz)")

        message_parts = []
        if applied:
            message_parts.append(f"Übernommen: {', '.join(applied)}.")
        else:
            message_parts.append(
                "Felder waren bereits ausgefüllt - nichts überschrieben."
            )
        if result.confidence_notes:
            message_parts.append(" ".join(result.confidence_notes))
        message_parts.append(
            "Bitte alle Angaben vor dem Speichern prüfen."
        )
        self.import_status_label.setText(" ".join(message_parts))

    def _on_import_failed(self, error_message: str) -> None:
        self.import_status_label.setText(f"Import fehlgeschlagen: {error_message}")

    def _on_import_finished(self) -> None:
        self.import_btn.setEnabled(True)
        self.import_btn.setText("⬇ Aus Link importieren")
        self._import_worker = None

    def _on_accept(self) -> None:
        if not self.firma_input.text().strip() or not self.rolle_input.text().strip():
            QMessageBox.warning(
                self, "Fehlende Angaben",
                "Bitte Firma und Rolle ausfüllen."
            )
            return
        self.accept()

    def get_data(self) -> dict:
        data = {
            "firmenname": self.firma_input.text().strip(),
            "rollenbezeichnung": self.rolle_input.text().strip(),
            "bewerbungsdatum": self.datum_input.date().toString("yyyy-MM-dd"),
            "joblink": self.joblink_input.text().strip(),
            "followup_datum": (
                self.followup_input.date().toString("yyyy-MM-dd")
                if self.followup_checkbox.isChecked() else ""
            ),
            "anmerkungen": self.anmerkungen_input.toPlainText().strip(),
        }
        # Anhang-Pfad bleibt beim Bearbeiten erhalten (wird separat über das
        # Detail-Panel gesetzt/entfernt, nicht über dieses Formular).
        if self.existing_data:
            data["anhang_pfad"] = self.existing_data.get("anhang_pfad", "")
        return data


# ---------------------------------------------------------------------------
# MainWindow
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.profile_manager = ProfileManager()
        active_profile = self.profile_manager.get_last_active()
        db_path = self.profile_manager.get_path(active_profile)

        self.manager = ApplicationManager(db_path=db_path)
        self.current_theme = th.ThemeName.DARK
        self.palette_ = th.get_palette(self.current_theme)

        self.setWindowTitle(
            f"Career Tracker & Application Manager (CTAM) – Profil: {active_profile}"
        )
        self.resize(1320, 820)

        self.search_text = ""
        self.active_status_filters: set[str] = set(STATUS_OPTIONS)
        self.current_sort = DEFAULT_SORT

        self._build_ui()
        self._connect_signals()
        self._setup_shortcuts()
        self.refresh_board()
        self.check_followups()  # Beim Start: fällige Follow-ups anzeigen

    # -- UI-Aufbau ------------------------------------------------------

    def _build_ui(self) -> None:
        p = self.palette_
        central = QWidget()
        central.setStyleSheet(th.central_stylesheet(p))
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # -- Top-Bar: Follow-up-Banner + Aktionen ----------------------
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(12, 8, 12, 8)
        self.followup_banner = QLabel("")
        self.followup_banner.setStyleSheet(
            f"background:{p.warning_bg}; color:{p.warning_text}; "
            f"padding:6px 10px; border-radius:6px;"
        )
        self.followup_banner.setVisible(False)
        self.followup_banner.setWordWrap(True)
        top_bar.addWidget(self.followup_banner, stretch=1)

        self.export_btn = QPushButton("⬇ Export")
        self.export_btn.setStyleSheet(th.secondary_button_stylesheet(p))
        self.export_btn.setToolTip("Bewerbungsliste als CSV exportieren (Strg+E)")
        top_bar.addWidget(self.export_btn)

        self.stats_btn = QPushButton("📊 Statistik")
        self.stats_btn.setStyleSheet(th.secondary_button_stylesheet(p))
        top_bar.addWidget(self.stats_btn)

        self.new_app_btn = QPushButton("+ Neue Bewerbung")
        self.new_app_btn.setStyleSheet(th.primary_button_stylesheet(p))
        self.new_app_btn.setToolTip("Neue Bewerbung anlegen (Strg+N)")
        top_bar.addWidget(self.new_app_btn)

        top_bar_widget = QWidget()
        top_bar_widget.setLayout(top_bar)
        top_bar_widget.setStyleSheet(th.topbar_stylesheet(p))
        root_layout.addWidget(top_bar_widget)

        # -- Hauptbereich: Sidebar | Kanban | Detail-Panel ---------------
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setStyleSheet(th.splitter_stylesheet(p))
        self.splitter.setHandleWidth(2)
        root_layout.addWidget(self.splitter, stretch=1)

        self.splitter.addWidget(self._build_sidebar())

        self.kanban_container = QWidget()
        self.kanban_container.setStyleSheet(th.kanban_area_stylesheet(p))
        self.kanban_layout = QHBoxLayout(self.kanban_container)
        self.kanban_layout.setContentsMargins(12, 12, 12, 12)
        self.kanban_layout.setSpacing(12)
        self.columns: dict[str, KanbanColumn] = {}
        self.column_headers: dict[str, QLabel] = {}
        for status in STATUS_OPTIONS:
            col_widget, list_widget, header = self._build_kanban_column(status)
            self.kanban_layout.addWidget(col_widget)
            self.columns[status] = list_widget
            self.column_headers[status] = header
        self.splitter.addWidget(self.kanban_container)

        self.detail_panel = DetailPanel(self.palette_)
        self.splitter.addWidget(self.detail_panel)

        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setStretchFactor(2, 0)
        self.splitter.setSizes([230, 760, 330])

    def _build_sidebar(self) -> QWidget:
        p = self.palette_
        sidebar = QWidget()
        sidebar.setStyleSheet(th.sidebar_stylesheet(p))
        sidebar.setMinimumWidth(210)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # -- Profil-Auswahl ------------------------------------------
        layout.addWidget(QLabel("<b>Profil</b>"))
        profile_row = QHBoxLayout()
        self.profile_combo = QComboBox()
        self.profile_combo.addItems(self.profile_manager.list_profiles().keys())
        self.profile_combo.setCurrentText(self.profile_manager.get_last_active())
        profile_row.addWidget(self.profile_combo, stretch=1)
        self.add_profile_btn = QPushButton("+")
        self.add_profile_btn.setFixedWidth(28)
        self.add_profile_btn.setToolTip("Neues Profil anlegen (eigene Datenbankdatei)")
        profile_row.addWidget(self.add_profile_btn)
        layout.addLayout(profile_row)

        # -- Theme-Umschalter ------------------------------------------
        theme_row = QHBoxLayout()
        theme_row.addWidget(QLabel("<b>Theme</b>"))
        self.theme_toggle_btn = QPushButton("☀ Hell" if self.current_theme == th.ThemeName.DARK else "🌙 Dunkel")
        self.theme_toggle_btn.setToolTip("Zwischen Hell- und Dunkel-Theme wechseln")
        theme_row.addWidget(self.theme_toggle_btn)
        layout.addLayout(theme_row)

        # -- Suche --------------------------------------------------------
        layout.addWidget(QLabel("<b>Suche</b>"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Firma oder Rolle... (Strg+F)")
        layout.addWidget(self.search_input)

        # -- Sortierung -----------------------------------------------
        layout.addWidget(QLabel("<b>Sortierung</b>"))
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(SORT_OPTIONS.keys())
        self.sort_combo.setCurrentText(DEFAULT_SORT)
        layout.addWidget(self.sort_combo)

        # -- Status-Filter --------------------------------------------
        layout.addWidget(QLabel("<b>Status-Filter</b>"))
        self.status_checkboxes: dict[str, QCheckBox] = {}
        for status in STATUS_OPTIONS:
            cb = QCheckBox(status)
            cb.setChecked(True)
            self.status_checkboxes[status] = cb
            layout.addWidget(cb)

        # -- Follow-ups -----------------------------------------------
        layout.addWidget(QLabel("<b>Nächste Aktionen</b>"))
        self.followups_list = QListWidget()
        self.followups_list.setMaximumHeight(200)
        layout.addWidget(self.followups_list)

        layout.addStretch()
        return sidebar

    def _build_kanban_column(self, status: str) -> tuple[QWidget, KanbanColumn, QLabel]:
        p = self.palette_
        container = QWidget()
        container.setMinimumWidth(220)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        header = QLabel(status)
        header.setStyleSheet(th.column_header_stylesheet(p))
        layout.addWidget(header)

        list_widget = KanbanColumn(status, p)
        layout.addWidget(list_widget, stretch=1)

        return container, list_widget, header

    # -- Signal-/Slot-Verbindungen -------------------------------------------

    def _connect_signals(self) -> None:
        self.new_app_btn.clicked.connect(self.open_new_application_dialog)
        self.export_btn.clicked.connect(self.export_applications_csv)
        self.stats_btn.clicked.connect(self.open_stats_dashboard)
        self.theme_toggle_btn.clicked.connect(self.toggle_theme)
        self.add_profile_btn.clicked.connect(self.open_add_profile_dialog)
        self.profile_combo.currentTextChanged.connect(self.switch_profile)

        self.search_input.textChanged.connect(self._on_filter_changed)
        self.sort_combo.currentTextChanged.connect(self._on_filter_changed)
        for cb in self.status_checkboxes.values():
            cb.toggled.connect(self._on_filter_changed)
        self.followups_list.itemClicked.connect(self._on_followup_item_clicked)

        for column in self.columns.values():
            column.card_dropped.connect(self.on_card_dropped)
            column.card_selected.connect(self.on_card_selected)
            column.edit_requested_ctx.connect(self.open_edit_application_dialog)
            column.delete_requested_ctx.connect(self.on_delete_requested)

        self._connect_detail_panel_signals()

    def _connect_detail_panel_signals(self) -> None:
        """Verbindet die Signale des aktuellen DetailPanel-Widgets. Wird
        sowohl beim initialen Aufbau als auch nach einem Theme-Wechsel
        aufgerufen, da das DetailPanel dabei durch eine neue Instanz
        ersetzt wird (siehe apply_theme())."""
        self.detail_panel.status_change_requested.connect(self.on_status_change_requested)
        self.detail_panel.note_added.connect(self.on_note_added)
        self.detail_panel.edit_requested.connect(self.open_edit_application_dialog)
        self.detail_panel.delete_requested.connect(self.on_delete_requested)
        self.detail_panel.attachment_set_requested.connect(self.on_attachment_set)
        self.detail_panel.attachment_cleared_requested.connect(self.on_attachment_cleared)

    def _setup_shortcuts(self) -> None:
        """Tastatur-Shortcuts auf Fensterebene. Das Entf-Löschen einer
        ausgewählten Karte ist zusätzlich direkt in KanbanColumn verdrahtet,
        damit es unabhängig vom Fokus innerhalb einer Spalte funktioniert."""
        QShortcut(QKeySequence("Ctrl+N"), self, activated=self.open_new_application_dialog)
        QShortcut(QKeySequence("Ctrl+E"), self, activated=self.export_applications_csv)
        QShortcut(QKeySequence("Ctrl+F"), self, activated=self.search_input.setFocus)

    # -- Theme ------------------------------------------------------------

    def toggle_theme(self) -> None:
        """Wechselt zwischen Hell- und Dunkel-Theme und stylt alle
        betroffenen Widgets neu, ohne die Anwendung neu zu starten."""
        self.current_theme = (
            th.ThemeName.LIGHT if self.current_theme == th.ThemeName.DARK
            else th.ThemeName.DARK
        )
        self.palette_ = th.get_palette(self.current_theme)
        self.apply_theme()

    def apply_theme(self) -> None:
        p = self.palette_
        self.centralWidget().setStyleSheet(th.central_stylesheet(p))
        self.splitter.setStyleSheet(th.splitter_stylesheet(p))
        self.kanban_container.setStyleSheet(th.kanban_area_stylesheet(p))

        for status, header in self.column_headers.items():
            header.setStyleSheet(th.column_header_stylesheet(p))
        for column in self.columns.values():
            column.apply_palette(p)

        # Sidebar und Top-Bar sowie Buttons neu stylen
        sidebar = self.splitter.widget(0)
        sidebar.setStyleSheet(th.sidebar_stylesheet(p))
        top_bar_widget = self.centralWidget().layout().itemAt(0).widget()
        top_bar_widget.setStyleSheet(th.topbar_stylesheet(p))
        self.export_btn.setStyleSheet(th.secondary_button_stylesheet(p))
        self.stats_btn.setStyleSheet(th.secondary_button_stylesheet(p))
        self.new_app_btn.setStyleSheet(th.primary_button_stylesheet(p))
        self.followup_banner.setStyleSheet(
            f"background:{p.warning_bg}; color:{p.warning_text}; "
            f"padding:6px 10px; border-radius:6px;"
        )
        self.theme_toggle_btn.setText(
            "☀ Hell" if self.current_theme == th.ThemeName.DARK else "🌙 Dunkel"
        )

        # Detail-Panel komplett neu aufbauen: die inneren Labels/Buttons
        # tragen individuelle Stylesheets (aus der alten Palette), die ein
        # bloßes Umstylen des äußeren Containers nicht erreicht. Deshalb
        # wird das Widget ersetzt statt nur umgefärbt.
        previous_app_id = self.detail_panel.current_app_id
        old_panel = self.detail_panel
        self.detail_panel = DetailPanel(p)
        self._connect_detail_panel_signals()
        self.splitter.replaceWidget(2, self.detail_panel)
        old_panel.deleteLater()

        self.refresh_board()
        if previous_app_id is not None:
            self.on_card_selected(previous_app_id)
        else:
            self.detail_panel.show_empty_state()

    # -- Profile ------------------------------------------------------------

    def open_add_profile_dialog(self) -> None:
        name, ok = QInputDialog.getText(
            self, "Neues Profil", "Profilname (z. B. 'Bewerbung 2027'):"
        )
        if not ok or not name.strip():
            return
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Datenbankdatei für neues Profil wählen",
            f"{name.strip()}.db", "SQLite-Datenbank (*.db)"
        )
        if not file_path:
            return
        self.profile_manager.add_profile(name.strip(), file_path)
        self.profile_combo.addItem(name.strip())
        self.profile_combo.setCurrentText(name.strip())

    def switch_profile(self, profile_name: str) -> None:
        if not profile_name:
            return
        db_path = self.profile_manager.get_path(profile_name)
        self.manager = ApplicationManager(db_path=db_path)
        self.profile_manager.set_last_active(profile_name)
        self.setWindowTitle(
            f"Career Tracker & Application Manager (CTAM) – Profil: {profile_name}"
        )
        self.detail_panel.show_empty_state()
        self.refresh_board()
        self.check_followups()

    # -- Workflow: Startup / Follow-ups ---------------------------------

    def check_followups(self) -> None:
        """Beim Starten der App: get_followups_due() aufrufen und
        fällige Bewerbungen prominent anzeigen (Banner + Sidebar-Liste)."""
        due = self.manager.get_followups_due(days=7)
        self.followups_list.clear()
        for app in due:
            self.followups_list.addItem(
                f"{app['firmenname']} – {app['rollenbezeichnung']} "
                f"({app['followup_datum']})"
            )
            self.followups_list.item(self.followups_list.count() - 1).setData(
                Qt.ItemDataRole.UserRole, app["id"]
            )

        if due:
            self.followup_banner.setText(
                f"🔔 {len(due)} Follow-up(s) in den nächsten 7 Tagen fällig."
            )
            self.followup_banner.setVisible(True)
        else:
            self.followup_banner.setVisible(False)

    def _on_followup_item_clicked(self, item) -> None:
        app_id = item.data(Qt.ItemDataRole.UserRole)
        if app_id is not None:
            self.on_card_selected(app_id)

    # -- Board-Refresh mit Filtern + Sortierung -------------------------------

    def _on_filter_changed(self, *_args) -> None:
        self.search_text = self.search_input.text().strip().lower()
        self.active_status_filters = {
            status for status, cb in self.status_checkboxes.items() if cb.isChecked()
        }
        self.current_sort = self.sort_combo.currentText()
        self.refresh_board()

    def refresh_board(self) -> None:
        """Lädt alle Bewerbungen neu (in der gewählten Sortierung) und
        verteilt sie auf die Kanban-Spalten, unter Berücksichtigung von
        Such- und Status-Filtern."""
        applications = self.manager.get_all_applications(sort_by=self.current_sort)

        for column in self.columns.values():
            column.clear_cards()

        counts: dict[str, int] = {status: 0 for status in STATUS_OPTIONS}
        for app in applications:
            if app["status"] not in self.active_status_filters:
                continue
            if self.search_text:
                haystack = (
                    app.get("firmenname", "") + " " + app.get("rollenbezeichnung", "")
                ).lower()
                if self.search_text not in haystack:
                    continue
            column = self.columns.get(app["status"])
            if column is not None:
                column.add_card(app)
                counts[app["status"]] += 1

        for status, header in self.column_headers.items():
            header.setText(f"{status} ({counts[status]})")

    # -- Kanban-Karten-Events -------------------------------------------------

    def on_card_dropped(self, app_id: int, new_status: str) -> None:
        """Wird ausgelöst, wenn eine Karte per Drag & Drop in eine andere
        Status-Spalte gezogen wurde -> aktualisiert das Backend."""
        try:
            self.manager.update_status(app_id, new_status)
        except ApplicationNotFoundError as exc:
            QMessageBox.warning(self, "Fehler", str(exc))
        finally:
            self.refresh_board()
            self.check_followups()

    def on_card_selected(self, app_id: int) -> None:
        """Beim Öffnen/Auswählen einer Karte: alle relevanten Daten vom
        Backend laden und im Detail-Panel anzeigen."""
        try:
            app_data = self.manager.get_application(app_id)
        except ApplicationNotFoundError:
            return
        interactions = self.manager.get_interactions(app_id)
        self.detail_panel.show_application(app_data, interactions)

    # -- Detail-Panel-Events --------------------------------------------------

    def on_status_change_requested(self, app_id: int, new_status: str) -> None:
        try:
            self.manager.update_status(app_id, new_status)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Fehler", str(exc))
        self.refresh_board()
        self.check_followups()
        self.on_card_selected(app_id)

    def on_note_added(self, app_id: int, note_text: str) -> None:
        self.manager.add_note(app_id, note_text)
        self.on_card_selected(app_id)

    def on_delete_requested(self, app_id: int) -> None:
        confirm = QMessageBox.question(
            self, "Bewerbung löschen",
            "Diese Bewerbung inkl. Verlauf wirklich unwiderruflich löschen?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self.manager.delete_application(app_id)
            if self.detail_panel.current_app_id == app_id:
                self.detail_panel.show_empty_state()
            self.refresh_board()
            self.check_followups()

    def on_attachment_set(self, app_id: int, file_path: str) -> None:
        self.manager.set_attachment(app_id, file_path)
        self.on_card_selected(app_id)
        self.refresh_board()

    def on_attachment_cleared(self, app_id: int) -> None:
        self.manager.clear_attachment(app_id)
        self.on_card_selected(app_id)
        self.refresh_board()

    # -- Formulare: Neue Bewerbung / Bearbeiten -------------------------------

    def open_new_application_dialog(self) -> None:
        dialog = ApplicationFormDialog(self, palette=self.palette_)
        while dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_data()
            try:
                self.manager.add_application(data)
                self.refresh_board()
                self.check_followups()
                return
            except DuplicateError as exc:
                # Klares, nicht-blockierendes Dialogfenster bei Duplikat-Fehler.
                # Formular bleibt geöffnet, Nutzer kann korrigieren/abbrechen.
                QMessageBox.warning(self, "Doppelte Bewerbung erkannt", str(exc))
                continue

    def open_edit_application_dialog(self, app_id: int) -> None:
        try:
            existing = self.manager.get_application(app_id)
        except ApplicationNotFoundError:
            return
        dialog = ApplicationFormDialog(self, existing_data=existing, palette=self.palette_)
        while dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_data()
            try:
                self.manager.update_application(app_id, data)
                self.refresh_board()
                self.check_followups()
                self.on_card_selected(app_id)
                return
            except DuplicateError as exc:
                QMessageBox.warning(self, "Doppelte Bewerbung erkannt", str(exc))
                continue

    # -- Export -----------------------------------------------------------

    def export_applications_csv(self) -> None:
        """Exportiert die gesamte Bewerbungsliste als CSV (z. B. für die
        Steuererklärung oder Nachweise beim Jobcenter)."""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Bewerbungen exportieren", "bewerbungen_export.csv",
            "CSV-Datei (*.csv)"
        )
        if not file_path:
            return
        count = self.manager.export_to_csv(file_path)
        QMessageBox.information(
            self, "Export abgeschlossen",
            f"{count} Bewerbung(en) wurden nach\n{file_path}\nexportiert."
        )

    # -- Statistik --------------------------------------------------------

    def open_stats_dashboard(self) -> None:
        dialog = StatsDialog(self.manager, self.palette_, self)
        dialog.exec()
