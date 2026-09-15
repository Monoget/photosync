"""Phase 9 tests: version comparison and update-check logic."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from core.services.update_checker import UpdateChecker  # noqa: E402
from core.services.version import is_newer, parse_version  # noqa: E402
from infrastructure.configuration.settings_store import SettingsStore  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.mark.parametrize(
    "a,b,newer",
    [
        ("1.10.0", "1.9.0", True),     # spec §23 example
        ("1.9.0", "1.10.0", False),
        ("2.0.0", "1.99.99", True),
        ("1.0.0", "1.0.0", False),
        ("1.0.1", "1.0.0", True),
        ("v1.2.0", "1.1.9", True),
        ("1.2", "1.2.0", False),
    ],
)
def test_is_newer(a, b, newer):
    assert is_newer(a, b) is newer


def test_parse_version_tolerates_garbage():
    assert parse_version("1.2.3-beta") == (1, 2, 3)
    assert parse_version("nonsense") == (0,)


def make_checker(tmp_path, current, response, monkeypatch):
    settings = SettingsStore(tmp_path / "settings.json")
    settings.set("update_base_url", "https://updates.example")
    return settings, UpdateChecker(
        settings, current, fetch=lambda _url: response
    )


def test_checker_emits_for_newer_version(qapp, tmp_path, monkeypatch):
    settings, checker = make_checker(
        tmp_path, "1.0.0", {"version": "1.1.0", "sha256": "x"}, monkeypatch
    )
    seen = []
    checker.update_available.connect(seen.append)
    info = checker.check()
    assert info["version"] == "1.1.0"
    assert seen and seen[0]["version"] == "1.1.0"


def test_checker_silent_for_same_or_older(qapp, tmp_path, monkeypatch):
    _, checker = make_checker(tmp_path, "1.1.0", {"version": "1.1.0"}, monkeypatch)
    assert checker.check() is None
    _, checker = make_checker(tmp_path, "1.2.0", {"version": "1.1.0"}, monkeypatch)
    assert checker.check() is None


def test_checker_respects_skipped_version(qapp, tmp_path, monkeypatch):
    settings, checker = make_checker(
        tmp_path, "1.0.0", {"version": "1.1.0"}, monkeypatch
    )
    checker.skip_version("1.1.0")
    assert checker.check() is None
    # …but a mandatory release overrides the skip
    settings2, checker2 = make_checker(
        tmp_path, "1.0.0", {"version": "1.1.0", "mandatory": True}, monkeypatch
    )
    checker2.skip_version("1.1.0")
    assert checker2.check() is not None


def test_checker_disabled_without_base_url(qapp, tmp_path, monkeypatch):
    monkeypatch.delenv("UPDATE_BASE_URL", raising=False)
    monkeypatch.delenv("API_BASE_URL", raising=False)
    settings = SettingsStore(tmp_path / "settings.json")
    checker = UpdateChecker(settings, "1.0.0", fetch=lambda _u: {"version": "9.0.0"})
    assert not checker.enabled
    assert checker.check() is None


def test_checker_survives_server_failure(qapp, tmp_path, monkeypatch):
    _, checker = make_checker(tmp_path, "1.0.0", None, monkeypatch)
    assert checker.check() is None  # no crash, no emit
