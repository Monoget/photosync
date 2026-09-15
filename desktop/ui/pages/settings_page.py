"""Settings page: view and change the photo destination folder."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QLabel, QMessageBox, QPushButton

from infrastructure.configuration.settings_store import SettingsStore
from infrastructure.storage.destination import validate_destination
from ui.pages.base_page import BasePage
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

        general = Card("General")
        note = QLabel("Startup, background, and update preferences will "
                      "appear here in an upcoming build.")
        note.setProperty("class", "muted")
        note.setWordWrap(True)
        general.add(note)
        self.body.addWidget(general)

        self.finish()

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
