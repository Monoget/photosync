"""Settings page: view and change the photo destination folder."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QLabel,
    QMessageBox,
    QPushButton,
)

from infrastructure.configuration.settings_store import SettingsStore
from infrastructure.configuration.startup import (
    is_start_with_windows,
    set_start_with_windows,
)
from infrastructure.storage.destination import validate_destination
from ui.pages.base_page import BasePage
from ui.styles.theme import Theme, apply_theme
from ui.widgets.card import Card


class SettingsPage(BasePage):
    def __init__(self, settings: SettingsStore | None = None) -> None:
        super().__init__("Settings")
        self._settings = settings

        dest = Card("Photo Destination")
        self.dest_label = QLabel(self._destination_text())
        self.dest_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        change_btn = QPushButton("Change Folder…")
        change_btn.clicked.connect(self._change_folder)
        change_btn.setEnabled(settings is not None)
        dest.add(self.dest_label)
        dest.add(change_btn)
        self.body.addWidget(dest)

        appearance = Card("Appearance")
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Dark", "Light"])
        current_theme = (settings.get("theme", "dark") if settings else "dark")
        self.theme_combo.setCurrentIndex(0 if current_theme == "dark" else 1)
        self.theme_combo.currentIndexChanged.connect(self._theme_changed)
        self.theme_combo.setEnabled(settings is not None)
        appearance.add(self.theme_combo)
        self.body.addWidget(appearance)

        startup = Card("Startup & Background")
        self.startup_box = QCheckBox("Start PhotoSync with Windows")
        self.startup_box.setChecked(is_start_with_windows())
        self.startup_box.toggled.connect(self._startup_toggled)
        self.background_box = QCheckBox("Keep running in the background when closed")
        self.background_box.setChecked(
            bool(settings.get("run_in_background", True)) if settings else True
        )
        self.background_box.toggled.connect(self._background_toggled)
        self.background_box.setEnabled(settings is not None)
        startup.add(self.startup_box)
        startup.add(self.background_box)
        self.body.addWidget(startup)

        updates = Card("Updates")
        self.update_check_box = QCheckBox("Check for updates automatically")
        self.update_check_box.setChecked(
            bool(settings.get("update_check_auto", True)) if settings else True
        )
        self.update_check_box.toggled.connect(
            lambda on: self._set("update_check_auto", on)
        )
        self.update_notify_box = QCheckBox("Notify me about new versions")
        self.update_notify_box.setChecked(
            bool(settings.get("update_notify", True)) if settings else True
        )
        self.update_notify_box.toggled.connect(
            lambda on: self._set("update_notify", on)
        )
        for box in (self.update_check_box, self.update_notify_box):
            box.setEnabled(settings is not None)
        updates.add(self.update_check_box)
        updates.add(self.update_notify_box)
        self.body.addWidget(updates)

        self.finish()

    def _set(self, key: str, value) -> None:
        if self._settings is not None:
            self._settings.set(key, value)

    def _theme_changed(self, index: int) -> None:
        theme = "dark" if index == 0 else "light"
        self._set("theme", theme)
        app = QApplication.instance()
        if app is not None:
            apply_theme(app, Theme.DARK if theme == "dark" else Theme.LIGHT)

    def _startup_toggled(self, enabled: bool) -> None:
        if not set_start_with_windows(enabled):
            QMessageBox.warning(
                self, "Startup",
                "Could not update the Windows startup setting.",
            )

    def _background_toggled(self, enabled: bool) -> None:
        self._set("run_in_background", enabled)

    def _destination_text(self) -> str:
        current = self._settings.destination_dir if self._settings else None
        return str(current) if current else "Not configured"

    def _change_folder(self) -> None:
        assert self._settings is not None
        start = self._settings.destination_dir or Path.home()
        chosen = QFileDialog.getExistingDirectory(
            self, "Choose Photo Backup Folder", str(start)
        )
        if not chosen:
            return
        path = Path(chosen)
        check = validate_destination(path)
        if not check.ok:
            QMessageBox.warning(self, "Cannot use this folder", check.reason)
            return
        self._settings.set_destination_dir(path)
        self.dest_label.setText(str(path))
