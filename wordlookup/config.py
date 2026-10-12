import base64
import ctypes
import json
import logging
import os
import sys
import threading
from ctypes import wintypes
from pathlib import Path

from wordlookup import APP_NAME

DEFAULT_MODEL = "gemini-flash-lite-latest"
# The "-latest" aliases follow Google's newest model, so they don't break when old versions retire.
MODEL_CHOICES = [
    "gemini-flash-lite-latest",
    "gemini-flash-latest",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
]
HOTKEY_CHOICES = ["Ctrl+Shift+D", "Ctrl+Shift+L", "Ctrl+Shift+Space", "Ctrl+Alt+D"]
THEME_CHOICES = ["system", "light", "dark"]
DURATION_CHOICES = [4, 6, 8, 10, 15, 20, 30]

DEFAULTS = {
    "model": DEFAULT_MODEL,
    "trigger": "clipboard",      # "clipboard" or "hotkey"
    "hotkey": "Ctrl+Shift+D",
    "popup_seconds": 8,
    "theme": "system",
}


def app_data_dir():
    path = Path(os.getenv("APPDATA") or Path.home()) / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def app_dir():
    """Folder holding the exe (frozen) or the project root (source)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def resource_path(name):
    """Locate a bundled resource such as the icon, in PyInstaller or source layouts."""
    candidates = []
    if hasattr(sys, "_MEIPASS"):
        candidates.append(Path(sys._MEIPASS) / name)
    candidates.append(app_dir() / name)
    for path in candidates:
        if path.exists():
            return path
    return None


# --- Windows DPAPI: encrypts data so only the current Windows user can decrypt it ---

class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


_crypt32 = ctypes.windll.crypt32
_kernel32 = ctypes.windll.kernel32
_kernel32.LocalFree.argtypes = [ctypes.c_void_p]
_kernel32.LocalFree.restype = ctypes.c_void_p
_CRYPTPROTECT_UI_FORBIDDEN = 0x1


def _dpapi(data, decrypt=False):
    buffer = ctypes.create_string_buffer(data, len(data))
    blob_in = _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
    blob_out = _DataBlob()
    fn = _crypt32.CryptUnprotectData if decrypt else _crypt32.CryptProtectData
    if not fn(ctypes.byref(blob_in), None, None, None, None,
              _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(blob_out)):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        _kernel32.LocalFree(ctypes.cast(blob_out.pbData, ctypes.c_void_p))


def protect(text):
    return base64.b64encode(_dpapi(text.encode("utf-8"))).decode("ascii")


def unprotect(token):
    return _dpapi(base64.b64decode(token), decrypt=True).decode("utf-8")


class Settings:
    """Thread-safe settings stored in %APPDATA%/Word Lookup/config.json."""

    def __init__(self):
        self._path = app_data_dir() / "config.json"
        self._lock = threading.Lock()
        self._data = dict(DEFAULTS)
        self._load()

    def _load(self):
        if not self._path.exists():
            return
        try:
            stored = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception as e:
            logging.warning(f"Could not read settings, using defaults: {e}")
            return
        if "api_key" in stored and "api_key_protected" not in stored:
            # v1 stored a Fernet token next to its own key file; it can't be migrated
            # without bundling cryptography, so the user is asked for the key once.
            logging.info("Found v1 API key; asking for it again to store it securely")
        stored.pop("api_key", None)
        self._data.update(stored)
        legacy_key_file = app_data_dir() / ".key"
        if legacy_key_file.exists():
            try:
                legacy_key_file.unlink()
            except OSError:
                pass

    def _save(self):
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
        os.replace(tmp, self._path)

    def get(self, name):
        with self._lock:
            return self._data.get(name, DEFAULTS.get(name))

    def update(self, **values):
        with self._lock:
            self._data.update(values)
            self._save()

    @property
    def api_key_from_env(self):
        return os.getenv("GEMINI_API_KEY", "").strip()

    @property
    def api_key(self):
        if self.api_key_from_env:
            return self.api_key_from_env
        token = self.get("api_key_protected")
        if not token:
            return ""
        try:
            return unprotect(token)
        except Exception as e:
            logging.warning(f"Stored API key could not be decrypted: {e}")
            return ""

    def set_api_key(self, key):
        self.update(api_key_protected=protect(key) if key else "")
