"""
theme.py
--------
Zentrale Farb-/Theme-Verwaltung für CTAM. Statt Farben über mehrere
Dateien verteilt hart zu codieren, liegen hier zwei Paletten (Dunkel/Hell)
sowie Hilfsfunktionen, die daraus fertige Qt-Stylesheets bauen.

Verwendung:
    from theme import get_theme, ThemeName

    theme = get_theme(ThemeName.DARK)
    widget.setStyleSheet(theme.sidebar_stylesheet())

Ein Theme-Wechsel zur Laufzeit ruft `MainWindow.apply_theme()` auf, das
alle betroffenen Widgets neu stylt (siehe main_window.py).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ThemeName(str, Enum):
    DARK = "dark"
    LIGHT = "light"


@dataclass(frozen=True)
class Palette:
    """Rohe Farbwerte einer Palette. Alle abhängigen Stylesheets werden
    daraus generiert, damit ein Theme-Wechsel an einer einzigen Stelle
    passiert."""

    name: ThemeName

    # Flächen
    bg_root: str
    bg_sidebar: str
    bg_topbar: str
    bg_kanban_area: str
    bg_column: str
    bg_card: str
    bg_input: str
    bg_detail_panel: str
    bg_history_entry: str

    # Ränder
    border_subtle: str
    border_input: str

    # Text
    text_primary: str
    text_secondary: str
    text_muted: str
    text_on_accent: str

    # Akzent-/Statusfarben (identisch in beiden Themes, damit Status
    # immer wiedererkennbar bleibt)
    accent: str = "#5B8DEF"
    accent_hover: str = "#4A78D6"
    danger: str = "#E5534B"
    danger_bg_hover: str = "#4A2E2C"
    warning_bg: str = "#FFF3CD"
    warning_text: str = "#8a6d3b"

    status_colors: dict = field(default_factory=lambda: {
        "Beworben": "#5B8DEF",
        "Interview": "#F2A93B",
        "Angebot": "#3FB27F",
        "Abgelehnt": "#E5534B",
        "Erledigt/Archiviert": "#8A8F98",
    })


DARK_PALETTE = Palette(
    name=ThemeName.DARK,
    bg_root="#2B2F3A",
    bg_sidebar="#2B2F3A",
    bg_topbar="#3A3F4D",
    bg_kanban_area="#EDEFF3",
    bg_column="#E4E7ED",
    bg_card="#ffffff",
    bg_input="#3A3F4D",
    bg_detail_panel="#2B2F3A",
    bg_history_entry="#3A3F4D",
    border_subtle="#1E2129",
    border_input="#4A4F5E",
    text_primary="#F0F2F6",
    text_secondary="#C7CBD6",
    text_muted="#9AA1B0",
    text_on_accent="#FFFFFF",
)

LIGHT_PALETTE = Palette(
    name=ThemeName.LIGHT,
    bg_root="#FFFFFF",
    bg_sidebar="#F4F6FA",
    bg_topbar="#FFFFFF",
    bg_kanban_area="#F4F5F7",
    bg_column="#EEF0F3",
    bg_card="#ffffff",
    bg_input="#FFFFFF",
    bg_detail_panel="#FFFFFF",
    bg_history_entry="#F4F5F7",
    border_subtle="#DDE1E6",
    border_input="#C9CDD6",
    text_primary="#1A1A1A",
    text_secondary="#555555",
    text_muted="#8A8F98",
    text_on_accent="#FFFFFF",
)


def get_palette(name: ThemeName) -> Palette:
    return DARK_PALETTE if name == ThemeName.DARK else LIGHT_PALETTE


# ---------------------------------------------------------------------------
# Fertige Stylesheet-Bausteine (werden von main_window.py / widgets.py genutzt)
# ---------------------------------------------------------------------------

def central_stylesheet(p: Palette) -> str:
    return f"background:{p.bg_root};"


def topbar_stylesheet(p: Palette) -> str:
    return f"background:{p.bg_topbar}; border-bottom:1px solid {p.border_subtle};"


def splitter_stylesheet(p: Palette) -> str:
    return f"""
        QSplitter {{ background:{p.bg_root}; }}
        QSplitter::handle {{ background:{p.border_subtle}; width:2px; }}
        QSplitter::handle:hover {{ background:{p.accent}; }}
    """


def sidebar_stylesheet(p: Palette) -> str:
    return f"""
        QWidget {{
            background:{p.bg_sidebar};
            border-right:1px solid {p.border_subtle};
        }}
        QLabel {{
            color:{p.text_primary};
            border: none;
            background: transparent;
        }}
        QCheckBox {{
            color:{p.text_primary};
            background: transparent;
        }}
        QLineEdit {{
            background:{p.bg_input};
            color:{p.text_primary};
            border:1px solid {p.border_input};
            border-radius:4px;
            padding:4px 6px;
        }}
        QListWidget {{
            background:{p.bg_input};
            color:{p.text_primary};
            border:1px solid {p.border_input};
            border-radius:4px;
        }}
        QComboBox {{
            background:{p.bg_input};
            color:{p.text_primary};
            border:1px solid {p.border_input};
            border-radius:4px;
            padding:4px 6px;
        }}
    """


def kanban_area_stylesheet(p: Palette) -> str:
    return f"background:{p.bg_kanban_area};"


def column_header_stylesheet(p: Palette) -> str:
    return (
        f"font-weight:700; font-size:13px; padding:6px; color:{p.text_primary}; "
        f"background:{p.bg_topbar}; border-radius:6px;"
    )


def column_list_stylesheet(p: Palette) -> str:
    return f"""
        QListWidget {{
            background-color: {p.bg_column};
            border: 1px solid {p.border_subtle};
            border-radius: 6px;
        }}
        QListWidget::item {{ border: none; }}
        QListWidget::item:selected {{ background: transparent; }}
    """


def card_stylesheet(p: Palette) -> str:
    return f"""
        QFrame#card {{
            background-color: {p.bg_card};
            border: 1px solid {p.border_subtle};
            border-radius: 8px;
        }}
        QFrame#card:hover {{
            border: 1px solid {p.accent};
        }}
    """


def detail_panel_stylesheet(p: Palette) -> str:
    return f"background-color:{p.bg_detail_panel}; border-left: 2px solid {p.border_subtle};"


def history_entry_stylesheet(p: Palette) -> str:
    return f"background:{p.bg_history_entry}; border-radius:6px; padding:8px 10px; margin-bottom:2px;"


def primary_button_stylesheet(p: Palette) -> str:
    return f"""
        QPushButton {{
            background:{p.accent}; color:{p.text_on_accent}; border-radius:5px;
            padding:6px 14px; font-weight:600;
        }}
        QPushButton:hover {{ background:{p.accent_hover}; }}
    """


def secondary_button_stylesheet(p: Palette) -> str:
    return f"""
        QPushButton {{
            background:{p.bg_input}; color:{p.text_primary}; border:1px solid {p.border_input};
            border-radius:5px; padding:6px 12px;
        }}
        QPushButton:hover {{ background:{p.bg_history_entry}; }}
    """


def danger_button_stylesheet(p: Palette) -> str:
    return f"""
        QPushButton {{
            background:{p.bg_input}; color:{p.danger}; border:1px solid {p.border_input};
            border-radius:5px; padding:6px 12px;
        }}
        QPushButton:hover {{ background:{p.danger_bg_hover}; }}
    """


def text_input_stylesheet(p: Palette) -> str:
    return (
        f"background:{p.bg_input}; color:{p.text_primary}; "
        f"border:1px solid {p.border_input}; border-radius:6px; padding:6px;"
    )
