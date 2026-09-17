"""Update notification dialog with verified download (spec §24-25)."""
from __future__ import annotations

import hashlib
import logging
import os
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QHBoxLayout,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.services.update_checker import UpdateChecker

log = logging.getLogger(__name__)


class _Downloader(QObject):
    finished = Signal(str)  # installer path
    failed = Signal(str)

    def __init__(self, url: str, sha256: str) -> None:
        super().__init__()
        self._url = url
        self._sha256 = sha256.lower()

    def start(self) -> None:
        threading.Thread(target=self._run, daemon=True, name="update-dl").start()

    def _run(self) -> None:
        if not self._url.lower().startswith("https://"):
            self.failed.emit("Update URL is not HTTPS; refusing to download.")
            return
        try:
            fd, tmp_name = tempfile.mkstemp(suffix=".exe", prefix="PixSynqUpdate-")
            digest = hashlib.sha256()
            with urllib.request.urlopen(self._url, timeout=60) as resp, \
                    os.fdopen(fd, "wb") as out:
                for chunk in iter(lambda: resp.read(256 * 1024), b""):
                    out.write(chunk)
                    digest.update(chunk)
            if digest.hexdigest() != self._sha256:
                Path(tmp_name).unlink(missing_ok=True)
                self.failed.emit(
                    "Downloaded file failed verification and was discarded."
                )
                return
            self.finished.emit(tmp_name)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            log.warning("Update download failed: %s", exc)
            self.failed.emit("Download failed. Please try again later.")


class UpdateDialog(QDialog):
    """Shows what's new; downloads, verifies, and launches the installer."""

    def __init__(
        self,
        info: dict,
        checker: UpdateChecker,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("PixSynq Update")
        self.setModal(True)
        self.setMinimumWidth(440)
        self._info = info
        self._checker = checker
        self._downloader: _Downloader | None = None
        self.installer_path: str | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(12)

        title = QLabel("A new version is available")
        title.setProperty("class", "pageTitle")
        layout.addWidget(title)

        version = QLabel(info.get("title") or f"PixSynq {info.get('version', '')}")
        layout.addWidget(version)

        message = QLabel(info.get("message") or "")
        message.setProperty("class", "muted")
        message.setWordWrap(True)
        layout.addWidget(message)

        self.status = QLabel("")
        self.status.setProperty("class", "muted")
        layout.addWidget(self.status)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.later_btn = QPushButton("Later")
        self.later_btn.clicked.connect(self._later)
        self.update_btn = QPushButton("Update Now")
        self.update_btn.setProperty("class", "primary")
        self.update_btn.clicked.connect(self._update_now)
        buttons.addWidget(self.later_btn)
        buttons.addWidget(self.update_btn)
        layout.addLayout(buttons)

        if info.get("mandatory"):
            self.later_btn.hide()

    def _later(self) -> None:
        version = self._info.get("version")
        if version:
            self._checker.skip_version(version)
        self.reject()

    def _update_now(self) -> None:
        url = self._info.get("download_url", "")
        sha = self._info.get("sha256", "")
        if not url or len(sha) != 64:
            self.status.setText("This release is missing verification data.")
            return
        self.update_btn.setEnabled(False)
        self.later_btn.setEnabled(False)
        self.status.setText("Downloading update…")
        self._downloader = _Downloader(url, sha)
        self._downloader.finished.connect(self._launch_installer)
        self._downloader.failed.connect(self._download_failed)
        self._downloader.start()

    def _download_failed(self, reason: str) -> None:
        self.status.setText(reason)
        self.update_btn.setEnabled(True)
        self.later_btn.setEnabled(True)

    def _launch_installer(self, path: str) -> None:
        self.installer_path = path
        self.status.setText("Verified. Starting installer…")
        # The installer is its own process, so replacing the running
        # executable is safe once this app exits (spec §25).
        os.startfile(path)  # noqa: S606 - verified download
        self.accept()
