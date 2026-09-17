"""Phase 2 tests: settings persistence, installation ID, validation, wizard."""
import json
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from core.services.registration import (  # noqa: E402
    RegistrationInput,
    validate_registration,
)
from infrastructure.configuration.settings_store import SettingsStore  # noqa: E402
from infrastructure.storage.destination import validate_destination  # noqa: E402
from ui.dialogs.setup_wizard import SetupWizard  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


# -- SettingsStore -----------------------------------------------------


def test_settings_roundtrip(tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    store.set("foo", {"bar": 1})
    reloaded = SettingsStore(tmp_path / "settings.json")
    assert reloaded.get("foo") == {"bar": 1}


def test_installation_id_is_stable_uuid(tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    first = store.installation_id
    assert len(first) == 36
    assert SettingsStore(tmp_path / "settings.json").installation_id == first


def test_corrupt_settings_recovers(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{not json", encoding="utf-8")
    store = SettingsStore(path)
    assert store.get("anything") is None
    store.set("k", "v")
    assert json.loads(path.read_text(encoding="utf-8")) == {"k": "v"}


# -- Registration validation ------------------------------------------


def test_registration_valid():
    reg = RegistrationInput("Ada Lovelace", "ada@example.com", True)
    assert validate_registration(reg) == []


@pytest.mark.parametrize(
    "name,email,consent",
    [
        ("", "ada@example.com", True),
        ("Ada", "not-an-email", True),
        ("Ada", "ada@example.com", False),
    ],
)
def test_registration_invalid(name, email, consent):
    assert validate_registration(RegistrationInput(name, email, consent))


# -- Destination validation -------------------------------------------


def test_destination_created_and_writable(tmp_path):
    target = tmp_path / "new" / "PixSynq"
    check = validate_destination(target)
    assert check.ok
    assert target.is_dir()


def test_destination_invalid_path():
    assert not validate_destination(Path("")).ok


def test_destination_rejects_file_in_the_way(tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("I am a file")
    assert not validate_destination(blocker / "sub").ok


# -- Wizard flow -------------------------------------------------------


def test_wizard_full_flow(qapp, tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    wizard = SetupWizard(store)

    wizard._next()  # welcome -> register
    wizard.name_edit.setText("Ada Lovelace")
    wizard.email_edit.setText("ada@example.com")
    wizard.consent_box.setChecked(True)
    wizard._submit_registration()
    assert wizard._stack.currentIndex() == 2

    wizard._destination = tmp_path / "photos"
    wizard._submit_folder()
    assert wizard._stack.currentIndex() == 3

    wizard.accept()
    assert store.setup_complete
    assert store.destination_dir == tmp_path / "photos"
    reg = store.get("registration")
    assert reg["email"] == "ada@example.com"
    assert reg["upload_status"] == "pending"


def test_wizard_blocks_invalid_registration(qapp, tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    wizard = SetupWizard(store)
    wizard._next()
    wizard.name_edit.setText("")
    wizard._submit_registration()
    assert wizard._stack.currentIndex() == 1
    assert wizard.register_error.text()
