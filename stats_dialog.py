"""
stats_dialog.py
----------------
Statistik-Dashboard für CTAM: einfache Auswertungen als separater Dialog
(nicht im Hauptfenster, um das Kanban-Board nicht zu überladen).

Zeigt:
    - Bewerbungen pro Monat (Balkendiagramm)
    - Status-Verteilung (Balkendiagramm)
    - Erfolgsquoten (Interview-Quote, Angebots-Quote) als Textkennzahlen

Nutzt matplotlib eingebettet über FigureCanvasQTAgg, da dies ohne
zusätzliches PyQt6-Charts-Paket auskommt und in der Zielumgebung bereits
verfügbar ist.
"""

from __future__ import annotations

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PyQt6.QtWidgets import (
    QDialog,
    QGridLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from database_manager import ApplicationManager
import theme as th


class KpiCard(QWidget):
    """Kleine Kennzahl-Karte (z. B. 'Interview-Quote: 42%')."""

    def __init__(self, title: str, value: str, palette: th.Palette, parent=None) -> None:
        super().__init__(parent)
        p = palette
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(4)
        self.setStyleSheet(
            f"background:{p.bg_history_entry}; border-radius:8px;"
        )

        value_label = QLabel(value)
        value_label.setStyleSheet(f"font-size:22px; font-weight:700; color:{p.accent}; padding:0;")
        layout.addWidget(value_label)

        title_label = QLabel(title)
        title_label.setStyleSheet(f"color:{p.text_muted}; font-size:12px; padding:0;")
        title_label.setWordWrap(True)
        layout.addWidget(title_label)


class StatsDialog(QDialog):
    """Statistik-Dashboard: Bewerbungen/Monat, Status-Verteilung,
    Erfolgsquoten (Interview -> Angebot)."""

    def __init__(self, manager: ApplicationManager, palette: th.Palette, parent=None) -> None:
        super().__init__(parent)
        self.manager = manager
        self.palette_ = palette
        self.setWindowTitle("Statistik-Dashboard")
        self.resize(760, 640)
        self._build_ui()

    def _build_ui(self) -> None:
        p = self.palette_
        self.setStyleSheet(f"background:{p.bg_root};")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        heading = QLabel("Statistik-Dashboard")
        heading.setStyleSheet(f"font-size:18px; font-weight:700; color:{p.text_primary};")
        layout.addWidget(heading)

        # -- KPI-Kacheln ---------------------------------------------
        rates = self.manager.get_conversion_rates()
        kpi_row = QGridLayout()
        kpi_row.setSpacing(10)
        kpi_row.addWidget(
            KpiCard("Bewerbungen gesamt", str(rates["gesamt"]), p), 0, 0
        )
        kpi_row.addWidget(
            KpiCard("Interview-Quote", f"{rates['interview_quote']}%", p), 0, 1
        )
        kpi_row.addWidget(
            KpiCard("Angebots-Quote (nach Interview)",
                    f"{rates['angebot_quote_von_interview']}%", p), 0, 2
        )
        layout.addLayout(kpi_row)

        # -- Chart: Bewerbungen pro Monat --------------------------------
        monthly = self.manager.get_applications_per_month()
        fig1 = Figure(figsize=(6, 2.6), dpi=100)
        fig1.patch.set_facecolor(p.bg_root)
        ax1 = fig1.add_subplot(111)
        ax1.set_facecolor(p.bg_root)
        if monthly:
            months = [m for m, _ in monthly]
            counts = [c for _, c in monthly]
            ax1.bar(months, counts, color=p.accent)
        ax1.set_title("Bewerbungen pro Monat", color=p.text_primary, fontsize=11)
        self._style_axes(ax1, p)
        canvas1 = FigureCanvasQTAgg(fig1)
        layout.addWidget(canvas1)

        # -- Chart: Status-Verteilung -----------------------------------
        distribution = self.manager.get_status_distribution()
        fig2 = Figure(figsize=(6, 2.6), dpi=100)
        fig2.patch.set_facecolor(p.bg_root)
        ax2 = fig2.add_subplot(111)
        ax2.set_facecolor(p.bg_root)
        statuses = list(distribution.keys())
        values = list(distribution.values())
        colors = [p.status_colors.get(s, p.accent) for s in statuses]
        ax2.bar(statuses, values, color=colors)
        ax2.set_title("Status-Verteilung", color=p.text_primary, fontsize=11)
        self._style_axes(ax2, p)
        canvas2 = FigureCanvasQTAgg(fig2)
        layout.addWidget(canvas2)

        layout.addStretch()

    @staticmethod
    def _style_axes(ax, p: th.Palette) -> None:
        ax.tick_params(colors=p.text_muted, labelsize=8)
        for spine in ax.spines.values():
            spine.set_color(p.border_subtle)
        ax.title.set_color(p.text_primary)
