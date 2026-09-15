"""Application bootstrap: Qt application, logging, theme, main window."""
from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from infrastructure.configuration.paths import AppPaths
from infrastructure.configuration.settings_store import SettingsStore
from infrastructure.discovery.service import DiscoveryService
from infrastructure.logging_setup import configure_logging
from ui.dialogs.setup_wizard import SetupWizard
from ui.styles.theme import Theme, apply_theme
from ui.windows.main_window import MainWindow

APP_NAME = "PhotoSync"
APP_VERSION = "0.1.0"
ORG_NAME = "PhotoSync"

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

    apply_theme(app, Theme.DARK)

    settings = SettingsStore(paths.settings_path)
    log.info("Installation ID: %s", settings.installation_id)

    if not settings.setup_complete:
        wizard = SetupWizard(settings)
        if wizard.exec() != SetupWizard.DialogCode.Accepted:
            log.info("Setup cancelled; exiting")
            return 0

    discovery = DiscoveryService(app_version=APP_VERSION)
    window = MainWindow(
        app_version=APP_VERSION, settings=settings, discovery=discovery
    )
    window.show()
    discovery.start()
    app.aboutToQuit.connect(discovery.stop)

    return app.exec()
