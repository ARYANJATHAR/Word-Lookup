import logging
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
import tkinter.messagebox
import webbrowser
from tkinter import ttk
from types import SimpleNamespace

from PIL import Image, ImageDraw, ImageTk

from wordlookup import APP_NAME, VERSION, gemini, startup, winapi
from wordlookup.config import (DURATION_CHOICES, HOTKEY_CHOICES, MODEL_CHOICES,
                               THEME_CHOICES, resource_path)

API_KEY_URL = "https://aistudio.google.com/apikey"

PALETTES = {
    "light": SimpleNamespace(
        dark=False, bg="#ffffff", surface="#f3f4f7", hover="#e8eaf0", border="#dcdfe6",
        text="#1b1c20", muted="#636875", accent="#2f5bea", accent_hover="#2449c4",
        on_accent="#ffffff", chip="#eef2ff", chip_hover="#dce4ff", chip_text="#2442b0",
        error="#c62828", success="#1e8e3e"),
    "dark": SimpleNamespace(
        dark=True, bg="#1e1f24", surface="#2a2c33", hover="#34363f", border="#3b3e48",
        text="#f1f2f5", muted="#9da2ae", accent="#7c9cff", accent_hover="#9bb3ff",
        on_accent="#0d1230", chip="#2c3350", chip_hover="#384170", chip_text="#cdd8ff",
        error="#ff8a80", success="#7ee2a8"),
}

# Segoe Fluent Icons (Windows 11) / Segoe MDL2 Assets (Windows 10) glyphs
ICON_CLOSE, ICON_COPY, ICON_EYE = "", "", ""


def make_fonts(root):
    families = set(tkfont.families(root))
    ui = "Segoe UI Variable Text" if "Segoe UI Variable Text" in families else "Segoe UI"
    display = "Segoe UI Variable Display" if "Segoe UI Variable Display" in families else ui
    icons = next((f for f in ("Segoe Fluent Icons", "Segoe MDL2 Assets") if f in families), None)
    return SimpleNamespace(
        title=tkfont.Font(root, family=display, size=15, weight="bold"),
        heading=tkfont.Font(root, family=display, size=14, weight="bold"),
        pos=tkfont.Font(root, family=ui, size=10, slant="italic"),
        body=tkfont.Font(root, family=ui, size=11),
        example=tkfont.Font(root, family=ui, size=10, slant="italic"),
        small=tkfont.Font(root, family=ui, size=9),
        caption=tkfont.Font(root, family=ui, size=8, weight="bold"),
        chip=tkfont.Font(root, family=ui, size=10),
        button=tkfont.Font(root, family=ui, size=10, weight="bold"),
        link=tkfont.Font(root, family=ui, size=9, underline=True),
        icon=tkfont.Font(root, family=icons, size=9) if icons else tkfont.Font(root, family=ui, size=11),
        has_icon_font=icons is not None,
    )


class Toolkit:
    """Shared look-and-feel helpers bound to the app's Tk root."""

    def __init__(self, root):
        self.root = root
        self.fonts = make_fonts(root)
        self.scale = root.winfo_fpixels("1i") / 96.0
        self._pills = {}

    def px(self, n):
        return int(round(n * self.scale))

    def pill(self, width, height, fill, background, radius=None):
        """An anti-aliased rounded rectangle image (Tk's own canvas shapes are jagged)."""
        radius = height // 2 if radius is None else radius
        key = (width, height, fill, background, radius)
        if key not in self._pills:
            ss = 4
            image = Image.new("RGB", (width * ss, height * ss), background)
            ImageDraw.Draw(image).rounded_rectangle(
                (0, 0, width * ss - 1, height * ss - 1), radius=radius * ss, fill=fill)
            image = image.resize((width, height), Image.LANCZOS)
            self._pills[key] = ImageTk.PhotoImage(image, master=self.root)
        return self._pills[key]

    def icon_glyph(self, glyph, fallback):
        return glyph if self.fonts.has_icon_font else fallback

    def icon_button(self, parent, p, glyph, fallback, command, bg=None):
        bg = bg or p.bg
        label = tk.Label(parent, text=self.icon_glyph(glyph, fallback), font=self.fonts.icon,
                         fg=p.muted, bg=bg, cursor="hand2", padx=self.px(6), pady=self.px(4))
        label.bind("<Enter>", lambda e: label.configure(bg=p.hover, fg=p.text))
        label.bind("<Leave>", lambda e: label.configure(bg=bg, fg=p.muted))
        label.bind("<ButtonRelease-1>", lambda e: command())
        return label

    def pill_button(self, parent, p, text, command, primary=True, min_width=88):
        font = self.fonts.button
        width = max(self.px(min_width), font.measure(text) + self.px(32))
        height = font.metrics("linespace") + self.px(14)
        fill, hover, fg = (p.accent, p.accent_hover, p.on_accent) if primary else (p.surface, p.hover, p.text)
        normal_img = self.pill(width, height, fill, p.bg, radius=self.px(8))
        hover_img = self.pill(width, height, hover, p.bg, radius=self.px(8))
        button = tk.Label(parent, image=normal_img, text=text, compound="center", font=font,
                          fg=fg, bg=p.bg, bd=0, cursor="hand2")
        button.enabled = True

        def set_enabled(enabled):
            button.enabled = enabled
            button.configure(cursor="hand2" if enabled else "arrow", fg=fg if enabled else p.muted)

        button.set_enabled = set_enabled
        button.bind("<Enter>", lambda e: button.enabled and button.configure(image=hover_img))
        button.bind("<Leave>", lambda e: button.configure(image=normal_img))
        button.bind("<ButtonRelease-1>", lambda e: button.enabled and command())
        return button

    def link(self, parent, p, text, command):
        label = tk.Label(parent, text=text, font=self.fonts.link, fg=p.accent, bg=p.bg, cursor="hand2")
        label.bind("<ButtonRelease-1>", lambda e: command())
        return label


class Popup(tk.Toplevel):
    """Borderless definition card shown next to the mouse cursor."""

    WIDTH = 344
    FADE_IN, FADE_OUT, OPACITY = 0.12, 0.16, 0.98

    def __init__(self, app, anchor):
        super().__init__(app.root)
        self.app, self.kit, self.p = app, app.kit, app.palette
        self.f, px = self.kit.fonts, self.kit.px
        self.anchor = anchor
        self.mode = None
        self.phrase = None
        self._alpha = 0.0
        self._closing = False
        self._moved = False
        self._drag = None
        self._duration = self._remaining = 1.0
        self._phase = 0.0
        self._last_tick = time.monotonic()
        self._status_after = None

        self.withdraw()
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.attributes("-alpha", 0.0)
        self.configure(bg=self.p.border)

        self.inner = tk.Frame(self, bg=self.p.bg)
        self.inner.pack(fill="both", expand=True, padx=1, pady=1)
        self.content = tk.Frame(self.inner, bg=self.p.bg)
        self.content.pack(fill="both", expand=True, padx=px(18), pady=(px(12), px(14)))
        self.bar = tk.Canvas(self.inner, height=px(3), bg=self.p.bg, highlightthickness=0, bd=0)
        self.bar.pack(fill="x", side="bottom")
        self._bar_rect = self.bar.create_rectangle(0, 0, 0, px(3), fill=self.p.accent, width=0)
        self._make_draggable(self.inner, self.content)

        self.update_idletasks()
        if winapi.round_corners(self, self.p.border):
            self.inner.pack_configure(padx=0, pady=0)  # DWM draws the border on Windows 11
        self._tick()

    # --- states ---

    def show_loading(self, phrase):
        self.phrase = phrase
        self._reset("loading")
        self._header(phrase)
        self._loading_label = tk.Label(self.content, text="Looking up", font=self.f.body,
                                       fg=self.p.muted, bg=self.p.bg)
        self._loading_label.pack(anchor="w", pady=(self.kit.px(6), 0))
        self._make_draggable(self._loading_label)
        self._show()

    def show_result(self, d):
        px, p = self.kit.px, self.p
        self.phrase = d.phrase
        self._reset("result")
        self._header(d.phrase, d.part_of_speech, copy_text=f"{d.phrase}: {d.meaning}")
        wrap = px(self.WIDTH - 36)
        if d.pronunciation:
            self._text(f"/{d.pronunciation}/", self.f.small, p.muted, wrap).pack(anchor="w")
        tk.Frame(self.content, bg=p.border, height=1).pack(fill="x", pady=(px(10), px(10)))
        self._text(d.meaning or "No definition found.", self.f.body, p.text, wrap).pack(anchor="w")

        if d.example:
            example = tk.Frame(self.content, bg=p.bg)
            example.pack(fill="x", pady=(px(10), 0))
            tk.Frame(example, bg=p.accent, width=px(3)).pack(side="left", fill="y")
            self._text(d.example, self.f.example, p.muted, wrap - px(14), parent=example) \
                .pack(side="left", padx=(px(10), 0), pady=px(1))
            self._make_draggable(example)

        if d.synonyms:
            self._text("SYNONYMS", self.f.caption, p.muted).pack(anchor="w", pady=(px(14), px(6)))
            self._chips(d.synonyms, wrap)
            hint = "Click a synonym to copy it"
        else:
            hint = ""
        self._status = self._text(hint, self.f.small, p.muted)
        self._status.pack(anchor="w", pady=(px(10), 0))
        self._start_countdown()
        self._show()

    def show_error(self, phrase, message, settings_link=True):
        px, p = self.kit.px, self.p
        self.phrase = phrase
        self._reset("error")
        self._header(phrase or APP_NAME)
        self._text(message, self.f.body, p.error, px(self.WIDTH - 36)).pack(anchor="w", pady=(px(6), 0))
        if settings_link:
            self.kit.link(self.content, p, "Open Settings", self.app.open_settings).pack(anchor="w", pady=(px(8), 0))
        self._start_countdown()
        self._show()

    def close(self):
        self._closing = True

    def alive(self):
        return not self._closing and self.winfo_exists()

    # --- building blocks ---

    def _reset(self, mode):
        self.mode = mode
        for child in self.content.winfo_children():
            child.destroy()
        # Fixed-width spacer so the card keeps its width whatever the content.
        tk.Frame(self.content, bg=self.p.bg, width=self.kit.px(self.WIDTH - 36), height=0).pack()

    def _text(self, text, font, fg, wrap=0, parent=None):
        label = tk.Label(parent or self.content, text=text, font=font, fg=fg, bg=self.p.bg,
                         justify="left", anchor="w", wraplength=wrap)
        self._make_draggable(label)
        return label

    def _header(self, phrase, part_of_speech="", copy_text=None):
        px, p = self.kit.px, self.p
        row = tk.Frame(self.content, bg=p.bg)
        row.pack(fill="x")
        self.kit.icon_button(row, p, ICON_CLOSE, "✕", self.close).pack(side="right", anchor="n")
        if copy_text:
            self.kit.icon_button(row, p, ICON_COPY, "⧉", lambda: self._copy(copy_text, "Definition copied")) \
                .pack(side="right", anchor="n")
        title = tk.Label(row, text=phrase, font=self.f.title, fg=p.text, bg=p.bg,
                         justify="left", wraplength=px(self.WIDTH - 130))
        title.pack(side="left", anchor="w")
        self._make_draggable(row, title)
        if part_of_speech:
            pos = tk.Label(row, text=part_of_speech, font=self.f.pos, fg=p.muted, bg=p.bg)
            pos.pack(side="left", anchor="s", padx=(px(8), 0), pady=(0, px(4)))
            self._make_draggable(pos)

    def _chips(self, words, max_width):
        px, p, font = self.kit.px, self.p, self.f.chip
        gap, height = px(6), font.metrics("linespace") + px(8)
        row, used = None, max_width
        for word in words:
            width = font.measure(word) + px(22)
            if used + width > max_width:
                row = tk.Frame(self.content, bg=p.bg)
                row.pack(anchor="w", pady=(0, gap))
                self._make_draggable(row)
                used = 0
            normal, hover = self.kit.pill(width, height, p.chip, p.bg), self.kit.pill(width, height, p.chip_hover, p.bg)
            chip = tk.Label(row, image=normal, text=word, compound="center", font=font,
                            fg=p.chip_text, bg=p.bg, bd=0, cursor="hand2")
            chip.pack(side="left", padx=(0 if used == 0 else gap, 0))
            chip.bind("<Enter>", lambda e, c=chip, i=hover: c.configure(image=i))
            chip.bind("<Leave>", lambda e, c=chip, i=normal: c.configure(image=i))
            chip.bind("<ButtonRelease-1>", lambda e, w=word: self._copy(w, f"Copied “{w}”"))
            used += width + (0 if used == 0 else gap)

    def _copy(self, text, message):
        self.app.copy_to_clipboard(text)
        if getattr(self, "_status", None) and self._status.winfo_exists():
            self._status.configure(text=message, fg=self.p.success)
            if self._status_after:
                self.after_cancel(self._status_after)
            self._status_after = self.after(1600, lambda: self._status.winfo_exists() and self._status.configure(
                text="Click a synonym to copy it", fg=self.p.muted))

    def _make_draggable(self, *widgets):
        for widget in widgets:
            widget.bind("<ButtonPress-1>", self._drag_start)
            widget.bind("<B1-Motion>", self._drag_move)
            widget.bind("<ButtonRelease-1>", lambda e: setattr(self, "_drag", None), add="+")

    def _drag_start(self, event):
        self._drag = (event.x_root - self.winfo_x(), event.y_root - self.winfo_y())

    def _drag_move(self, event):
        if self._drag:
            self._moved = True
            self.geometry(f"+{event.x_root - self._drag[0]}+{event.y_root - self._drag[1]}")

    # --- layout & animation ---

    def _show(self):
        self.update_idletasks()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        if self._moved:
            x, y = self.winfo_x(), self.winfo_y()
        else:
            cx, cy = self.anchor
            gap = self.kit.px(16)
            x, y = cx + gap, cy + gap
            left, top, right, bottom = winapi.work_area_at(cx, cy)
            if x + w > right:
                x = cx - w - gap
            if y + h > bottom:
                y = cy - h - gap
            x = max(left, min(x, right - w))
            y = max(top, min(y, bottom - h))
        self.geometry(f"+{x}+{y}")
        self.deiconify()

    def _start_countdown(self):
        self._duration = self._remaining = float(self.app.settings.get("popup_seconds"))

    def _pointer_inside(self):
        x, y = self.winfo_pointerxy()
        return (self.winfo_rootx() <= x < self.winfo_rootx() + self.winfo_width()
                and self.winfo_rooty() <= y < self.winfo_rooty() + self.winfo_height())

    def _tick(self):
        if not self.winfo_exists():
            return
        now = time.monotonic()
        dt, self._last_tick = now - self._last_tick, now

        if self._closing:
            self._alpha -= dt / self.FADE_OUT * self.OPACITY
            if self._alpha <= 0:
                self.destroy()
                return
        elif self._alpha < self.OPACITY and self.mode:
            self._alpha = min(self.OPACITY, self._alpha + dt / self.FADE_IN * self.OPACITY)
        self.attributes("-alpha", max(self._alpha, 0.0))

        width = self.bar.winfo_width()
        if self.mode == "loading":
            self._phase = (self._phase + dt * 0.9) % 1.0
            segment = width * 0.3
            start = -segment + (width + segment) * self._phase
            self.bar.coords(self._bar_rect, start, 0, start + segment, self.kit.px(3))
            if self._loading_label.winfo_exists():
                self._loading_label.configure(text="Looking up" + "." * (int(now * 3) % 4))
        elif self.mode in ("result", "error") and not self._closing:
            if not self._drag and not self._pointer_inside():
                self._remaining -= dt
            if self._remaining <= 0:
                self.close()
            self.bar.coords(self._bar_rect, 0, 0, width * max(self._remaining, 0) / self._duration,
                            self.kit.px(3))
        self.after(16, self._tick)


class SettingsWindow(tk.Toplevel):
    """Settings dialog; doubles as the first-run setup screen."""

    def __init__(self, app, first_run=False, on_close=None):
        super().__init__(app.root)
        self.app, self.kit, self.p = app, app.kit, app.palette
        self.first_run = first_run
        self.on_close = on_close
        self._checking = False
        px, p, f = self.kit.px, self.p, self.kit.fonts
        settings = app.settings

        self.title(f"{APP_NAME} – Welcome" if first_run else f"{APP_NAME} – Settings")
        self.configure(bg=p.bg)
        self.resizable(False, False)
        icon = resource_path("app_icon.ico")
        if icon:
            try:
                self.iconbitmap(str(icon))
            except tk.TclError:
                pass
        self._style_ttk()

        body = tk.Frame(self, bg=p.bg)
        body.pack(fill="both", expand=True, padx=px(28), pady=px(24))
        body.columnconfigure(1, weight=1)

        heading = "Welcome to Word Lookup" if first_run else "Settings"
        tk.Label(body, text=heading, font=f.heading, fg=p.text, bg=p.bg).grid(row=0, column=0, columnspan=2, sticky="w")
        subtitle = ("Copy any word and its meaning pops up next to your cursor.\nAdd a free Gemini API key to get started."
                    if first_run else f"Version {VERSION}")
        tk.Label(body, text=subtitle, font=f.small, fg=p.muted, bg=p.bg, justify="left") \
            .grid(row=1, column=0, columnspan=2, sticky="w", pady=(px(4), 0))

        # API key
        self._section(body, 2, "GEMINI API KEY")
        self.key_var = tk.StringVar(value="" if settings.api_key_from_env else settings.api_key)
        key_box = tk.Frame(body, bg=p.surface, highlightthickness=1, highlightbackground=p.border,
                           highlightcolor=p.accent)
        key_box.grid(row=3, column=0, columnspan=2, sticky="ew")
        self.key_entry = tk.Entry(key_box, textvariable=self.key_var, show="•", font=f.body, bd=0,
                                  bg=p.surface, fg=p.text, insertbackground=p.text,
                                  disabledbackground=p.surface, disabledforeground=p.muted)
        self.key_entry.pack(side="left", fill="x", expand=True, padx=(px(10), 0), pady=px(7))
        self.kit.icon_button(key_box, p, ICON_EYE, "👁", self._toggle_key, bg=p.surface).pack(side="right", padx=px(4))
        key_help = tk.Frame(body, bg=p.bg)
        key_help.grid(row=4, column=0, columnspan=2, sticky="w", pady=(px(6), 0))
        if settings.api_key_from_env:
            self.key_entry.insert(0, "Set by the GEMINI_API_KEY environment variable")
            self.key_entry.configure(show="", state="disabled")
        else:
            self.kit.link(key_help, p, "Get a free API key from Google AI Studio",
                          lambda: webbrowser.open(API_KEY_URL)).pack(side="left")

        # Trigger
        self._section(body, 5, "HOW TO LOOK UP A WORD")
        self.trigger_var = tk.StringVar(value=settings.get("trigger"))
        self._radio(body, 6, "Automatically when I copy 1–3 words", "clipboard")
        hotkey_row = tk.Frame(body, bg=p.bg)
        hotkey_row.grid(row=7, column=0, columnspan=2, sticky="w", pady=(px(2), 0))
        self._radio(hotkey_row, None, "Only when I select a word and press", "hotkey").pack(side="left")
        self.hotkey_var = tk.StringVar(value=settings.get("hotkey"))
        ttk.Combobox(hotkey_row, textvariable=self.hotkey_var, values=HOTKEY_CHOICES, state="readonly",
                     width=16, style="WL.TCombobox", font=f.small).pack(side="left", padx=(px(6), 0))
        tk.Label(body, text="Shortcut mode never sends your clipboard to Gemini unless you ask.",
                 font=f.small, fg=p.muted, bg=p.bg).grid(row=8, column=0, columnspan=2, sticky="w", pady=(px(4), 0))

        # Model & appearance
        self._section(body, 9, "PREFERENCES")
        self.model_var = tk.StringVar(value=settings.get("model"))
        self.theme_var = tk.StringVar(value=settings.get("theme").capitalize())
        self.duration_var = tk.StringVar(value=f"{settings.get('popup_seconds')} seconds")
        self._field(body, 10, "Gemini model", self.model_var, MODEL_CHOICES, editable=True)
        self._field(body, 11, "Theme", self.theme_var, [t.capitalize() for t in THEME_CHOICES])
        self._field(body, 12, "Popup stays for", self.duration_var, [f"{s} seconds" for s in DURATION_CHOICES])

        self.startup_var = tk.BooleanVar(value=startup.is_enabled())
        tk.Checkbutton(body, text="Start Word Lookup when Windows starts", variable=self.startup_var,
                       font=f.body, fg=p.text, bg=p.bg, activebackground=p.bg, activeforeground=p.text,
                       selectcolor=p.surface, highlightthickness=0, bd=0, cursor="hand2") \
            .grid(row=13, column=0, columnspan=2, sticky="w", pady=(px(14), 0))

        # Footer
        footer = tk.Frame(body, bg=p.bg)
        footer.grid(row=14, column=0, columnspan=2, sticky="ew", pady=(px(22), 0))
        self.status = tk.Label(footer, text="", font=f.small, fg=p.muted, bg=p.bg,
                               justify="left", wraplength=px(250))
        self.status.pack(side="left", fill="x", expand=True, anchor="w")
        self.save_button = self.kit.pill_button(footer, p, "Get started" if first_run else "Save", self._save)
        self.save_button.pack(side="right")
        if not first_run:
            self.kit.pill_button(footer, p, "Cancel", self._close, primary=False) \
                .pack(side="right", padx=(0, px(8)))

        self.bind("<Return>", lambda e: self._save())
        self.bind("<Escape>", lambda e: self._close())
        self.protocol("WM_DELETE_WINDOW", self._close)
        self._place()
        if not settings.api_key_from_env:
            self.key_entry.focus_set()

    # --- widgets ---

    def _style_ttk(self):
        p, root = self.p, self.app.root
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("WL.TCombobox", fieldbackground=p.surface, background=p.surface, foreground=p.text,
                        arrowcolor=p.muted, bordercolor=p.border, lightcolor=p.surface, darkcolor=p.surface,
                        selectbackground=p.surface, selectforeground=p.text, padding=self.kit.px(5))
        style.map("WL.TCombobox", fieldbackground=[("readonly", p.surface)], foreground=[("readonly", p.text)],
                  bordercolor=[("focus", p.accent)], background=[("active", p.hover)])
        root.option_add("*TCombobox*Listbox.background", p.surface)
        root.option_add("*TCombobox*Listbox.foreground", p.text)
        root.option_add("*TCombobox*Listbox.selectBackground", p.accent)
        root.option_add("*TCombobox*Listbox.selectForeground", p.on_accent)
        root.option_add("*TCombobox*Listbox.font", self.kit.fonts.small)

    def _section(self, parent, row, text):
        tk.Label(parent, text=text, font=self.kit.fonts.caption, fg=self.p.muted, bg=self.p.bg) \
            .grid(row=row, column=0, columnspan=2, sticky="w", pady=(self.kit.px(20), self.kit.px(6)))

    def _radio(self, parent, row, text, value):
        p = self.p
        button = tk.Radiobutton(parent, text=text, value=value, variable=self.trigger_var, font=self.kit.fonts.body,
                                fg=p.text, bg=p.bg, activebackground=p.bg, activeforeground=p.text,
                                selectcolor=p.surface, highlightthickness=0, bd=0, cursor="hand2")
        if row is not None:
            button.grid(row=row, column=0, columnspan=2, sticky="w")
        return button

    def _field(self, parent, row, label, variable, values, editable=False):
        px = self.kit.px
        tk.Label(parent, text=label, font=self.kit.fonts.body, fg=self.p.text, bg=self.p.bg) \
            .grid(row=row, column=0, sticky="w", pady=px(3), padx=(0, px(16)))
        ttk.Combobox(parent, textvariable=variable, values=values, state="normal" if editable else "readonly",
                     style="WL.TCombobox", font=self.kit.fonts.small, width=26) \
            .grid(row=row, column=1, sticky="ew", pady=px(3))

    def _toggle_key(self):
        if str(self.key_entry["state"]) != "disabled":
            self.key_entry.configure(show="" if self.key_entry["show"] else "•")

    def _place(self):
        self.update_idletasks()
        winapi.set_dark_title_bar(self, self.p.dark)
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        left, top, right, bottom = winapi.work_area_at(*winapi.cursor_pos())
        self.geometry(f"+{left + (right - left - w) // 2}+{top + (bottom - top - h) // 3}")
        self.lift()
        self.attributes("-topmost", True)
        self.after(300, lambda: self.winfo_exists() and self.attributes("-topmost", False))
        self.focus_force()

    def _set_status(self, text, color=None):
        self.status.configure(text=text, fg=color or self.p.muted)

    # --- actions ---

    def _save(self):
        if self._checking:
            return
        settings = self.app.settings
        from_env = bool(settings.api_key_from_env)
        key = settings.api_key if from_env else self.key_var.get().strip()
        if not key:
            self._set_status("Enter your Gemini API key to continue.", self.p.error)
            return
        values = {
            "api_key": key,
            "model": self.model_var.get().strip() or MODEL_CHOICES[0],
            "trigger": self.trigger_var.get(),
            "hotkey": self.hotkey_var.get(),
            "theme": self.theme_var.get().lower(),
            "popup_seconds": int(self.duration_var.get().split()[0]),
            "startup": self.startup_var.get(),
        }
        if not self.first_run and key == settings.api_key and values["model"] == settings.get("model"):
            self._finish(values, None)
            return

        self._checking = True
        self.save_button.set_enabled(False)
        self._set_status("Checking your key with Gemini…")

        def check():
            try:
                gemini.lookup("hello", key, values["model"])
                error = None
            except gemini.LookupFailed as e:
                error = str(e)
            except Exception as e:
                logging.exception("Key check failed")
                error = f"Unexpected error: {e}"
            self.app.call(self._finish, values, error)

        threading.Thread(target=check, daemon=True).start()

    def _finish(self, values, error):
        if not self.winfo_exists():
            return
        self._checking = False
        self.save_button.set_enabled(True)
        if error:
            self._set_status(error, self.p.error)
            return
        self.app.apply_settings(values)
        self.destroy()
        if self.on_close:
            self.on_close(True)

    def _close(self):
        if self.first_run:
            if not tkinter.messagebox.askyesno(
                    APP_NAME, "Word Lookup needs a Gemini API key to work.\n\nQuit Word Lookup?", parent=self):
                return
        self.destroy()
        if self.on_close:
            self.on_close(False)
