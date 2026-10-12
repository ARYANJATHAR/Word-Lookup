import ctypes
import logging
import re
import sys
from logging.handlers import RotatingFileHandler

from dotenv import load_dotenv

from wordlookup import APP_NAME, VERSION, winapi
from wordlookup.config import app_data_dir, app_dir


class SensitiveFormatter(logging.Formatter):
    _patterns = [re.compile(p) for p in (r"GEMINI_API_KEY=\S*", r"key=[^\s&]*", r"AIza[0-9A-Za-z_\-]{20,}", r"AQ\.[0-9A-Za-z_\-]{20,}")]

    def format(self, record):
        message = super().format(record)
        for pattern in self._patterns:
            message = pattern.sub("[REDACTED]", message)
        return message


def setup_logging():
    formatter = SensitiveFormatter("%(asctime)s - %(levelname)s - %(threadName)s - %(message)s")
    handlers = [RotatingFileHandler(app_data_dir() / "word_lookup.log", maxBytes=1_000_000,
                                    backupCount=2, encoding="utf-8")]
    if sys.stdout:  # None in the windowed PyInstaller build
        handlers.append(logging.StreamHandler(sys.stdout))
    for handler in handlers:
        handler.setFormatter(formatter)
    logging.basicConfig(level=logging.INFO, handlers=handlers)


def main():
    setup_logging()
    logging.info(f"Starting {APP_NAME} {VERSION}")
    winapi.enable_dpi_awareness()  # must happen before any window is created

    mutex = winapi.acquire_single_instance()
    if not mutex:
        logging.info("Another instance is already running")
        ctypes.windll.user32.MessageBoxW(
            None, "Word Lookup is already running.\nLook for its icon in the system tray.", APP_NAME, 0x40)
        return 0

    load_dotenv(app_dir() / ".env")

    from wordlookup.app import App
    try:
        App().run()
    except Exception:
        logging.exception("Fatal error")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
