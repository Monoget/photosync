"""Phase 11 tests: start-with-Windows registry toggle (isolated test key)."""
import sys

import pytest

from infrastructure.configuration.startup import (
    is_start_with_windows,
    set_start_with_windows,
)

TEST_KEY = r"Software\PixSynqTest\Run"

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="Windows registry only"
)


@pytest.fixture(autouse=True)
def cleanup():
    yield
    import winreg

    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, TEST_KEY)
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, r"Software\PixSynqTest")
    except OSError:
        pass


def test_startup_toggle_roundtrip():
    assert not is_start_with_windows(TEST_KEY)
    assert set_start_with_windows(True, TEST_KEY)
    assert is_start_with_windows(TEST_KEY)
    assert set_start_with_windows(False, TEST_KEY)
    assert not is_start_with_windows(TEST_KEY)


def test_disable_when_never_enabled_is_fine():
    assert set_start_with_windows(False, TEST_KEY)
