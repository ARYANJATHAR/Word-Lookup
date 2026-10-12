"""Run-at-login via HKCU\\...\\Run, which needs no admin rights."""
import logging
import sys
import winreg
from pathlib import Path

from wordlookup import APP_NAME
from wordlookup.config import app_dir

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def launch_command():
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    interpreter = pythonw if pythonw.exists() else Path(sys.executable)
    return f'"{interpreter}" "{app_dir() / "main.py"}"'


def is_enabled():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, APP_NAME)
            return True
    except OSError:
        return False


def set_enabled(enabled):
    try:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, launch_command())
            elif is_enabled():
                winreg.DeleteValue(key, APP_NAME)
        logging.info(f"Run at startup {'enabled' if enabled else 'disabled'}")
        return True
    except OSError as e:
        logging.error(f"Could not change startup setting: {e}")
        return False
