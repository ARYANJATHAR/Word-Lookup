import logging
import queue
import threading
import time
import tkinter as tk

import pyperclip
import pystray
from PIL import Image, ImageDraw

from wordlookup import APP_NAME, gemini, startup, winapi
from wordlookup.config import Settings, resource_path
from wordlookup.ui import PALETTES, Popup, SettingsWindow, Toolkit


class App:
    """Owns the single Tk main loop. Other threads hand work to it through `call`."""

    def __init__(self):
        self.settings = Settings()
        self.cache = gemini.Cache()
        self.root = tk.Tk()
        self.root.withdraw()
        self.kit = Toolkit(self.root)
        self.enabled = True
        self.popup = None
        self.settings_window = None
        self.icon = None
        self.hotkey = None
        self._queue = queue.Queue()
        self._stop = threading.Event()
        self._ignore_text = None
        self._lookup_id = 0

    # --- threading ---

    def call(self, fn, *args):
        """Run fn(*args) on the Tk thread. Safe to call from any thread."""
        self._queue.put((fn, args))

    def _drain_queue(self):
        while True:
            try:
                fn, args = self._queue.get_nowait()
            except queue.Empty:
                break
            try:
                fn(*args)
            except Exception:
                logging.exception(f"UI task {getattr(fn, '__name__', fn)} failed")
        if not self._stop.is_set():
            self.root.after(30, self._drain_queue)

    # --- lifecycle ---

    def run(self):
        self.root.after(30, self._drain_queue)
        if self.settings.api_key:
            self._start()
        else:
            logging.info("No API key yet, showing setup")
            self.open_settings(first_run=True)
        self.root.mainloop()
        logging.info("Application exited")

    def _start(self):
        self.icon = self._create_tray_icon()
        self.icon.run_detached()
        threading.Thread(target=self._monitor_clipboard, daemon=True, name="clipboard").start()
        self._restart_hotkey()
        if self.settings.get("trigger") == "hotkey":
            hint = f"Select a word and press {self.settings.get('hotkey')} to look it up."
        else:
            hint = "Copy any word to see its meaning."
        self.root.after(1500, lambda: self._notify(f"Running in the system tray. {hint}"))

    def quit(self):
        logging.info("Application exiting...")
        self._stop.set()
        if self.hotkey:
            self.hotkey.stop()
        if self.icon:
            self.icon.stop()
        self.root.quit()

    @property
    def palette(self):
        theme = self.settings.get("theme")
        if theme == "system":
            theme = "dark" if winapi.system_prefers_dark() else "light"
        return PALETTES.get(theme, PALETTES["light"])

    # --- lookups ---

    def _monitor_clipboard(self):
        last_seq = winapi.clipboard_sequence()
        while not self._stop.is_set():
            time.sleep(0.25)
            seq = winapi.clipboard_sequence()
            if seq == last_seq:
                continue
            last_seq = seq
            if not self.enabled or self.settings.get("trigger") != "clipboard":
                continue
            if winapi.clipboard_is_private():
                continue
            try:
                text = pyperclip.paste()
            except Exception as e:
                logging.warning(f"Could not read clipboard: {e}")
                continue
            if self._ignore_text is not None and text == self._ignore_text:
                self._ignore_text = None
                continue
            phrase = gemini.normalize_phrase(text)
            if phrase:
                self.call(self.lookup, phrase)

    def _on_hotkey(self):
        # Runs on the hotkey thread; copying the selection involves short waits.
        if not self.enabled:
            return
        winapi.copy_selection()
        try:
            text = pyperclip.paste()
        except Exception:
            text = ""
        phrase = gemini.normalize_phrase(text)
        if phrase:
            self.call(self.lookup, phrase)
        else:
            self.call(self.show_message, "Select 1–3 words first, then press the shortcut.")

    def _new_popup(self):
        if self.popup and self.popup.winfo_exists():
            self.popup.destroy()
        self.popup = Popup(self, winapi.cursor_pos())
        return self.popup

    def lookup(self, phrase):
        popup = self.popup
        if popup and popup.alive() and popup.mode == "loading" and popup.phrase == phrase:
            return  # same copy reported twice
        model = self.settings.get("model")
        cached = self.cache.get(model, phrase)
        popup = self._new_popup()
        if cached:
            popup.show_result(cached)
            self._refresh_menu()
            return

        popup.show_loading(phrase)
        self._lookup_id += 1
        lookup_id, api_key = self._lookup_id, self.settings.api_key

        def work():
            try:
                result = gemini.lookup(phrase, api_key, model)
                self.cache.put(model, result)
                self.call(self._lookup_done, lookup_id, phrase, result, None)
            except gemini.LookupFailed as e:
                self.call(self._lookup_done, lookup_id, phrase, None, str(e))
            except Exception as e:
                logging.exception("Lookup failed")
                self.call(self._lookup_done, lookup_id, phrase, None, f"Something went wrong: {e}")

        threading.Thread(target=work, daemon=True, name="lookup").start()

    def _lookup_done(self, lookup_id, phrase, result, error):
        self._refresh_menu()
        if lookup_id != self._lookup_id or not (self.popup and self.popup.alive()):
            return
        if result:
            self.popup.show_result(result)
        else:
            self.popup.show_error(phrase, error)

    def show_definition(self, definition):
        self._new_popup().show_result(definition)

    def show_message(self, message):
        self._new_popup().show_error(None, message, settings_link=False)

    def copy_to_clipboard(self, text):
        self._ignore_text = text  # don't look up our own copies
        try:
            pyperclip.copy(text)
        except Exception as e:
            logging.warning(f"Could not copy to clipboard: {e}")

    # --- settings ---

    def open_settings(self, first_run=False):
        if self.settings_window and self.settings_window.winfo_exists():
            self.settings_window.lift()
            self.settings_window.focus_force()
            return

        def closed(saved):
            self.settings_window = None
            if first_run:
                if saved:
                    self._start()
                else:
                    self.quit()

        self.settings_window = SettingsWindow(self, first_run=first_run, on_close=closed)

    def apply_settings(self, values):
        old_trigger, old_hotkey = self.settings.get("trigger"), self.settings.get("hotkey")
        if not self.settings.api_key_from_env and values["api_key"] != self.settings.api_key:
            self.settings.set_api_key(values["api_key"])
        self.settings.update(model=values["model"], trigger=values["trigger"], hotkey=values["hotkey"],
                             theme=values["theme"], popup_seconds=values["popup_seconds"])
        if values["startup"] != startup.is_enabled():
            startup.set_enabled(values["startup"])
        if self.icon and (values["trigger"], values["hotkey"]) != (old_trigger, old_hotkey):
            self._restart_hotkey()
        self._refresh_menu()

    def _restart_hotkey(self):
        if self.hotkey:
            self.hotkey.stop()
            self.hotkey = None
        if self.settings.get("trigger") != "hotkey":
            return
        hotkey = self.settings.get("hotkey")
        listener = winapi.HotkeyListener(hotkey, self._on_hotkey)
        if listener.start_and_wait():
            self.hotkey = listener
            logging.info(f"Hotkey {hotkey} registered")
        else:
            self._notify(f"{hotkey} is already used by another app. Pick a different shortcut in Settings.")

    # --- tray ---

    def _notify(self, message):
        if self.icon:
            try:
                self.icon.notify(message, APP_NAME)
            except Exception as e:
                logging.warning(f"Notification failed: {e}")

    def _refresh_menu(self):
        if self.icon:
            self.icon.update_menu()

    def _toggle_enabled(self):
        self.enabled = not self.enabled
        logging.info(f"Lookups {'resumed' if self.enabled else 'paused'}")
        self._notify("Lookups resumed." if self.enabled else "Lookups paused. Your clipboard is left alone.")
        self._refresh_menu()

    def _toggle_startup(self):
        target = not startup.is_enabled()
        if startup.set_enabled(target):
            self._notify("Word Lookup will start with Windows." if target else "Word Lookup won't start with Windows.")
        else:
            self._notify("Couldn't change the startup setting. See the log for details.")
        self._refresh_menu()

    def _recent_items(self):
        recent = self.cache.recent(8)
        if not recent:
            return [pystray.MenuItem("No lookups yet", None, enabled=False)]

        def opener(definition):  # pystray rejects callbacks with extra (default) arguments
            return lambda icon, item: self.call(self.show_definition, definition)

        return [pystray.MenuItem(d.phrase, opener(d)) for d in recent]

    def _create_tray_icon(self):
        icon_path = resource_path("app_icon.ico")
        if icon_path:
            image = Image.open(icon_path)
        else:
            logging.warning("app_icon.ico not found, drawing a fallback icon")
            image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
            ImageDraw.Draw(image).rounded_rectangle((4, 4, 60, 60), radius=14, fill="#2f5bea")

        menu = pystray.Menu(
            pystray.MenuItem(lambda item: "Pause lookups" if self.enabled else "Resume lookups",
                             lambda icon, item: self.call(self._toggle_enabled), default=True),
            pystray.MenuItem("Recent lookups", pystray.Menu(self._recent_items)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Settings…", lambda icon, item: self.call(self.open_settings)),
            pystray.MenuItem("Start with Windows", lambda icon, item: self.call(self._toggle_startup),
                             checked=lambda item: startup.is_enabled()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit", lambda icon, item: self.call(self.quit)),
        )
        return pystray.Icon(APP_NAME, image, APP_NAME, menu)
