"""
main.py
-------
Einstiegspunkt für "Career Tracker & Application Manager (CTAM)".
Vollständig offline-fähige Desktop-Anwendung (PyQt6 + SQLite3).

Start:
    python main.py
"""

import sys

from PyQt6.QtWidgets import QApplication

from main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Career Tracker & Application Manager")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
