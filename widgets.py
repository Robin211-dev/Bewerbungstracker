"""
widgets.py
----------
Wiederverwendbare GUI-Bausteine für CTAM:

    - ApplicationCardWidget: Karte auf dem Kanban-Board (zeigt Firma, Rolle,
                              Datum, Status-Badge, Anhang-Indikator; klickbar).
    - KanbanColumn:          QListWidget-Subklasse für eine Status-Spalte mit
                              Drag & Drop-Unterstützung zwischen Spalten sowie
                              einem Rechtsklick-Kontextmenü pro Karte.
    - DetailPanel:           Kontextuelles Panel, das Stammdaten + die
                              Interaktions-Historie einer ausgewählten
                              Bewerbung anzeigt, inkl. Anhang-Verwaltung.

Alle Farben werden zentral aus `theme.py` bezogen, damit ein Theme-Wechsel
(Hell/Dunkel) an einer Stelle passiert (siehe MainWindow.apply_theme()).
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from database_manager import STATUS_OPTIONS
import theme as th


# ---------------------------------------------------------------------------
# ApplicationCardWidget
# ---------------------------------------------------------------------------

class ApplicationCardWidget(QFrame):
    """Zeigt eine einzelne Bewerbung als Karte auf dem Kanban-Board."""

    def __init__(
        self,
        app_data: dict,
        palette: th.Palette,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.app_data = app_data
        self.app_id = app_data["id"]
        self.palette_ = palette
        self._build_ui()

    def _build_ui(self) -> None:
        p = self.palette_
        self.setObjectName("card")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(th.card_stylesheet(p))
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        header_row = QHBoxLayout()
        firma_label = QLabel(self.app_data.get("firmenname", ""))
        # Karten sind in beiden Themes weiß (p.bg_card), daher braucht der
        # Firmenname immer einen dunklen Text - unabhängig vom aktiven Theme.
        firma_label.setStyleSheet("font-weight: 600; font-size: 13px; color:#1A1A1A;")
        firma_label.setWordWrap(True)
        header_row.addWidget(firma_label, stretch=1)

        if self.app_data.get("anhang_pfad"):
            attach_icon = QLabel("📎")
            attach_icon.setToolTip(Path(self.app_data["anhang_pfad"]).name)
            attach_icon.setStyleSheet("font-size:12px;")
            header_row.addWidget(attach_icon)
        layout.addLayout(header_row)

        rolle_label = QLabel(self.app_data.get("rollenbezeichnung", ""))
        rolle_label.setStyleSheet("color:#555555; font-size: 12px;")
        rolle_label.setWordWrap(True)
        layout.addWidget(rolle_label)

        footer = QHBoxLayout()
        datum_label = QLabel(self.app_data.get("bewerbungsdatum", ""))
        datum_label.setStyleSheet("color:#8A8F98; font-size: 11px;")
        footer.addWidget(datum_label)
        footer.addStretch()

        status = self.app_data.get("status", "")
        badge = QLabel(status)
        color = p.status_colors.get(status, "#8A8F98")
        badge.setStyleSheet(
            f"background-color:{color}; color:white; font-size:10px; "
            f"border-radius:6px; padding:2px 6px;"
        )
        footer.addWidget(badge)
        layout.addLayout(footer)

        followup = self.app_data.get("followup_datum")
        if followup:
            fu_label = QLabel(f"⏰ Follow-up: {followup}")
            fu_label.setStyleSheet("color:#C9720C; font-size: 10px;")
            layout.addWidget(fu_label)


# ---------------------------------------------------------------------------
# KanbanColumn
# ---------------------------------------------------------------------------

class KanbanColumn(QListWidget):
    """Eine Spalte des Kanban-Boards für genau einen Status. Unterstützt
    Drag & Drop zwischen Spalten (emittiert `card_dropped`), Klick zum
    Anzeigen der Details (`card_selected`) sowie ein Rechtsklick-
    Kontextmenü für schnelles Bearbeiten/Löschen ohne das Detail-Panel
    öffnen zu müssen (`edit_requested_ctx`, `delete_requested_ctx`)."""

    card_dropped = pyqtSignal(int, str)
    card_selected = pyqtSignal(int)
    edit_requested_ctx = pyqtSignal(int)
    delete_requested_ctx = pyqtSignal(int)

    def __init__(
        self,
        status_name: str,
        palette: th.Palette,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.status_name = status_name
        self.palette_ = palette
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setSpacing(8)
        self.apply_palette(palette)
        self.itemClicked.connect(self._on_item_clicked)

        # Rechtsklick-Kontextmenü
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu_requested)

        # Entf-Taste löscht die aktuell ausgewählte Karte in dieser Spalte
        delete_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Delete), self)
        delete_shortcut.activated.connect(self._on_delete_shortcut)

    # -- Styling ------------------------------------------------------------

    def apply_palette(self, palette: th.Palette) -> None:
        self.palette_ = palette
        self.setStyleSheet(th.column_list_stylesheet(palette))

    # -- Öffentliche API ------------------------------------------------

    def clear_cards(self) -> None:
        self.clear()

    def add_card(self, app_data: dict) -> None:
        item = QListWidgetItem(self)
        item.setData(Qt.ItemDataRole.UserRole, app_data["id"])
        card = ApplicationCardWidget(app_data, self.palette_)
        item.setSizeHint(card.sizeHint())
        self.addItem(item)
        self.setItemWidget(item, card)

    # -- Interne Slots ----------------------------------------------------

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        app_id = item.data(Qt.ItemDataRole.UserRole)
        if app_id is not None:
            self.card_selected.emit(app_id)

    def _on_context_menu_requested(self, pos) -> None:
        item = self.itemAt(pos)
        if item is None:
            return
        app_id = item.data(Qt.ItemDataRole.UserRole)
        if app_id is None:
            return

        menu = QMenu(self)
        edit_action = menu.addAction("Bearbeiten")
        delete_action = menu.addAction("Löschen")
        chosen = menu.exec(self.mapToGlobal(pos))
        if chosen == edit_action:
            self.edit_requested_ctx.emit(app_id)
        elif chosen == delete_action:
            self.delete_requested_ctx.emit(app_id)

    def _on_delete_shortcut(self) -> None:
        item = self.currentItem()
        if item is None:
            return
        app_id = item.data(Qt.ItemDataRole.UserRole)
        if app_id is not None:
            self.delete_requested_ctx.emit(app_id)

    # -- Drag & Drop --------------------------------------------------------

    def dropEvent(self, event) -> None:  # noqa: N802 (Qt-API)
        source = event.source()
        if isinstance(source, KanbanColumn) and source is not self:
            item = source.currentItem()
            if item is None:
                event.ignore()
                return
            app_id = item.data(Qt.ItemDataRole.UserRole)
            event.setDropAction(Qt.DropAction.MoveAction)
            event.accept()
            # Die eigentliche Datenänderung + Board-Refresh übernimmt
            # der Slot in MainWindow, der auf dieses Signal hört.
            self.card_dropped.emit(app_id, self.status_name)
        else:
            # Reihenfolge innerhalb derselben Spalte ändern - erlaubt,
            # aber ohne Backend-Auswirkung (Sortierung bleibt bewerbung-
            # datum-/dringlichkeitsbasiert, siehe SORT_OPTIONS).
            event.ignore()


# ---------------------------------------------------------------------------
# DetailPanel
# ---------------------------------------------------------------------------

class DetailPanel(QWidget):
    """Kontextuelles Panel, das die Details + Interaktions-Historie einer
    ausgewählten Bewerbung anzeigt."""

    status_change_requested = pyqtSignal(int, str)
    note_added = pyqtSignal(int, str)
    edit_requested = pyqtSignal(int)
    delete_requested = pyqtSignal(int)
    attachment_set_requested = pyqtSignal(int, str)
    attachment_cleared_requested = pyqtSignal(int)

    def __init__(self, palette: th.Palette, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.current_app_id: int | None = None
        self.current_attachment: str = ""
        self.palette_ = palette
        self.setMinimumWidth(300)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self._build_ui()
        self.show_empty_state()

    def _build_ui(self) -> None:
        p = self.palette_
        self.setStyleSheet(th.detail_panel_stylesheet(p))
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(12)

        self.empty_label = QLabel("Wähle eine Bewerbung aus, um Details zu sehen.")
        self.empty_label.setStyleSheet(f"color:{p.text_muted}; padding:4px 6px;")
        self.empty_label.setWordWrap(True)
        outer.addWidget(self.empty_label)

        self.title_label = QLabel()
        self.title_label.setStyleSheet(f"font-size:17px; font-weight:700; color:{p.text_primary}; padding:2px 6px;")
        self.title_label.setWordWrap(True)
        outer.addWidget(self.title_label)

        self.subtitle_label = QLabel()
        self.subtitle_label.setStyleSheet(f"color:{p.text_secondary}; padding:0 6px;")
        self.subtitle_label.setWordWrap(True)
        outer.addWidget(self.subtitle_label)

        self.meta_label = QLabel()
        self.meta_label.setStyleSheet(f"color:{p.text_muted}; font-size:12px; padding:0 6px;")
        self.meta_label.setWordWrap(True)
        outer.addWidget(self.meta_label)

        self.link_label = QLabel()
        self.link_label.setOpenExternalLinks(True)
        self.link_label.setWordWrap(True)
        self.link_label.setStyleSheet("padding:0 6px;")
        outer.addWidget(self.link_label)

        self.notes_label = QLabel()
        self.notes_label.setWordWrap(True)
        self.notes_label.setStyleSheet(
            f"color:{p.text_primary}; background:{p.bg_history_entry}; border-radius:6px; padding:10px;"
        )
        outer.addWidget(self.notes_label)

        # -- Anhang/Dokument -----------------------------------------
        attach_row = QHBoxLayout()
        attach_row.setContentsMargins(6, 6, 6, 6)
        attach_row.setSpacing(8)
        self.attachment_label = QLabel("Kein Anhang hinterlegt")
        self.attachment_label.setStyleSheet(f"color:{p.text_muted}; font-size:12px;")
        self.attachment_label.setWordWrap(True)
        attach_row.addWidget(self.attachment_label, stretch=1)

        self.attach_btn = QPushButton("📎 Anhang wählen")
        self.attach_btn.setStyleSheet(th.secondary_button_stylesheet(p))
        self.attach_btn.clicked.connect(self._on_choose_attachment)
        attach_row.addWidget(self.attach_btn)

        self.remove_attach_btn = QPushButton("Entfernen")
        self.remove_attach_btn.setStyleSheet(th.danger_button_stylesheet(p))
        self.remove_attach_btn.clicked.connect(self._on_remove_attachment)
        attach_row.addWidget(self.remove_attach_btn)
        outer.addLayout(attach_row)

        # -- Status ändern ---------------------------------------------
        status_row = QHBoxLayout()
        status_row.setContentsMargins(6, 6, 6, 6)
        status_row.setSpacing(8)
        status_label = QLabel("Status ändern:")
        status_label.setStyleSheet(f"color:{p.text_primary};")
        status_row.addWidget(status_label)

        self.status_combo = QComboBox()
        self.status_combo.addItems(STATUS_OPTIONS)
        self.status_combo.setStyleSheet(
            f"QComboBox {{ background:{p.bg_input}; color:{p.text_primary}; "
            f"border:1px solid {p.border_input}; border-radius:4px; padding:4px 8px; }}"
        )
        self.status_combo.currentTextChanged.connect(self._on_status_changed)
        status_row.addWidget(self.status_combo, stretch=1)
        outer.addLayout(status_row)


        # -- Aktions-Buttons -----------------------------------------
        actions_row = QHBoxLayout()
        actions_row.setContentsMargins(6, 4, 6, 4)
        actions_row.setSpacing(8)
        self.edit_btn = QPushButton("Bearbeiten")
        self.edit_btn.setStyleSheet(th.secondary_button_stylesheet(p))
        self.edit_btn.clicked.connect(
            lambda: self.current_app_id is not None
            and self.edit_requested.emit(self.current_app_id)
        )
        self.delete_btn = QPushButton("Löschen")
        self.delete_btn.setStyleSheet(th.danger_button_stylesheet(p))
        self.delete_btn.clicked.connect(
            lambda: self.current_app_id is not None
            and self.delete_requested.emit(self.current_app_id)
        )
        actions_row.addWidget(self.edit_btn)
        actions_row.addWidget(self.delete_btn)
        outer.addLayout(actions_row)

        # -- Notiz hinzufügen -------------------------------------------
        note_label = QLabel("Notiz hinzufügen:")
        note_label.setStyleSheet(f"color:{p.text_primary}; padding:0 6px;")
        outer.addWidget(note_label)
        self.note_input = QTextEdit()
        self.note_input.setFixedHeight(60)
        self.note_input.setStyleSheet(th.text_input_stylesheet(p))
        outer.addWidget(self.note_input)
        self.add_note_btn = QPushButton("Notiz speichern")
        self.add_note_btn.setStyleSheet(th.primary_button_stylesheet(p))
        self.add_note_btn.clicked.connect(self._on_add_note)
        outer.addWidget(self.add_note_btn)

        # -- Interaktions-Historie -----------------------------------
        history_label = QLabel("Verlauf:")
        history_label.setStyleSheet(f"color:{p.text_primary}; padding:0 6px;")
        outer.addWidget(history_label)
        self.history_scroll = QScrollArea()
        self.history_scroll.setWidgetResizable(True)
        self.history_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self.history_container = QWidget()
        self.history_container.setStyleSheet("background: transparent;")
        self.history_layout = QVBoxLayout(self.history_container)
        self.history_layout.setContentsMargins(6, 4, 6, 4)
        self.history_layout.setSpacing(6)
        self.history_layout.addStretch()
        self.history_scroll.setWidget(self.history_container)
        outer.addWidget(self.history_scroll, stretch=1)

        # Standardmäßig alle Detail-Widgets verstecken (empty state)
        self._detail_widgets = [
            self.title_label, self.subtitle_label, self.meta_label,
            self.link_label, self.notes_label, self.edit_btn, self.delete_btn,
            self.add_note_btn, self.note_input, self.history_scroll,
            self.status_combo, self.attachment_label, self.attach_btn,
            self.remove_attach_btn,
        ]

    # -- Öffentliche API ------------------------------------------------

    def show_empty_state(self) -> None:
        self.current_app_id = None
        self.empty_label.setVisible(True)
        for w in self._detail_widgets:
            w.setVisible(False)

    def show_application(self, app_data: dict, interactions: list[dict]) -> None:
        self.current_app_id = app_data["id"]
        self.current_attachment = app_data.get("anhang_pfad") or ""
        self.empty_label.setVisible(False)
        for w in self._detail_widgets:
            w.setVisible(True)

        self.title_label.setText(app_data.get("firmenname", ""))
        self.subtitle_label.setText(app_data.get("rollenbezeichnung", ""))

        meta_parts = [f"Beworben am: {app_data.get('bewerbungsdatum', '–')}"]
        if app_data.get("followup_datum"):
            meta_parts.append(f"Follow-up: {app_data['followup_datum']}")
        self.meta_label.setText(" | ".join(meta_parts))

        joblink = app_data.get("joblink") or ""
        self.link_label.setText(
            f'<a href="{joblink}">{joblink}</a>' if joblink else ""
        )

        anmerkungen = app_data.get("anmerkungen") or ""
        self.notes_label.setText(anmerkungen)
        self.notes_label.setVisible(bool(anmerkungen))

        if self.current_attachment:
            self.attachment_label.setText(f"📎 {Path(self.current_attachment).name}")
            self.remove_attach_btn.setVisible(True)
        else:
            self.attachment_label.setText("Kein Anhang hinterlegt")
            self.remove_attach_btn.setVisible(False)

        self.status_combo.blockSignals(True)
        self.status_combo.setCurrentText(app_data.get("status", ""))
        self.status_combo.blockSignals(False)

        # Historie neu aufbauen
        while self.history_layout.count() > 1:
            item = self.history_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        p = self.palette_
        for interaction in interactions:
            entry = QLabel(
                f"<b style='color:{p.text_primary};'>{interaction['art']}</b> "
                f"<span style='color:{p.text_muted};'>– {interaction['datum']}</span><br>"
                f"<span style='color:{p.text_secondary};'>{interaction.get('details') or ''}</span>"
            )
            entry.setWordWrap(True)
            entry.setContentsMargins(10, 8, 10, 8)
            entry.setStyleSheet(th.history_entry_stylesheet(p))
            self.history_layout.insertWidget(self.history_layout.count() - 1, entry)

        self.note_input.clear()

    # -- Interne Slots ----------------------------------------------------

    def _on_status_changed(self, new_status: str) -> None:
        if self.current_app_id is not None:
            self.status_change_requested.emit(self.current_app_id, new_status)

    def _on_add_note(self) -> None:
        text = self.note_input.toPlainText().strip()
        if text and self.current_app_id is not None:
            self.note_added.emit(self.current_app_id, text)
            self.note_input.clear()

    def _on_choose_attachment(self) -> None:
        if self.current_app_id is None:
            return
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Anschreiben/CV auswählen",
            "",
            "Dokumente (*.pdf *.docx *.doc *.odt);;Alle Dateien (*.*)",
        )
        if file_path:
            self.attachment_set_requested.emit(self.current_app_id, file_path)

    def _on_remove_attachment(self) -> None:
        if self.current_app_id is not None:
            self.attachment_cleared_requested.emit(self.current_app_id)
