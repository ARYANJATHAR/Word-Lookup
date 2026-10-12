"""Thin ctypes wrappers for the Windows features the app needs."""
import ctypes
import logging
import threading
import time
import winreg
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
user32.MonitorFromPoint.restype = wintypes.HMONITOR
user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetAncestor.restype = wintypes.HWND
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT]
user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
user32.RegisterClipboardFormatW.restype = wintypes.UINT
user32.GetClipboardSequenceNumber.restype = wintypes.DWORD
kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.CreateMutexW.restype = wintypes.HANDLE


def enable_dpi_awareness():
    """Render at native resolution instead of being bitmap-stretched (blurry) by Windows."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # system DPI aware
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass


def acquire_single_instance(name="Local\\WordLookup.SingleInstance"):
    """Return a mutex handle, or None if another instance already holds it."""
    handle = kernel32.CreateMutexW(None, False, name)
    if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
        return None
    return handle


def system_prefers_dark():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
            return winreg.QueryValueEx(key, "AppsUseLightTheme")[0] == 0
    except OSError:
        return False


# --- Window styling (Windows 11 rounded corners, dark title bar) ---

_DWMWA_USE_IMMERSIVE_DARK_MODE = 20
_DWMWA_WINDOW_CORNER_PREFERENCE = 33
_DWMWA_BORDER_COLOR = 34
_DWMWCP_ROUND = 2


def _hwnd(tk_window):
    return user32.GetAncestor(tk_window.winfo_id(), 2)  # GA_ROOT


def _dwm_set(hwnd, attribute, value):
    try:
        value = ctypes.c_int(value)
        return ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value)) == 0
    except Exception:
        return False


def _colorref(hex_color):
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    return r | (g << 8) | (b << 16)


def round_corners(tk_window, border_color=None):
    """Ask DWM for rounded corners. Returns False on Windows 10, where it isn't supported."""
    hwnd = _hwnd(tk_window)
    if not _dwm_set(hwnd, _DWMWA_WINDOW_CORNER_PREFERENCE, _DWMWCP_ROUND):
        return False
    if border_color:
        _dwm_set(hwnd, _DWMWA_BORDER_COLOR, _colorref(border_color))
    return True


def set_dark_title_bar(tk_window, dark):
    _dwm_set(_hwnd(tk_window), _DWMWA_USE_IMMERSIVE_DARK_MODE, 1 if dark else 0)


# --- Screen geometry ---

class _MonitorInfo(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]


def cursor_pos():
    pt = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def work_area_at(x, y):
    """(left, top, right, bottom) of the work area on the monitor nearest to the point."""
    monitor = user32.MonitorFromPoint(wintypes.POINT(x, y), 2)  # MONITOR_DEFAULTTONEAREST
    info = _MonitorInfo()
    info.cbSize = ctypes.sizeof(info)
    if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        return 0, 0, user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    r = info.rcWork
    return r.left, r.top, r.right, r.bottom


# --- Clipboard ---

_PRIVATE_FORMATS = [
    user32.RegisterClipboardFormatW("ExcludeClipboardContentFromMonitorProcessing"),
    user32.RegisterClipboardFormatW("Clipboard Viewer Ignore"),
]


def clipboard_sequence():
    return user32.GetClipboardSequenceNumber()


def clipboard_is_private():
    """True when the copying app (e.g. a password manager) asked monitors to ignore it."""
    return any(fmt and user32.IsClipboardFormatAvailable(fmt) for fmt in _PRIVATE_FORMATS)


_VK_SHIFT, _VK_CONTROL, _VK_MENU, _VK_LWIN, _VK_RWIN, _VK_C = 0x10, 0x11, 0x12, 0x5B, 0x5C, 0x43
_KEYEVENTF_KEYUP = 0x2


def copy_selection(timeout=0.5):
    """Press Ctrl+C for the user and return True if the clipboard changed."""
    # Wait for the user to let go of the hotkey's modifiers, or our Ctrl+C becomes Ctrl+Shift+C.
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline and any(
            user32.GetAsyncKeyState(vk) & 0x8000
            for vk in (_VK_SHIFT, _VK_CONTROL, _VK_MENU, _VK_LWIN, _VK_RWIN)):
        time.sleep(0.02)
    before = clipboard_sequence()
    user32.keybd_event(_VK_CONTROL, 0, 0, 0)
    user32.keybd_event(_VK_C, 0, 0, 0)
    user32.keybd_event(_VK_C, 0, _KEYEVENTF_KEYUP, 0)
    user32.keybd_event(_VK_CONTROL, 0, _KEYEVENTF_KEYUP, 0)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if clipboard_sequence() != before:
            time.sleep(0.05)  # let the source app finish writing all formats
            return True
        time.sleep(0.02)
    return False


# --- Global hotkey ---

_MOD_ALT, _MOD_CONTROL, _MOD_SHIFT, _MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x4000
_WM_HOTKEY, _WM_QUIT = 0x0312, 0x0012
_KEY_CODES = {"Space": 0x20}


def parse_hotkey(text):
    modifiers, vk = 0, None
    for part in text.split("+"):
        part = part.strip()
        if part == "Ctrl":
            modifiers |= _MOD_CONTROL
        elif part == "Shift":
            modifiers |= _MOD_SHIFT
        elif part == "Alt":
            modifiers |= _MOD_ALT
        elif part in _KEY_CODES:
            vk = _KEY_CODES[part]
        elif len(part) == 1:
            vk = ord(part.upper())
    if vk is None:
        raise ValueError(f"Unsupported hotkey: {text}")
    return modifiers, vk


class HotkeyListener(threading.Thread):
    """Registers a system-wide hotkey and calls `callback` (on this thread) when pressed."""

    def __init__(self, hotkey, callback):
        super().__init__(daemon=True, name="hotkey")
        self.hotkey = hotkey
        self.callback = callback
        self.registered = False
        self._ready = threading.Event()
        self._thread_id = None

    def start_and_wait(self):
        self.start()
        self._ready.wait(2)
        return self.registered

    def run(self):
        msg = wintypes.MSG()
        self._thread_id = kernel32.GetCurrentThreadId()
        user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)  # create this thread's message queue
        modifiers, vk = parse_hotkey(self.hotkey)
        self.registered = bool(user32.RegisterHotKey(None, 1, modifiers | _MOD_NOREPEAT, vk))
        if not self.registered:
            logging.error(f"Could not register hotkey {self.hotkey} (error {ctypes.get_last_error()})")
        self._ready.set()
        if not self.registered:
            return
        try:
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == _WM_HOTKEY:
                    try:
                        self.callback()
                    except Exception:
                        logging.exception("Hotkey handler failed")
        finally:
            user32.UnregisterHotKey(None, 1)

    def stop(self):
        if self._thread_id:
            user32.PostThreadMessageW(self._thread_id, _WM_QUIT, 0, 0)
