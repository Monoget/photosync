"""Application bootstrap: Qt application, logging, theme, main window."""
from __future__ import annotations

import logging

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication

from core.services.telemetry import sync_registration_async
from core.services.update_checker import UpdateChecker
from infrastructure.configuration.paths import AppPaths
from infrastructure.configuration.settings_store import SettingsStore
from infrastructure.database.db import DeviceStore, PhotoStore, migrate
from infrastructure.discovery.service import DiscoveryService
from infrastructure.logging_setup import configure_logging
from infrastructure.networking.receiver import ReceiverServer
from infrastructure.security.identity import DeviceIdentity
from ui.dialogs.setup_wizard import SetupWizard
from ui.resources.icons import app_icon
from ui.styles.theme import Theme, apply_theme
from ui.tray import TrayController
from ui.windows.main_window import MainWindow

APP_NAME = "PixSynq"
APP_VERSION = "0.1.0"
ORG_NAME = "PixSynq"

log = logging.getLogger(__name__)


def run(argv: list[str]) -> int:
    paths = AppPaths.default()
    paths.ensure()
    configure_logging(paths.logs_dir)
    log.info("Starting %s %s", APP_NAME, APP_VERSION)

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName(ORG_NAME)

    settings = SettingsStore(paths.settings_path)
    log.info("Installation ID: %s", settings.installation_id)

    theme = Theme.LIGHT if settings.get("theme") == "light" else Theme.DARK
    apply_theme(app, theme)
    app.setWindowIcon(app_icon())

    if not settings.setup_complete:
        wizard = SetupWizard(settings)
        if wizard.exec() != SetupWizard.DialogCode.Accepted:
            log.info("Setup cancelled; exiting")
            return 0

    migrate(paths.database_path)
    device_store = DeviceStore(paths.database_path)
    photo_store = PhotoStore(paths.database_path)
    identity = DeviceIdentity.load_or_create(paths.data_dir)
    receiver = ReceiverServer(
        identity=identity,
        device_store=device_store,
        pc_id=settings.installation_id,
        app_version=APP_VERSION,
        photo_store=photo_store,
        settings=settings,
    )

    discovery = DiscoveryService(app_version=APP_VERSION)
    window = MainWindow(
        app_version=APP_VERSION,
        settings=settings,
        discovery=discovery,
        receiver=receiver,
        device_store=device_store,
        photo_store=photo_store,
    )
    tray = TrayController(app, window, receiver)
    window.tray_available = tray.tray.isSystemTrayAvailable()
    app.setQuitOnLastWindowClosed(False)
    window.show()

    receiver.start()
    discovery.start(port=receiver.port)
    app.aboutToQuit.connect(discovery.stop)
    app.aboutToQuit.connect(receiver.stop)

    # Best-effort server sync + update check; the app never depends on them.
    sync_registration_async(settings, APP_VERSION)
    checker = UpdateChecker(settings, APP_VERSION)
    checker.update_available.connect(
        lambda info: _show_update_dialog(app, window, info, checker)
    )
    QTimer.singleShot(5000, checker.check_async)

    return app.exec()


def _show_update_dialog(app, window, info: dict, checker: UpdateChecker) -> None:
    from ui.dialogs.update_dialog import UpdateDialog

    dialog = UpdateDialog(info, checker, window)
    if dialog.exec() == UpdateDialog.DialogCode.Accepted:
        # Installer launched; exit so it can replace the executable.
        app.quit()
