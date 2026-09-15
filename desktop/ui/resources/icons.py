"""Programmatic application icon (no binary assets in the repo)."""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QIcon, QPainter, QPixmap


def app_icon(size: int = 256) -> QIcon:
    """Rounded blue tile with a white camera glyph."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    s = size / 100.0
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(QColor("#2563eb")))
    painter.drawRoundedRect(QRectF(0, 0, 100 * s, 100 * s), 22 * s, 22 * s)

    painter.setBrush(QBrush(QColor("white")))
    # camera body
    painter.drawRoundedRect(QRectF(18 * s, 32 * s, 64 * s, 44 * s), 8 * s, 8 * s)
    # viewfinder bump
    painter.drawRoundedRect(QRectF(38 * s, 24 * s, 24 * s, 12 * s), 4 * s, 4 * s)
    # lens
    painter.setBrush(QBrush(QColor("#2563eb")))
    painter.drawEllipse(QRectF(36 * s, 40 * s, 28 * s, 28 * s))
    painter.setBrush(QBrush(QColor("white")))
    painter.drawEllipse(QRectF(42 * s, 46 * s, 16 * s, 16 * s))
    painter.end()
    return QIcon(pixmap)
