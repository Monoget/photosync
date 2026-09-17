"""First-run setup flow: Welcome → Register → Choose Folder → Ready.

A custom stacked dialog (not QWizard) so it matches the app theme.
"""
from __future__ import annotations

import getpass
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.services.registration import RegistrationInput, validate_registration
from infrastructure.configuration.settings_store import SettingsStore
from infrastructure.storage.destination import default_destination, validate_destination

PRIVACY_TEXT = (
    "PixSynq collects your name, email address, Windows username, "
    "app version, and operating system details to register this "
    "installation and notify you about software updates. The server "
    "records the IP address of the registration request. Nothing else "
    "is collected — never your photos, files, or browsing data."
)


class SetupWizard(QDialog):
    def __init__(self, settings: SettingsStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("PixSynq Setup")
        self.setModal(True)
        self.setMinimumSize(560, 480)
        self._settings = settings

        self._stack = QStackedWidget()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 24)
        layout.addWidget(self._stack, stretch=1)

        self._stack.addWidget(self._welcome_page())
        self._stack.addWidget(self._register_page())
        self._stack.addWidget(self._folder_page())
        self._stack.addWidget(self._ready_page())

    # -- Pages ----------------------------------------------------------

    def _welcome_page(self) -> QWidget:
        page, body = self._page("Welcome to PixSynq")
        sub = QLabel(
            "Automatically back up your Android photos\n"
            "to your Windows PC over Wi-Fi."
        )
        sub.setProperty("class", "muted")
        body.addWidget(sub)
        body.addStretch(1)
        body.addLayout(self._buttons(primary=("Get Started", self._next)))
        return page

    def _register_page(self) -> QWidget:
        page, body = self._page("Register PixSynq")

        body.addWidget(self._field_label("Name"))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Your name")
        body.addWidget(self.name_edit)

        body.addWidget(self._field_label("Email"))
        self.email_edit = QLineEdit()
        self.email_edit.setPlaceholderText("you@example.com")
        body.addWidget(self.email_edit)

        privacy = QLabel(PRIVACY_TEXT)
        privacy.setProperty("class", "muted")
        privacy.setWordWrap(True)
        body.addWidget(privacy)

        self.consent_box = QCheckBox(
            "I agree to the Privacy Policy and understand\n"
            "the information PixSynq collects."
        )
        body.addWidget(self.consent_box)

        self.register_error = QLabel("")
        self.register_error.setWordWrap(True)
        self.register_error.setStyleSheet("color: #ef4444;")
        body.addWidget(self.register_error)

        body.addStretch(1)
        body.addLayout(
            self._buttons(
                back=("Back", self._back),
                primary=("Continue", self._submit_registration),
            )
        )
        return page

    def _folder_page(self) -> QWidget:
        page, body = self._page("Choose where your photos should be stored")

        sub = QLabel("PixSynq will save transferred photos here:")
        sub.setProperty("class", "muted")
        body.addWidget(sub)

        self._destination = default_destination()
        self.folder_label = QLabel(str(self._destination))
        self.folder_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        body.addWidget(self.folder_label)

        choose = QPushButton("Choose Folder…")
        choose.clicked.connect(self._choose_folder)
        body.addWidget(choose, alignment=Qt.AlignmentFlag.AlignLeft)

        self.folder_error = QLabel("")
        self.folder_error.setWordWrap(True)
        self.folder_error.setStyleSheet("color: #ef4444;")
        body.addWidget(self.folder_error)

        body.addStretch(1)
        body.addLayout(
            self._buttons(
                back=("Back", self._back),
                primary=("Continue", self._submit_folder),
            )
        )
        return page

    def _ready_page(self) -> QWidget:
        page, body = self._page("You're all set")
        sub = QLabel(
            "PixSynq is ready. Next, install PixSynq on your Android "
            "phone and pair it from the Devices page."
        )
        sub.setProperty("class", "muted")
        sub.setWordWrap(True)
        body.addWidget(sub)
        body.addStretch(1)
        body.addLayout(self._buttons(primary=("Open PixSynq", self.accept)))
        return page

    # -- Helpers --------------------------------------------------------

    def _page(self, title: str) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget(objectName="appRoot")
        body = QVBoxLayout(page)
        body.setSpacing(14)
        heading = QLabel(title)
        heading.setProperty("class", "pageTitle")
        heading.setWordWrap(True)
        body.addWidget(heading)
        return page, body

    def _field_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setProperty("class", "cardTitle")
        return label

    def _buttons(
        self,
        primary: tuple[str, object],
        back: tuple[str, object] | None = None,
    ) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addStretch(1)
        if back:
            back_btn = QPushButton(back[0])
            back_btn.clicked.connect(back[1])
            row.addWidget(back_btn)
        primary_btn = QPushButton(primary[0])
        primary_btn.setProperty("class", "primary")
        primary_btn.clicked.connect(primary[1])
        row.addWidget(primary_btn)
        return row

    def _next(self) -> None:
        self._stack.setCurrentIndex(self._stack.currentIndex() + 1)

    def _back(self) -> None:
        self._stack.setCurrentIndex(self._stack.currentIndex() - 1)

    # -- Step handlers --------------------------------------------------

    def _submit_registration(self) -> None:
        reg = RegistrationInput(
            name=self.name_edit.text(),
            email=self.email_edit.text(),
            consented=self.consent_box.isChecked(),
        )
        problems = validate_registration(reg)
        if problems:
            self.register_error.setText("\n".join(problems))
            return
        self.register_error.setText("")
        self._settings.update(
            {
                "registration": {
                    "name": reg.name.strip(),
                    "email": reg.email.strip(),
                    "consented_at": datetime.now(timezone.utc).isoformat(),
                    "desktop_username": getpass.getuser(),
                    "upload_status": "pending",
                }
            }
        )
        self._next()

    def _choose_folder(self) -> None:
        chosen = QFileDialog.getExistingDirectory(
            self, "Choose Photo Backup Folder", str(self._destination)
        )
        if chosen:
            self._destination = Path(chosen)
            self.folder_label.setText(str(self._destination))
            self.folder_error.setText("")

    def _submit_folder(self) -> None:
        check = validate_destination(self._destination)
        if not check.ok:
            self.folder_error.setText(check.reason)
            return
        self.folder_error.setText("")
        self._settings.set_destination_dir(self._destination)
        self._next()

    def accept(self) -> None:  # noqa: D102
        self._settings.mark_setup_complete()
        super().accept()
