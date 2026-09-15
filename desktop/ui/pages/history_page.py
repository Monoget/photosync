"""Backup history page: recent completed transfers from the database."""
from __future__ import annotations

from datetime import datetime

from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from infrastructure.database.db import PhotoStore
from ui.pages.base_page import BasePage
from ui.widgets.card import Card


def _fmt_size(size: int | None) -> str:
    value = float(size or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{value:.1f} GB"


class HistoryPage(BasePage):
    def __init__(self, photo_store: PhotoStore | None = None) -> None:
        super().__init__("Backup History")
        self._photos = photo_store

        card = Card()
        self._list_host = QWidget()
        self._list_layout = QVBoxLayout(self._list_host)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(8)
        card.add(self._list_host)
        self.body.addWidget(card)

        self.finish()
        self.refresh()

    def on_photo_received(self, _filename: str) -> None:
        self.refresh()

    def refresh(self) -> None:
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()

        rows = self._photos.recent(200) if self._photos else []
        if not rows:
            empty = QLabel("No backups yet")
            hint = QLabel("Completed transfers will appear here.")
            hint.setProperty("class", "muted")
            self._list_layout.addWidget(empty)
            self._list_layout.addWidget(hint)
            return

        for row in rows:
            self._list_layout.addWidget(self._row_widget(row))

    def _row_widget(self, row) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        text = QVBoxLayout()
        name = QLabel(row["filename"])
        when = row["completed_at"] or ""
        try:
            when = datetime.fromisoformat(when).astimezone().strftime("%Y-%m-%d %H:%M")
        except ValueError:
            pass
        detail = QLabel(
            f"{row['device_name'] or 'Unknown device'}  •  "
            f"{_fmt_size(row['file_size'])}  •  {when}"
        )
        detail.setProperty("class", "muted")
        text.addWidget(name)
        text.addWidget(detail)
        layout.addLayout(text, stretch=1)
        return widget
