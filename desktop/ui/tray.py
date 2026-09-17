"""System tray icon and menu (spec §20)."""
from __future__ import annotations

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from infrastructure.networking.receiver import ReceiverServer
from ui.resources.icons import app_icon


class TrayController:
    def __init__(
        self,
        app: QApplication,
        window,
        receiver: ReceiverServer | None = None,
    ) -> None:
        self._app = app
        self._window = window
        self._receiver = receiver

        self.tray = QSystemTrayIcon(app_icon(), app)
        self.tray.setToolTip("PixSynq")

        menu = QMenu()
        open_action = QAction("Open", menu)
        open_action.triggered.connect(self.show_window)
        menu.addAction(open_action)

        self._pause_action = QAction("Pause Backup", menu)
        self._pause_action.triggered.connect(self._toggle_pause)
        self._pause_action.setEnabled(receiver is not None)
        menu.addAction(self._pause_action)

        menu.addSeparator()
        quit_action = QAction("Exit", menu)
        quit_action.triggered.connect(self._quit)
        menu.addAction(quit_action)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_activated)
        self.tray.show()
        self._menu = menu  # keep alive

    def show_window(self) -> None:
        self._window.showNormal()
        self._window.raise_()
        self._window.activateWindow()

    def notify(self, title: str, message: str) -> None:
        self.tray.showMessage(title, message, app_icon())

    def _on_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.show_window()

    def _toggle_pause(self) -> None:
        assert self._receiver is not None
        paused = not self._receiver.paused
        self._receiver.set_paused(paused)
        self._pause_action.setText("Resume Backup" if paused else "Pause Backup")

    def _quit(self) -> None:
        self._window.allow_close = True
        self._app.quit()
