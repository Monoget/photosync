"""Pairing dialog: shows the 6-digit code and a QR payload for the phone."""
from __future__ import annotations

import json

import qrcode
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPixmap
from PySide6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout, QWidget

from infrastructure.discovery.service import local_ip
from infrastructure.networking.receiver import ReceiverServer


def qr_pixmap(data: str, module_px: int = 5) -> QPixmap:
    qr = qrcode.QRCode(border=2)
    qr.add_data(data)
    qr.make(fit=True)
    matrix = qr.get_matrix()
    size = len(matrix) * module_px
    image = QImage(size, size, QImage.Format.Format_RGB32)
    image.fill(QColor("white"))
    for y, row in enumerate(matrix):
        for x, module in enumerate(row):
            if module:
                for dy in range(module_px):
                    for dx in range(module_px):
                        image.setPixelColor(
                            x * module_px + dx, y * module_px + dy, QColor("black")
                        )
    return QPixmap.fromImage(image)


class PairDialog(QDialog):
    def __init__(self, receiver: ReceiverServer, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Pair a Device")
        self.setModal(True)
        self._receiver = receiver

        code = receiver.pairing.begin_session()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 24)
        layout.setSpacing(14)

        title = QLabel("Pair your Android phone")
        title.setProperty("class", "pageTitle")
        layout.addWidget(title)

        steps = QLabel(
            "1. Open PhotoSync on your phone (same Wi-Fi network).\n"
            "2. Tap this PC when it appears.\n"
            "3. Enter this code, or scan the QR code:"
        )
        steps.setProperty("class", "muted")
        layout.addWidget(steps)

        code_label = QLabel(f"{code[:3]} {code[3:]}")
        code_label.setStyleSheet("font-size: 40px; font-weight: 700; letter-spacing: 6px;")
        code_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(code_label)

        payload = json.dumps(
            {
                "v": 1,
                "ip": local_ip(),
                "port": receiver.port,
                "fp": receiver.fingerprint,
                "code": code,
            }
        )
        qr_label = QLabel()
        qr_label.setPixmap(qr_pixmap(payload))
        qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(qr_label)

        self.status = QLabel("Waiting for your phone…")
        self.status.setProperty("class", "muted")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status)

        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        layout.addWidget(cancel, alignment=Qt.AlignmentFlag.AlignRight)

        receiver.pairing.device_paired.connect(self._on_paired)
        receiver.pairing.attempt_failed.connect(self._on_attempt_failed)

    def _on_paired(self, name: str) -> None:
        self.status.setText(f"Paired with {name}!")
        self.accept()

    def _on_attempt_failed(self, attempts_left: int) -> None:
        if attempts_left > 0:
            self.status.setText(
                f"Wrong code entered — {attempts_left} attempts remaining."
            )
        else:
            self.status.setText(
                "Too many wrong attempts. Close this dialog and try again."
            )

    def done(self, result: int) -> None:
        self._receiver.pairing.end_session()
        try:
            self._receiver.pairing.device_paired.disconnect(self._on_paired)
            self._receiver.pairing.attempt_failed.disconnect(self._on_attempt_failed)
        except RuntimeError:
            pass
        super().done(result)
