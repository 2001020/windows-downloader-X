"""Tk user interface."""

import hashlib
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk
from urllib.parse import unquote, urlparse

from . import APP_NAME, __version__
from .aria2 import Aria2, find_aria2c, resource_dir
from .config import Config, default_download_dir
from .i18n import Translator, clean_text, default_ui_language, preferred_sku_language
from .msdl import PRODUCTS, BlockedError, MsdlClient, NoLinksError, find_hash
from .net import system_proxy
from .theme import Theme

CUSTOM = "custom"
UI_LANGUAGES = (("zh", "简体中文"), ("en", "English"))
THEMES = ("system", "light", "dark")
# Tiles shown in the UI; a tile can cover several products (Windows 11 x64 / Arm64).
FAMILIES = (("win11", "Windows 11"), ("win10", "Windows 10"), ("win81", "Windows 8.1"), ("win7", "Windows 7"))


def family_products(family):
    return [p for p in PRODUCTS if p.family == family]


def family_archs(family):
    archs = []
    for p in family_products(family):
        archs += [a for a in p.archs if a not in archs]
    return archs


def human_size(n):
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return ("%.0f %s" if unit == "B" else "%.1f %s") % (n, unit)
        n /= 1024


def human_time(seconds):
    if seconds is None or seconds < 0 or seconds > 99 * 3600:
        return "--:--"
    seconds = int(seconds)
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    return "%d:%02d:%02d" % (h, m, s) if h else "%02d:%02d" % (m, s)


def restored_env():
    """Environment for launching system programs from a frozen app.

    PyInstaller points LD_LIBRARY_PATH at its bundled libraries; programs such
    as xdg-open must not inherit that.
    """
    env = dict(os.environ)
    if getattr(sys, "frozen", False) and sys.platform.startswith("linux"):
        orig = env.pop("LD_LIBRARY_PATH_ORIG", None)
        if orig is not None:
            env["LD_LIBRARY_PATH"] = orig
        else:
            env.pop("LD_LIBRARY_PATH", None)
    return env


def open_path(path, select=False):
    try:
        if sys.platform.startswith("win"):
            if select and os.path.isfile(path):
                subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
            else:
                os.startfile(path if os.path.isdir(path) else os.path.dirname(path))
        elif sys.platform == "darwin":
            if select and os.path.isfile(path):
                subprocess.Popen(["open", "-R", path])
            else:
                subprocess.Popen(["open", path if os.path.isdir(path) else os.path.dirname(path)])
        else:
            target = path if os.path.isdir(path) else os.path.dirname(path)
            subprocess.Popen(["xdg-open", target], env=restored_env(), stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
    except Exception:
        pass


def open_url(url):
    if sys.platform.startswith("linux"):
        try:
            subprocess.Popen(["xdg-open", url], env=restored_env(), stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
            return
        except Exception:
            pass
    webbrowser.open(url)


def asset_path(name):
    for base in (os.path.join(resource_dir(), "assets"),
                 os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")):
        path = os.path.join(base, name)
        if os.path.isfile(path):
            return path
    return None


class App:
    def __init__(self, root):
        self.root = root
        self.cfg = Config()
        self.t = Translator(self.cfg.get("ui_language") or default_ui_language())
        self.theme = Theme(root)
        self.theme.apply(self.cfg.get("theme", "system"), self.t.lang)
        self.events = queue.Queue()
        self.aria2 = None
        self.gid = None
        self.state = "idle"  # idle | busy | downloading | paused | verifying
        self.poll_busy = False
        self.product_infos = {}
        self.current_product = None
        self.download_product = None
        self.editions = []
        self.skus = []
        self.sku_client = None
        self.link_url = ""
        self.target_path = ""
        self.expected_hash = None
        self.verify_cancel = threading.Event()
        self.tokens = {"editions": 0, "skus": 0}
        self.i18n = []  # (widget, key) pairs relabelled on language switch
        self.arch_buttons = []

        self._build()
        self._apply_language()
        self._apply_colors()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        # Windowed builds have no console; show callback errors in the log.
        self.root.report_callback_exception = lambda exc, val, tb: self.log("Internal error: %r" % (val,))
        self.root.after(100, self._drain_events)
        self.root.after(500, self._poll)

        family = self.cfg.get("family")
        if family is None:  # settings written by 1.0.0
            old = self.cfg.get("product")
            family = {"win11arm": "win11"}.get(old, old)
            if old == "win11arm":
                self.cfg.set("arch_win11", "arm64")
        if family not in [k for k, _ in FAMILIES] + [CUSTOM]:
            family = FAMILIES[0][0]
        self.log("%s %s, Python %s, Tk %s" % (APP_NAME, __version__, sys.version.split()[0], tk.TkVersion))
        self.log("aria2c: %s" % (find_aria2c() or "NOT FOUND"))
        self.family_var.set(family)
        self.on_family()

    # ------------------------------------------------------------------ UI --
    def _label(self, parent, key, **kw):
        w = ttk.Label(parent, **kw)
        self.i18n.append((w, key))
        return w

    def _button(self, parent, key, command, **kw):
        w = ttk.Button(parent, command=command, **kw)
        self.i18n.append((w, key))
        return w

    def _card(self, parent, row, **grid):
        px = self.theme.px
        card = ttk.Frame(parent, style="Card.TFrame", padding=(px(16), px(12)))
        card.grid(row=row, column=0, sticky="nsew", **grid)
        return card

    def _build(self):
        px = self.theme.px
        root = self.root
        root.minsize(px(760), px(640))
        outer = ttk.Frame(root, padding=(px(24), px(18), px(24), px(16)))
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        self.outer = outer

        # Header: icon, title, language and theme pickers.
        header = ttk.Frame(outer)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(1, weight=1)
        icon = asset_path("icon-96.png" if self.theme.scale >= 1.75 else "icon-48.png")
        self.header_icon = tk.PhotoImage(file=icon) if icon else None
        if self.header_icon:
            ttk.Label(header, image=self.header_icon).grid(row=0, column=0, rowspan=2, sticky="w",
                                                           padx=(0, px(14)))
        self._label(header, "title", style="Title.TLabel").grid(row=0, column=1, sticky="sw")
        self._label(header, "subtitle", style="Muted.TLabel").grid(row=1, column=1, sticky="nw")
        pickers = ttk.Frame(header)
        pickers.grid(row=0, column=2, rowspan=2, sticky="e")
        self._label(pickers, "ui_language", style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        self.ui_lang_cb = ttk.Combobox(pickers, state="readonly", width=9, values=[n for _, n in UI_LANGUAGES])
        self.ui_lang_cb.grid(row=1, column=0, sticky="w")
        self.ui_lang_cb.bind("<<ComboboxSelected>>", self.on_ui_language)
        self._label(pickers, "theme", style="Muted.TLabel").grid(row=0, column=1, sticky="w", padx=(px(10), 0))
        self.theme_cb = ttk.Combobox(pickers, state="readonly", width=9)
        self.theme_cb.grid(row=1, column=1, sticky="w", padx=(px(10), 0))
        self.theme_cb.bind("<<ComboboxSelected>>", self.on_theme)

        # System tiles.
        tiles_box = ttk.Frame(outer)
        tiles_box.grid(row=1, column=0, sticky="ew", pady=(px(16), 0))
        self._label(tiles_box, "choose_system", style="Strong.TLabel").grid(row=0, column=0, columnspan=9,
                                                                             sticky="w", pady=(0, px(6)))
        self.family_var = tk.StringVar()
        self.tiles = []
        for i, (key, title) in enumerate(FAMILIES + ((CUSTOM, ""),)):
            tile = ttk.Radiobutton(tiles_box, text=title, value=key, variable=self.family_var,
                                   style="Tile.Toggle.TButton", command=self.on_family)
            tile.grid(row=1, column=i, sticky="ew", padx=(0 if i == 0 else px(8), 0))
            tiles_box.columnconfigure(i, weight=1, uniform="tiles")
            self.tiles.append(tile)
        self.i18n.append((self.tiles[-1], "product_custom"))

        # Image options.
        form = self._card(outer, 2, pady=(px(14), 0))
        form.columnconfigure(1, weight=1)
        pad = {"pady": px(4)}
        lpad = (0, px(14))

        self.edition_lbl = self._label(form, "edition")
        self.edition_lbl.grid(row=0, column=0, sticky="w", padx=lpad, **pad)
        self.edition_cb = ttk.Combobox(form, state="readonly")
        self.edition_cb.grid(row=0, column=1, sticky="ew", **pad)
        self.edition_cb.bind("<<ComboboxSelected>>", lambda e: self.on_edition())
        self.refresh_btn = self._button(form, "refresh", self.on_refresh)
        self.refresh_btn.grid(row=0, column=2, sticky="ew", padx=(px(8), 0), **pad)

        self.lang_lbl = self._label(form, "language")
        self.lang_lbl.grid(row=1, column=0, sticky="w", padx=lpad, **pad)
        self.lang_cb = ttk.Combobox(form, state="readonly")
        self.lang_cb.grid(row=1, column=1, columnspan=2, sticky="ew", **pad)
        self.lang_cb.bind("<<ComboboxSelected>>", lambda e: self.on_language())

        self.arch_lbl = self._label(form, "arch")
        self.arch_lbl.grid(row=2, column=0, sticky="w", padx=lpad, **pad)
        self.arch_row = ttk.Frame(form)
        self.arch_row.grid(row=2, column=1, columnspan=2, sticky="ew", **pad)
        self.arch_var = tk.StringVar()
        self.arch_hint = ttk.Label(self.arch_row, style="Muted.TLabel")
        self.arch_hint.pack(side="right")

        self.url_lbl = self._label(form, "custom_url")
        self.url_var = tk.StringVar()
        self.url_entry = ttk.Entry(form, textvariable=self.url_var)
        self.url_hint = self._label(form, "custom_url_hint", style="Muted.TLabel")

        self._label(form, "save_to").grid(row=5, column=0, sticky="w", padx=lpad, **pad)
        self.dir_var = tk.StringVar(value=self.cfg.get("download_dir") or default_download_dir())
        self.dir_entry = ttk.Entry(form, textvariable=self.dir_var)
        self.dir_entry.grid(row=5, column=1, sticky="ew", **pad)
        self.browse_btn = self._button(form, "browse", self.on_browse)
        self.browse_btn.grid(row=5, column=2, sticky="ew", padx=(px(8), 0), **pad)

        self.source_title = self._label(form, "source")
        self.source_title.grid(row=6, column=0, sticky="w", padx=lpad, **pad)
        self.source_lbl = ttk.Label(form, style="Ok.TLabel")
        self.source_lbl.grid(row=6, column=1, columnspan=2, sticky="w", **pad)
        self.note_lbl = ttk.Label(form, style="Warn.TLabel", justify="left")
        form.bind("<Configure>", lambda e: self.note_lbl.configure(wraplength=max(e.width - px(40), px(300))))

        # Progress.
        prog = self._card(outer, 3, pady=(px(14), 0))
        prog.columnconfigure(0, weight=1)
        self.file_var = tk.StringVar()
        ttk.Label(prog, textvariable=self.file_var, style="Strong.TLabel").grid(row=0, column=0, sticky="w")
        self.status_var = tk.StringVar()
        ttk.Label(prog, textvariable=self.status_var, style="Muted.TLabel").grid(row=1, column=0, sticky="w")
        self.percent_var = tk.StringVar(value="0%")
        ttk.Label(prog, textvariable=self.percent_var, style="Big.TLabel", anchor="e").grid(
            row=0, column=1, rowspan=2, sticky="e", padx=(px(12), 0))
        self.progress = ttk.Progressbar(prog, maximum=1000, mode="determinate")
        self.progress.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(px(10), px(10)))
        stats = ttk.Frame(prog)
        stats.grid(row=3, column=0, columnspan=2, sticky="ew")
        self.stat_vars = {}
        for i, key in enumerate(("stat_done", "stat_speed", "stat_eta", "stat_conns")):
            stats.columnconfigure(i, weight=1, uniform="stats")
            self._label(stats, key, style="Muted.TLabel").grid(row=0, column=i, sticky="w")
            var = tk.StringVar(value="--")
            ttk.Label(stats, textvariable=var, style="Value.TLabel").grid(row=1, column=i, sticky="w")
            self.stat_vars[key] = var
        self.hash_var = tk.StringVar()
        self.hash_lbl = ttk.Label(prog, textvariable=self.hash_var, style="Mono.TLabel")
        self.hash_lbl.grid(row=4, column=0, columnspan=2, sticky="w", pady=(px(8), 0))
        self.hash_lbl.grid_remove()
        self.hash_var.trace_add("write", lambda *a: self.hash_lbl.grid() if self.hash_var.get()
                                else self.hash_lbl.grid_remove())

        # Buttons.
        bar = ttk.Frame(outer)
        bar.grid(row=4, column=0, sticky="ew", pady=(px(14), 0))
        self.start_btn = self._button(bar, "start", self.on_start, style="Big.Accent.TButton")
        self.start_btn.pack(side="left")
        self.pause_btn = ttk.Button(bar, command=self.on_pause)
        self.pause_btn.pack(side="left", padx=(px(8), 0), fill="y")
        self.cancel_btn = self._button(bar, "cancel", self.on_cancel)
        self.cancel_btn.pack(side="left", padx=(px(8), 0), fill="y")
        self.page_btn = self._button(bar, "official_page", self.on_official_page)
        self.page_btn.pack(side="right", fill="y")
        self.copy_btn = self._button(bar, "copy_link", self.on_copy_link)
        self.copy_btn.pack(side="right", padx=(0, px(8)), fill="y")
        self.folder_btn = self._button(bar, "open_folder", self.on_open_folder)
        self.folder_btn.pack(side="right", padx=(0, px(8)), fill="y")

        # Advanced settings (collapsible) and log.
        lower = ttk.Frame(outer)
        lower.grid(row=5, column=0, sticky="nsew", pady=(px(10), 0))
        outer.rowconfigure(5, weight=1)
        lower.columnconfigure(0, weight=1)
        lower.rowconfigure(2, weight=1)
        self.adv_open = bool(self.cfg.get("advanced_open", False))
        self.adv_btn = ttk.Button(lower, style="Toolbutton", command=self.on_toggle_advanced)
        self.adv_btn.grid(row=0, column=0, sticky="w")
        self.adv = ttk.Frame(lower, style="Card.TFrame", padding=(px(16), px(10)))
        self.adv.columnconfigure(3, weight=1)
        self._label(self.adv, "connections").grid(row=0, column=0, sticky="w")
        self.conn_var = tk.IntVar(value=int(self.cfg.get("connections", 16)))
        ttk.Spinbox(self.adv, from_=1, to=16, width=4, textvariable=self.conn_var).grid(
            row=0, column=1, sticky="w", padx=(px(8), px(20)))
        self._label(self.adv, "proxy").grid(row=0, column=2, sticky="w")
        saved_proxy = self.cfg.get("proxy")
        self.proxy_var = tk.StringVar(value=system_proxy() if saved_proxy is None else saved_proxy)
        ttk.Entry(self.adv, textvariable=self.proxy_var).grid(row=0, column=3, sticky="ew", padx=(px(8), 0))
        self._label(self.adv, "proxy_hint", style="Muted.TLabel").grid(row=1, column=3, sticky="w",
                                                                       padx=(px(8), 0), pady=(px(2), 0))
        self.verify_var = tk.BooleanVar(value=bool(self.cfg.get("verify", True)))
        self.verify_chk = ttk.Checkbutton(self.adv, variable=self.verify_var, style="Switch.TCheckbutton")
        self.i18n.append((self.verify_chk, "verify"))
        self.verify_chk.grid(row=1, column=0, columnspan=3, sticky="w", pady=(px(6), 0))

        logbox = ttk.Frame(lower)
        logbox.grid(row=2, column=0, sticky="nsew", pady=(px(8), 0))
        logbox.columnconfigure(0, weight=1)
        logbox.rowconfigure(1, weight=1)
        self._label(logbox, "log", style="Strong.TLabel").grid(row=0, column=0, sticky="w", pady=(0, px(6)))
        logcard = ttk.Frame(logbox, style="Card.TFrame", padding=(px(10), px(6)))
        logcard.grid(row=1, column=0, sticky="nsew")
        logcard.columnconfigure(0, weight=1)
        logcard.rowconfigure(0, weight=1)
        self.log_text = tk.Text(logcard, height=4, wrap="word", state="disabled", relief="flat", borderwidth=0,
                                font=self.theme.fonts["mono"], highlightthickness=0)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(logcard, orient="vertical", command=self.log_text.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=sb.set)

        self._show_advanced()
        self._update_buttons()

    def _apply_colors(self):
        c = self.theme.colors
        self.log_text.configure(background=c["bg"], foreground=c["muted"], insertbackground=c["fg"],
                                selectbackground=c["accent"], selectforeground=c["bg"])
        self.root.configure(background=c["bg"])

    def _apply_language(self):
        t = self.t
        self.root.title("%s %s" % (t("title"), __version__))
        for widget, key in self.i18n:
            widget.configure(text=t(key))
        self.ui_lang_cb.current([c for c, _ in UI_LANGUAGES].index(t.lang))
        self.theme_cb.configure(values=[t("theme_" + m) for m in THEMES])
        mode = self.cfg.get("theme", "system")
        self.theme_cb.current(THEMES.index(mode) if mode in THEMES else 0)
        self._show_advanced()
        self._build_arch_buttons()
        self._fill_editions(keep=True)
        self._fill_languages(keep=True)
        self._update_source()
        self._update_buttons()
        if self.state == "idle" and not self.gid:
            self.set_status(t("ready"))
        if not self.file_var.get() or not self.target_path:
            self.file_var.set(t("no_task"))

    # ------------------------------------------------------------- helpers --
    def log(self, msg):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", time.strftime("%H:%M:%S  ") + clean_text(msg) + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def log_threadsafe(self, msg):
        self.events.put((self.log, (msg,)))

    def set_status(self, text):
        self.status_var.set(clean_text(str(text).splitlines()[0] if text else ""))

    def error_box(self, text):
        messagebox.showerror(self.t("error_title"), clean_text(text), parent=self.root)

    def run_bg(self, func, on_done=None, on_error=None):
        def worker():
            try:
                result = func()
            except Exception as e:  # reported on the UI thread
                self.events.put((on_error or self._show_error, (e,)))
                return
            if on_done:
                self.events.put((on_done, (result,)))

        threading.Thread(target=worker, daemon=True).start()

    def _drain_events(self):
        try:
            while True:
                func, args = self.events.get_nowait()
                try:
                    func(*args)
                except Exception as e:
                    self.log("Internal error: %r" % e)
        except queue.Empty:
            pass
        self.root.after(80, self._drain_events)

    def _show_error(self, error):
        self.state = "idle" if self.state == "busy" else self.state
        self._update_buttons()
        self.log(str(error))
        self.error_box(str(error))

    def family(self):
        return self.family_var.get()

    def product(self):
        products = family_products(self.family())
        arch = self.arch_var.get()
        for p in products:
            if arch in p.archs:
                return p
        return products[0] if products else None

    def client(self):
        return MsdlClient(proxy=self.proxy_var.get().strip() or None, log=self.log_threadsafe)

    def _update_buttons(self):
        s = self.state
        idle = s == "idle"
        active = s in ("downloading", "paused")
        self.start_btn.configure(state="normal" if idle else "disabled")
        self.pause_btn.configure(state="normal" if active else "disabled",
                                 text=self.t("resume") if s == "paused" else self.t("pause"))
        self.cancel_btn.configure(state="normal" if active or s == "verifying" else "disabled")
        self.copy_btn.configure(state="normal" if self.link_url else "disabled")
        product = self.product()
        self.page_btn.configure(state="disabled" if product is not None and product.retired else "normal")
        for cb in (self.edition_cb, self.lang_cb):
            cb.configure(state="readonly" if idle else "disabled")
        for w in self.tiles + self.arch_buttons + [self.refresh_btn, self.url_entry, self.dir_entry,
                                                    self.browse_btn]:
            w.configure(state="normal" if idle else "disabled")

    # ---------------------------------------------------------- selection --
    def on_ui_language(self, event=None):
        self.t.lang = UI_LANGUAGES[self.ui_lang_cb.current()][0]
        self.cfg.set("ui_language", self.t.lang)
        self.cfg.save()
        self.theme.apply(self.cfg.get("theme", "system"), self.t.lang)
        self._apply_language()

    def on_theme(self, event=None):
        mode = THEMES[max(0, self.theme_cb.current())]
        self.cfg.set("theme", mode)
        self.cfg.save()
        self.theme.apply(mode, self.t.lang)
        self._apply_colors()

    def on_toggle_advanced(self):
        self.adv_open = not self.adv_open
        self.cfg.set("advanced_open", self.adv_open)
        self._show_advanced()

    def _show_advanced(self):
        arrow = "▾" if self.adv_open else "▸"
        self.adv_btn.configure(text="%s  %s" % (arrow, self.t("advanced")))
        if self.adv_open:
            self.adv.grid(row=1, column=0, sticky="ew", pady=(self.theme.px(6), 0))
        else:
            self.adv.grid_remove()

    def _show_custom(self, custom):
        rows = ((self.edition_lbl, self.edition_cb, self.refresh_btn), (self.lang_lbl, self.lang_cb),
                (self.arch_lbl, self.arch_row), (self.source_title, self.source_lbl))
        for row in rows:
            for w in row:
                if custom:
                    w.grid_remove()
                else:
                    w.grid()
        px = self.theme.px
        if custom:
            self.url_lbl.grid(row=3, column=0, sticky="w", padx=(0, px(14)), pady=px(4))
            self.url_entry.grid(row=3, column=1, columnspan=2, sticky="ew", pady=px(4))
            self.url_hint.grid(row=4, column=1, columnspan=2, sticky="w", pady=(0, px(4)))
            self.url_entry.focus_set()
        else:
            for w in (self.url_lbl, self.url_entry, self.url_hint):
                w.grid_remove()

    def _build_arch_buttons(self):
        for b in self.arch_buttons:
            b.destroy()
        self.arch_buttons = []
        family = self.family()
        archs = family_archs(family)
        if not archs:
            return
        if self.arch_var.get() not in archs:
            saved = self.cfg.get("arch_" + family)
            self.arch_var.set(saved if saved in archs else archs[0])
        for i, arch in enumerate(archs):
            b = ttk.Radiobutton(self.arch_row, text=self.t("arch_" + arch), value=arch, variable=self.arch_var,
                                style="Seg.Toggle.TButton", command=self.on_arch)
            b.pack(side="left", padx=(0 if i == 0 else self.theme.px(6), 0))
            self.arch_buttons.append(b)
        self.arch_hint.configure(text=self.t("arch_hint_" + self.arch_var.get()))

    def _update_source(self):
        product = self.product()
        if product is None:
            self.note_lbl.grid_remove()
            return
        self.source_lbl.configure(text="✓  " + self.t("source_value"))
        note = {"win81": "note_win81", "win7": "note_win7"}.get(product.family)
        if note:
            self.note_lbl.configure(text="\u26a0  " + self.t(note))
            self.note_lbl.grid(row=7, column=0, columnspan=3, sticky="w", pady=(self.theme.px(6), 0))
        else:
            self.note_lbl.grid_remove()

    def on_family(self):
        family = self.family()
        self.cfg.set("family", family)
        custom = family == CUSTOM
        self.arch_var.set("")
        self._build_arch_buttons()
        self._show_custom(custom)
        self._update_source()
        self.on_product()

    def on_arch(self):
        family = self.family()
        self.cfg.set("arch_" + family, self.arch_var.get())
        self.arch_hint.configure(text=self.t("arch_hint_" + self.arch_var.get()))
        if self.product() is not self.current_product:
            self.on_product()

    def on_product(self, force=False):
        product = self.product()
        self.current_product = product
        self.link_url = ""
        self._update_buttons()
        if product is None:
            return
        self.edition_cb.set("")
        self.lang_cb.set("")
        self.lang_cb.configure(values=[])
        self.editions = []
        self.skus = []
        self.tokens["skus"] += 1
        info = self.product_infos.get(product.key)
        if info and not force:
            self._set_editions(product, info)
            return
        self.tokens["editions"] += 1
        token = self.tokens["editions"]
        self.edition_cb.set(self.t("loading"))
        if not product.retired:
            self.log(self.t("loading_editions", product=product.title))
        client = self.client()
        self.run_bg(lambda: client.product_info(product),
                    lambda info: self._editions_loaded(token, product, info))

    def _editions_loaded(self, token, product, info):
        if token != self.tokens["editions"]:
            return
        self.product_infos[product.key] = info
        if info.from_fallback:
            self.log(self.t("fallback_editions"))
        self._set_editions(product, info)

    def _set_editions(self, product, info):
        if self.product() is not product:
            return
        self.editions = info.editions
        self._fill_editions(keep=False)
        if self.editions:
            self.on_edition()

    def _fill_editions(self, keep):
        if not self.editions:
            return
        index = self.edition_cb.current() if keep else -1
        self.edition_cb.configure(values=[self.t.edition_name(e) for e in self.editions])
        self.edition_cb.current(index if 0 <= index < len(self.editions) else 0)

    def on_refresh(self):
        if self.product() is None:
            return
        self.on_product(force=True)

    def on_edition(self):
        product = self.product()
        index = self.edition_cb.current()
        if product is None or not (0 <= index < len(self.editions)):
            return
        edition = self.editions[index]
        self.tokens["skus"] += 1
        token = self.tokens["skus"]
        self.skus = []
        self.lang_cb.configure(values=[])
        self.lang_cb.set(self.t("loading"))
        self.log(self.t("loading_languages"))
        client = self.client()
        self.run_bg(lambda: (client, client.skus(product, edition.id)),
                    lambda res: self._skus_loaded(token, res),
                    lambda err: self._skus_failed(token, err))

    def _skus_loaded(self, token, result):
        if token != self.tokens["skus"]:
            return
        self.sku_client, self.skus = result
        self._fill_languages(keep=False)
        if self.skus:
            self.log("%s: %d languages" % (self.skus[0].product_name, len(self.skus)))

    def _skus_failed(self, token, error):
        if token != self.tokens["skus"]:
            return
        self.lang_cb.set("")
        self._report_msdl_error(error)

    def _fill_languages(self, keep):
        if not self.skus:
            return
        wanted = None
        if keep and 0 <= self.lang_cb.current() < len(self.skus):
            wanted = self.skus[self.lang_cb.current()].language
        wanted = wanted or self.cfg.get("sku_language") or preferred_sku_language()
        self.lang_cb.configure(values=[self.t.language_name(s.language) for s in self.skus])
        names = [s.language for s in self.skus]
        for candidate in (wanted, preferred_sku_language(), "English International", "English"):
            if candidate in names:
                self.lang_cb.current(names.index(candidate))
                break
        else:
            self.lang_cb.current(0)

    def on_language(self):
        index = self.lang_cb.current()
        if 0 <= index < len(self.skus):
            self.cfg.set("sku_language", self.skus[index].language)

    def on_browse(self):
        path = filedialog.askdirectory(initialdir=self.dir_var.get() or default_download_dir(), parent=self.root)
        if path:
            self.dir_var.set(path)

    def on_official_page(self):
        product = self.product() or PRODUCTS[0]
        if product.page_url:
            open_url(product.page_url)

    def on_copy_link(self):
        if self.link_url:
            self.root.clipboard_clear()
            self.root.clipboard_append(self.link_url)
            self.log(self.t("copied"))

    def on_open_folder(self):
        if self.target_path and os.path.exists(self.target_path):
            open_path(self.target_path, select=True)
        else:
            directory = self.dir_var.get()
            if os.path.isdir(directory):
                open_path(directory)

    def _report_msdl_error(self, error):
        self.state = "idle"
        self._update_buttons()
        if isinstance(error, BlockedError):
            text = self.t("blocked", error=error)
        elif isinstance(error, NoLinksError):
            text = self.t("no_links")
        else:
            text = str(error)
        self.log(text.splitlines()[0])
        self.set_status(text)
        self.error_box(text)

    # ----------------------------------------------------------- download --
    def _save_settings(self):
        self.cfg.set("download_dir", self.dir_var.get())
        self.cfg.set("proxy", self.proxy_var.get().strip())
        self.cfg.set("verify", bool(self.verify_var.get()))
        try:
            self.cfg.set("connections", max(1, min(16, int(self.conn_var.get()))))
        except (tk.TclError, ValueError):
            self.cfg.set("connections", 16)
        self.cfg.save()

    def _reset_progress(self):
        self.progress.configure(value=0)
        self.percent_var.set("0%")
        self.hash_var.set("")
        for var in self.stat_vars.values():
            var.set("--")

    def on_start(self):
        if self.state != "idle":
            return
        directory = self.dir_var.get().strip()
        if not directory:
            directory = default_download_dir()
            self.dir_var.set(directory)
        try:
            os.makedirs(directory, exist_ok=True)
        except OSError as e:
            self.error_box(str(e))
            return
        if not find_aria2c():
            self.error_box(self.t("no_aria2"))
            return
        self._save_settings()
        product = self.product()
        self.download_product = product
        self._reset_progress()

        if product is None:
            url = self.url_var.get().strip()
            if not url.lower().startswith(("http://", "https://")):
                messagebox.showwarning(self.t("custom_url"), self.t("need_url"), parent=self.root)
                return
            name = unquote(urlparse(url).path.rsplit("/", 1)[-1]) or "download.iso"
            self.link_url = url
            self.expected_hash = None
            self._begin_download(url, name)
            return

        sku_index = self.lang_cb.current()
        if not (0 <= sku_index < len(self.skus)):
            messagebox.showwarning(self.t("title"), self.t("need_selection"), parent=self.root)
            return
        sku = self.skus[sku_index]
        arch = self.arch_var.get() or product.archs[0]
        info = self.product_infos.get(product.key)
        # Reuse the session that listed the languages, unless the proxy changed since.
        client = self.sku_client
        if client is None or client.proxy != (self.proxy_var.get().strip() or None):
            client = self.client()
        self.state = "busy"
        self._update_buttons()
        self.set_status(self.t("requesting_link"))
        self.log(self.t("requesting_link"))

        def done(links):
            match = [l for l in links if l.arch == arch]
            if not match:
                self.state = "idle"
                self._update_buttons()
                available = ", ".join(self.t("arch_" + l.arch) for l in links)
                self._show_error(self.t("no_arch", arch=self.t("arch_" + arch), available=available))
                return
            link = match[0]
            self.link_url = link.url
            self.expected_hash = find_hash(info.hashes, sku, arch) if info else None
            self.log(self.t("link_ok", name=link.filename))
            self.state = "idle"
            self._begin_download(link.url, link.filename)

        self.run_bg(lambda: client.links(product, sku.id), done, self._report_msdl_error)

    def _begin_download(self, url, filename):
        directory = self.dir_var.get().strip()
        path = os.path.join(directory, filename)
        control = path + ".aria2"
        self.target_path = path
        self.file_var.set(clean_text(filename))
        if self.expected_hash:
            self.hash_var.set("SHA-256 (Microsoft)  " + self.expected_hash.upper())
        if os.path.exists(path):
            if os.path.exists(control):
                self.log(self.t("resuming_partial"))
            elif messagebox.askyesno(self.t("title"), self.t("file_exists", path=path), parent=self.root):
                try:
                    os.remove(path)
                except OSError as e:
                    self._show_error(e)
                    return
            else:
                self.state = "idle"
                self._update_buttons()
                return
        self.state = "busy"
        self._update_buttons()
        self.set_status(self.t("starting_aria2"))
        connections = int(self.cfg.get("connections", 16))
        proxy = self.proxy_var.get().strip() or None

        def add():
            if self.aria2 is None or not self.aria2.running():
                aria2 = Aria2()
                aria2.start()
                self.aria2 = aria2
                self.log_threadsafe(aria2.version())
            return self.aria2.add(url, directory, filename, connections=connections, proxy=proxy)

        def added(gid):
            self.log("%s → %s" % (urlparse(url).netloc, path))
            self.gid = gid
            self.state = "downloading"
            self._update_buttons()
            self.set_status(self.t("downloading"))

        def failed(error):
            self.state = "idle"
            self._update_buttons()
            self._show_error(self.t("failed", error=error))

        self.run_bg(add, added, failed)

    def _poll(self):
        self.root.after(500, self._poll)
        if self.poll_busy or not self.gid or self.state not in ("downloading", "paused"):
            return
        self.poll_busy = True
        gid = self.gid

        def done(status):
            self.poll_busy = False
            if gid == self.gid:
                self._on_status(status)

        def failed(error):
            self.poll_busy = False
            if gid == self.gid and (self.aria2 is None or not self.aria2.running()):
                output = self.aria2.console_output() if self.aria2 else ""
                self._download_failed("aria2c stopped unexpectedly. %s" % output)

        self.run_bg(lambda: self.aria2.status(gid), done, failed)

    def _on_status(self, st):
        total = int(st.get("totalLength") or 0)
        done = int(st.get("completedLength") or 0)
        speed = int(st.get("downloadSpeed") or 0)
        status = st.get("status")
        if total:
            self.progress.configure(value=done * 1000 // total)
            self.percent_var.set("%.1f%%" % (done * 100.0 / total))
        eta = (total - done) / speed if speed and total else None
        self.stat_vars["stat_done"].set("%s / %s" % (human_size(done), human_size(total) if total else "?"))
        self.stat_vars["stat_speed"].set("%s/s" % human_size(speed) if status != "paused" else "--")
        self.stat_vars["stat_eta"].set(human_time(eta) if status != "paused" else "--")
        self.stat_vars["stat_conns"].set(str(st.get("connections", "0")))
        self.set_status(self.t("paused") if status == "paused" else self.t("downloading"))
        if status == "paused" and self.state != "paused":
            self.state = "paused"
            self._update_buttons()
        elif status == "active" and self.state == "paused":
            self.state = "downloading"
            self._update_buttons()
        elif status == "complete":
            aria2, gid = self.aria2, self.gid
            self.run_bg(lambda: aria2.remove(gid))
            self.gid = None
            self.progress.configure(value=1000)
            self.percent_var.set("100%")
            self.stat_vars["stat_speed"].set("--")
            self.stat_vars["stat_eta"].set("--")
            self.log(self.t("done", path=self.target_path))
            if self.verify_var.get():
                self._verify()
            else:
                self._finished()
        elif status in ("error", "removed"):
            message = st.get("errorMessage") or status
            code = st.get("errorCode")
            if code and code != "0":
                message = "[aria2 %s] %s" % (code, message)
            self._download_failed(message)

    def _download_failed(self, message):
        if self.gid and self.aria2:
            aria2, gid = self.aria2, self.gid
            self.run_bg(lambda: aria2.remove(gid))
        self.gid = None
        self.state = "idle"
        self._update_buttons()
        text = self.t("failed", error=message)
        self.set_status(text)
        self.log(text)
        self.error_box(text)

    def _verify(self):
        self.state = "verifying"
        self._update_buttons()
        self.set_status(self.t("verifying"))
        self.log(self.t("verifying"))
        path = self.target_path
        self.verify_cancel = threading.Event()
        cancel = self.verify_cancel

        def progress(fraction):
            self.progress.configure(value=int(fraction * 1000))
            self.percent_var.set("%.0f%%" % (fraction * 100))

        def work():
            size = os.path.getsize(path) or 1
            h = hashlib.sha256()
            read = 0
            last = 0
            with open(path, "rb") as f:
                while True:
                    if cancel.is_set():
                        return None
                    chunk = f.read(4 * 1024 * 1024)
                    if not chunk:
                        break
                    h.update(chunk)
                    read += len(chunk)
                    if time.time() - last > 0.2:
                        last = time.time()
                        self.events.put((progress, (read / size,)))
            return h.hexdigest()

        self.run_bg(work, self._verified, lambda e: self._finished(error=e))

    def _verified(self, actual):
        if actual is None:
            return
        self.progress.configure(value=1000)
        self.percent_var.set("100%")
        expected = self.expected_hash
        if not expected:
            retired = self.download_product is not None and self.download_product.retired
            self.log(self.t("no_hash_retired" if retired else "no_hash"))
            self.log(self.t("sha256_actual", value=actual.upper()))
            self.hash_var.set("SHA-256  " + actual.upper())
            self._finished()
        elif actual.lower() == expected.lower():
            self.log(self.t("verify_ok"))
            self.hash_var.set("SHA-256 ✓  " + actual.upper())
            self._finished(note=self.t("verify_ok"))
        else:
            text = self.t("verify_bad", expected=expected.upper(), actual=actual.upper())
            self.log(text.replace("\n", " "))
            self._finished(error=text)

    def _finished(self, note=None, error=None):
        self.state = "idle"
        self._update_buttons()
        if error:
            self.set_status(str(error))
            self.error_box(str(error))
            return
        text = self.t("done", path=self.target_path)
        self.set_status(self.t("done_title"))
        if note:
            text += "\n\n" + note
        if messagebox.askyesno(self.t("done_title"), text + "\n\n" + self.t("open_folder_q"), parent=self.root):
            open_path(self.target_path, select=True)

    def on_pause(self):
        if not self.gid or not self.aria2:
            return
        gid = self.gid
        if self.state == "paused":
            self.run_bg(lambda: self.aria2.resume(gid), lambda r: self._set_state("downloading"))
        else:
            self.run_bg(lambda: self.aria2.pause(gid), lambda r: self._set_state("paused"))

    def _set_state(self, state):
        if self.gid:
            self.state = state
            self._update_buttons()
            self.set_status(self.t("paused") if state == "paused" else self.t("downloading"))

    def on_cancel(self):
        if self.state == "verifying":
            self.verify_cancel.set()
            self.state = "idle"
            self._update_buttons()
            self.set_status(self.t("cancelled"))
            return
        if not self.gid:
            return
        answer = messagebox.askyesnocancel(self.t("cancel"), self.t("confirm_cancel"), parent=self.root)
        if answer is None:
            return
        gid, path = self.gid, self.target_path
        self.gid = None
        aria2 = self.aria2

        def work():
            aria2.remove(gid)
            if answer:
                # forceRemove returns before the file handle is closed on Windows.
                for _ in range(20):
                    try:
                        for p in (path, path + ".aria2"):
                            if os.path.exists(p):
                                os.remove(p)
                        break
                    except OSError:
                        time.sleep(0.25)

        def done(_):
            self.state = "idle"
            self._update_buttons()
            self._reset_progress()
            self.set_status(self.t("cancelled"))
            self.log(self.t("cancelled"))

        self.run_bg(work, done)

    def on_close(self):
        if self.state in ("downloading", "paused", "busy"):
            if not messagebox.askyesno(self.t("title"), self.t("confirm_quit"), parent=self.root):
                return
        self._save_settings()
        if self.aria2:
            try:
                self.aria2.stop()
            except Exception:
                pass
        self.root.destroy()


def set_window_icon(root):
    try:
        icon = asset_path("icon.png")
        if icon:
            image = tk.PhotoImage(file=icon)
            root.iconphoto(True, image)
            root._icon_image = image
    except tk.TclError:
        pass


def enable_dpi_awareness():
    if sys.platform.startswith("win"):
        try:
            import ctypes

            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(1)
            except Exception:
                ctypes.windll.user32.SetProcessDPIAware()
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("WinISO.Downloader")
        except Exception:
            pass


def main():
    enable_dpi_awareness()
    root = tk.Tk(className="winiso-downloader")
    set_window_icon(root)
    app = App(root)
    root.update_idletasks()
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    w = min(max(root.winfo_reqwidth(), app.theme.px(900)), sw - 40)
    h = min(max(root.winfo_reqheight() + app.theme.px(40), app.theme.px(760)), sh - 90)
    x = max(0, (sw - w) // 2)
    y = max(0, (sh - h) // 3)
    root.geometry("%dx%d+%d+%d" % (w, h, x, y))
    # The Windows title bar can only be recoloured once the window exists.
    root.after(150, app.theme.refresh_title_bar)
    root.mainloop()
