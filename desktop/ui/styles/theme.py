"""Application theming: light and dark palettes applied via QSS.

All colors are defined as tokens so both themes share one stylesheet
template and widgets never hardcode colors.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from PySide6.QtWidgets import QApplication


class Theme(Enum):
    LIGHT = "light"
    DARK = "dark"


@dataclass(frozen=True)
class Tokens:
    bg: str
    surface: str
    surface_alt: str
    border: str
    text: str
    text_muted: str
    accent: str
    accent_hover: str
    accent_text: str
    success: str
    danger: str
    sidebar_bg: str
    sidebar_item_hover: str
    sidebar_item_active: str


LIGHT = Tokens(
    bg="#f4f6f8",
    surface="#ffffff",
    surface_alt="#eef1f4",
    border="#dde3e9",
    text="#1a2330",
    text_muted="#5f6b7a",
    accent="#2563eb",
    accent_hover="#1d4ed8",
    accent_text="#ffffff",
    success="#16a34a",
    danger="#dc2626",
    sidebar_bg="#eaeef2",
    sidebar_item_hover="#dde3ea",
    sidebar_item_active="#d3dcf5",
)

DARK = Tokens(
    bg="#12161c",
    surface="#1a2029",
    surface_alt="#212936",
    border="#2c3644",
    text="#e8ecf1",
    text_muted="#93a0b0",
    accent="#3b82f6",
    accent_hover="#2f6fe0",
    accent_text="#ffffff",
    success="#22c55e",
    danger="#ef4444",
    sidebar_bg="#161b22",
    sidebar_item_hover="#1f2731",
    sidebar_item_active="#24304a",
)


STYLESHEET = """
* {{
    font-family: "Segoe UI Variable", "Segoe UI", sans-serif;
    font-size: 14px;
}}
QMainWindow, QDialog, QWidget#appRoot {{
    background: {bg};
}}
QLineEdit {{
    background: {surface_alt};
    color: {text};
    border: 1px solid {border};
    border-radius: 6px;
    padding: 7px 10px;
    selection-background-color: {accent};
}}
QLineEdit:focus {{
    border-color: {accent};
}}
QCheckBox {{
    color: {text};
    spacing: 8px;
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {border};
    border-radius: 4px;
    background: {surface_alt};
}}
QCheckBox::indicator:checked {{
    background: {accent};
    border-color: {accent};
}}
QComboBox {{
    background: {surface_alt};
    color: {text};
    border: 1px solid {border};
    border-radius: 6px;
    padding: 6px 10px;
    min-width: 140px;
}}
QComboBox QAbstractItemView {{
    background: {surface};
    color: {text};
    border: 1px solid {border};
    selection-background-color: {accent};
}}
QLabel {{
    color: {text};
    background: transparent;
}}
QLabel[class="muted"] {{
    color: {text_muted};
}}
QLabel[class="pageTitle"] {{
    font-size: 22px;
    font-weight: 600;
}}
QLabel[class="cardTitle"] {{
    font-size: 12px;
    font-weight: 600;
    color: {text_muted};
    letter-spacing: 1px;
}}
QLabel[class="statValue"] {{
    font-size: 26px;
    font-weight: 600;
}}
QFrame[class="card"] {{
    background: {surface};
    border: 1px solid {border};
    border-radius: 10px;
}}
QPushButton {{
    background: {surface_alt};
    color: {text};
    border: 1px solid {border};
    border-radius: 6px;
    padding: 7px 16px;
}}
QPushButton:hover {{
    border-color: {accent};
}}
QPushButton[class="primary"] {{
    background: {accent};
    color: {accent_text};
    border: none;
    font-weight: 600;
}}
QPushButton[class="primary"]:hover {{
    background: {accent_hover};
}}
QWidget#sidebar {{
    background: {sidebar_bg};
    border-right: 1px solid {border};
}}
QPushButton[class="navItem"] {{
    background: transparent;
    border: none;
    border-radius: 8px;
    padding: 10px 14px;
    text-align: left;
    color: {text_muted};
}}
QPushButton[class="navItem"]:hover {{
    background: {sidebar_item_hover};
    color: {text};
}}
QPushButton[class="navItem"]:checked {{
    background: {sidebar_item_active};
    color: {text};
    font-weight: 600;
}}
QProgressBar {{
    background: {surface_alt};
    border: none;
    border-radius: 5px;
    height: 10px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{
    background: {accent};
    border-radius: 5px;
}}
"""


def tokens_for(theme: Theme) -> Tokens:
    return DARK if theme is Theme.DARK else LIGHT


def apply_theme(app: QApplication, theme: Theme) -> None:
    t = tokens_for(theme)
    app.setStyleSheet(STYLESHEET.format(**t.__dict__))
