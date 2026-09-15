"""Phase 1 smoke tests: the app shell constructs without a display."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from infrastructure.configuration.paths import AppPaths  # noqa: E402
from ui.styles.theme import Theme, apply_theme  # noqa: E402
from ui.windows.main_window import MainWindow  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_main_window_builds_all_pages(qapp):
    apply_theme(qapp, Theme.DARK)
    window = MainWindow(app_version="0.1.0-test")
    assert window._pages.count() == 5
    titles = [b.text() for b in window._nav_group.buttons()]
    assert titles == ["Dashboard", "Devices", "Backup History", "Settings", "About"]


def test_nav_switches_pages(qapp):
    window = MainWindow(app_version="0.1.0-test")
    buttons = window._nav_group.buttons()
    buttons[3].click()
    assert window._pages.currentIndex() == 3


def test_light_theme_applies(qapp):
    apply_theme(qapp, Theme.LIGHT)
    assert "#" in qapp.styleSheet()


def test_app_paths_are_per_user(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    paths = AppPaths.default()
    assert paths.data_dir == tmp_path / "PhotoSync"
    paths.ensure()
    assert paths.logs_dir.is_dir()
