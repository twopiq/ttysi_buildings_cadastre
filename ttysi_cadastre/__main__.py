import sys

from PySide6.QtWidgets import QApplication

from ttysi_cadastre.ui import theme
from ttysi_cadastre.ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("TTYSI Binolar kadastri")
    app.setOrganizationName("TTYSI")
    app.setStyle("Fusion")
    theme.apply(app)
    w = MainWindow()
    w.show()
    if len(sys.argv) > 1 and sys.argv[1].lower().endswith(".ttysi"):
        w.open_project(sys.argv[1])
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
