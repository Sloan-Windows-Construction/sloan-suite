import os
from PyQt5.QtWidgets import QSystemTrayIcon, QMenu
from PyQt5.QtGui import QIcon

class Tray:
    def __init__(self, app, controller, parent=None, icon_path: str = ""):
        self.app = app
        self.controller = controller

        icon = QIcon()
        if icon_path and os.path.exists(icon_path):
            icon = QIcon(icon_path)

        # Fallback to a default if somehow not provided
        if icon.isNull():
            # last resort: a generic system icon; avoids the “No Icon set” warning
            icon = app.windowIcon()

        self.tray = QSystemTrayIcon(icon, parent)

        menu = QMenu()
        act_config = menu.addAction("Open Config…")
        act_exit = menu.addAction("Exit")
        act_config.triggered.connect(lambda: self.controller.open_config.emit())
        act_exit.triggered.connect(lambda: self.app.quit())

        self.tray.setContextMenu(menu)
        self.tray.setToolTip("Sloan Renamer & Organizer")
        self.tray.show()
