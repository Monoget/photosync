"""Start-with-Windows via the per-user Run registry key (no admin needed)."""
from __future__ import annotations

import logging
import sys

log = logging.getLogger(__name__)

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "PixSynq"


def _command() -> str:
    if getattr(sys, "frozen", False):  # PyInstaller build
        return f'"{sys.executable}"'
    main_py = sys.argv[0]
    return f'"{sys.executable}" "{main_py}"'


def set_start_with_windows(enable: bool, key_path: str = RUN_KEY) -> bool:
    try:
        import winreg
    except ImportError:  # non-Windows dev machine
        return False
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            if enable:
                winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, _command())
            else:
                try:
                    winreg.DeleteValue(key, VALUE_NAME)
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        log.exception("Could not update startup setting")
        return False


def is_start_with_windows(key_path: str = RUN_KEY) -> bool:
    try:
        import winreg
    except ImportError:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            winreg.QueryValueEx(key, VALUE_NAME)
            return True
    except OSError:
        return False
