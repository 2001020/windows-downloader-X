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
from tkinter import filedialog, font as tkfont, messagebox, ttk
from urllib.parse import unquote, urlparse

from . import APP_NAME, __version__
from .aria2 import Aria2, find_aria2c, resource_dir
from .config import Config, default_download_dir
from .i18n import Translator, default_ui_language, preferred_sku_language
from .msdl import PRODUCTS, BlockedError, MsdlClient, find_hash
from .net import system_proxy

CUSTOM = "custom"
UI_LANGUAGES = (("zh", "简体中文"), ("en", "English"))


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


class App:
    def __init__(self, root):
        self.root = root
        self.cfg = Config()
        self.t = Translator(self.cfg.get("ui_language") or default_ui_language())
        self.events = queue.Queue()
        self.aria2 = None
        self.gid = None
        self.state = "idle"  # idle | busy | downloading | paused | verifying
        self.poll_busy = False
        self.product_infos = {}
        self.editions = []
        self.skus = []
        self.sku_client = None
        self.link_url = ""
        self.target_path = ""
        self.expected_hash = None
        self.tokens = {"editions": 0, "skus": 0}
        self.i18n = []  # (widget, key) pairs relabelled on language switch

        self._setup_style()
        self._build()
        self._apply_language()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        # Windowed builds have no console; show callback errors in the log.
        self.root.report_callback_exception = lambda exc, val, tb: self.log("Internal error: %r" % (val,))
        self.root.after(100, self._drain_events)
        self.root.after(500, self._poll)

        last = self.cfg.get("product", PRODUCTS[0].key)
        keys = [p.key for p in PRODUCTS] + [CUSTOM]
        self.product_cb.current(keys.index(last) if last in keys else 0)
        self.on_product()
        self.log("%s %s · Python %s · Tk %s" % (APP_NAME, __version__, sys.version.split()[0], tk.TkVersion))
        aria2c = find_aria2c()
        self.log("aria2c: %s" % (aria2c or "NOT FOUND"))

    # ------------------------------------------------------------------ UI --
    def _setup_style(self):
        style = ttk.Style(self.root)
        if sys.platform.startswith("linux") and "clam" in style.theme_names():
            style.theme_use("clam")
            for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
                try:
                    tkfont.nametofont(name).configure(size=10)
                except tk.TclError:
                    pass
        base = tkfont.nametofont("TkDefaultFont")
        self.title_font = base.copy()
        self.title_font.configure(size=base.cget("size") + 7 if base.cget("size") > 0 else -22, weight="bold")
        self.bold_font = base.copy()
        self.bold_font.configure(weight="bold")
        self.small_font = base.copy()
        self.small_font.configure(size=max(base.cget("size") - 1, 8) if base.cget("size") > 0 else base.cget("size"))
        style.configure("Title.TLabel", font=self.title_font)
        style.configure("Accent.TButton", font=self.bold_font)
        if sys.platform != "darwin":
            # Aqua picks readable secondary colours itself, also in dark mode.
            style.configure("Sub.TLabel", foreground="#666666")
            style.configure("Status.TLabel", foreground="#444444")

    def _label(self, parent, key, **kw):
        w = ttk.Label(parent, **kw)
        self.i18n.append((w, key))
        return w

    def _button(self, parent, key, command, **kw):
        w = ttk.Button(parent, command=command, **kw)
        self.i18n.append((w, key))
        return w

    def _build(self):
        root = self.root
        root.minsize(680, 540)
        outer = ttk.Frame(root, padding=(18, 14, 18, 12))
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)

        # Header
        header = ttk.Frame(outer)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        self._label(header, "title", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        self._label(header, "subtitle", style="Sub.TLabel").grid(row=1, column=0, sticky="w", pady=(2, 0))
        langbox = ttk.Frame(header)
        langbox.grid(row=0, column=1, rowspan=2, sticky="ne")
        self._label(langbox, "ui_language").pack(side="left", padx=(0, 6))
        self.ui_lang_cb = ttk.Combobox(langbox, state="readonly", width=10, values=[n for _, n in UI_LANGUAGES])
        self.ui_lang_cb.current([c for c, _ in UI_LANGUAGES].index(self.t.lang))
        self.ui_lang_cb.bind("<<ComboboxSelected>>", self.on_ui_language)
        self.ui_lang_cb.pack(side="left")

        ttk.Separator(outer).grid(row=1, column=0, sticky="ew", pady=10)

        # Selection form
        form = ttk.Frame(outer)
        form.grid(row=2, column=0, sticky="ew")
        form.columnconfigure(1, weight=1)
        pad = {"pady": 4}

        self._label(form, "product").grid(row=0, column=0, sticky="w", padx=(0, 12), **pad)
        self.product_cb = ttk.Combobox(form, state="readonly")
        self.product_cb.grid(row=0, column=1, columnspan=2, sticky="ew", **pad)
        self.product_cb.bind("<<ComboboxSelected>>", lambda e: self.on_product())

        self.edition_lbl = self._label(form, "edition")
        self.edition_lbl.grid(row=1, column=0, sticky="w", padx=(0, 12), **pad)
        self.edition_cb = ttk.Combobox(form, state="readonly")
        self.edition_cb.grid(row=1, column=1, sticky="ew", **pad)
        self.edition_cb.bind("<<ComboboxSelected>>", lambda e: self.on_edition())
        self.refresh_btn = self._button(form, "refresh", self.on_refresh)
        self.refresh_btn.grid(row=1, column=2, sticky="e", padx=(8, 0), **pad)

        self.lang_lbl = self._label(form, "language")
        self.lang_lbl.grid(row=2, column=0, sticky="w", padx=(0, 12), **pad)
        self.lang_cb = ttk.Combobox(form, state="readonly")
        self.lang_cb.grid(row=2, column=1, columnspan=2, sticky="ew", **pad)
        self.lang_cb.bind("<<ComboboxSelected>>", lambda e: self.on_language())

        self.arch_lbl = self._label(form, "arch")
        self.arch_lbl.grid(row=3, column=0, sticky="w", padx=(0, 12), **pad)
        self.arch_cb = ttk.Combobox(form, state="readonly")
        self.arch_cb.grid(row=3, column=1, columnspan=2, sticky="ew", **pad)

        self.url_lbl = self._label(form, "custom_url")
        self.url_var = tk.StringVar()
        self.url_entry = ttk.Entry(form, textvariable=self.url_var)
        self.url_hint = self._label(form, "custom_url_hint", style="Sub.TLabel")

        self._label(form, "save_to").grid(row=6, column=0, sticky="w", padx=(0, 12), **pad)
        self.dir_var = tk.StringVar(value=self.cfg.get("download_dir") or default_download_dir())
        ttk.Entry(form, textvariable=self.dir_var).grid(row=6, column=1, sticky="ew", **pad)
        self._button(form, "browse", self.on_browse).grid(row=6, column=2, sticky="e", padx=(8, 0), **pad)

        self.source_title = self._label(form, "source")
        self.source_title.grid(row=7, column=0, sticky="w", padx=(0, 12), **pad)
        self.source_lbl = self._label(form, "source_value", style="Sub.TLabel")
        self.source_lbl.grid(row=7, column=1, columnspan=2, sticky="w", **pad)

        # Advanced options
        self.adv = ttk.LabelFrame(outer, padding=(10, 6))
        self.i18n.append((self.adv, "advanced"))
        self.adv.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        self.adv.columnconfigure(3, weight=1)
        self._label(self.adv, "connections").grid(row=0, column=0, sticky="w")
        self.conn_var = tk.IntVar(value=int(self.cfg.get("connections", 16)))
        ttk.Spinbox(self.adv, from_=1, to=16, width=4, textvariable=self.conn_var).grid(
            row=0, column=1, sticky="w", padx=(6, 18))
        self._label(self.adv, "proxy").grid(row=0, column=2, sticky="w")
        saved_proxy = self.cfg.get("proxy")
        self.proxy_var = tk.StringVar(value=system_proxy() if saved_proxy is None else saved_proxy)
        ttk.Entry(self.adv, textvariable=self.proxy_var).grid(row=0, column=3, sticky="ew", padx=(6, 0))
        self.proxy_hint = self._label(self.adv, "proxy_hint", style="Sub.TLabel")
        self.proxy_hint.grid(row=1, column=3, sticky="w", padx=(6, 0))
        self.verify_var = tk.BooleanVar(value=bool(self.cfg.get("verify", True)))
        self.verify_chk = ttk.Checkbutton(self.adv, variable=self.verify_var)
        self.i18n.append((self.verify_chk, "verify"))
        self.verify_chk.grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 0))

        # Progress
        prog = ttk.Frame(outer)
        prog.grid(row=4, column=0, sticky="ew", pady=(14, 0))
        prog.columnconfigure(0, weight=1)
        self.file_var = tk.StringVar(value="")
        ttk.Label(prog, textvariable=self.file_var, font=self.bold_font).grid(row=0, column=0, sticky="w")
        self.hash_var = tk.StringVar(value="")
        ttk.Label(prog, textvariable=self.hash_var, style="Sub.TLabel", font=self.small_font).grid(
            row=1, column=0, sticky="w")
        self.progress = ttk.Progressbar(prog, maximum=1000, mode="determinate")
        self.progress.grid(row=2, column=0, sticky="ew", pady=(6, 4))
        self.percent_var = tk.StringVar(value="")
        ttk.Label(prog, textvariable=self.percent_var, width=7, anchor="e").grid(row=2, column=1, padx=(8, 0))
        self.stat_var = tk.StringVar(value="")
        ttk.Label(prog, textvariable=self.stat_var, style="Status.TLabel").grid(row=3, column=0, columnspan=2,
                                                                             sticky="w")

        # Buttons
        bar = ttk.Frame(outer)
        bar.grid(row=5, column=0, sticky="ew", pady=(10, 0))
        self.start_btn = self._button(bar, "start", self.on_start, style="Accent.TButton")
        self.start_btn.pack(side="left")
        self.pause_btn = ttk.Button(bar, command=self.on_pause)
        self.pause_btn.pack(side="left", padx=(8, 0))
        self.cancel_btn = self._button(bar, "cancel", self.on_cancel)
        self.cancel_btn.pack(side="left", padx=(8, 0))
        self.page_btn = self._button(bar, "official_page", self.on_official_page)
        self.page_btn.pack(side="right")
        self.copy_btn = self._button(bar, "copy_link", self.on_copy_link)
        self.copy_btn.pack(side="right", padx=(0, 8))
        self.folder_btn = self._button(bar, "open_folder", self.on_open_folder)
        self.folder_btn.pack(side="right", padx=(0, 8))

        # Log
        logf = ttk.LabelFrame(outer, padding=(6, 4))
        self.i18n.append((logf, "log"))
        logf.grid(row=6, column=0, sticky="nsew", pady=(12, 0))
        outer.rowconfigure(6, weight=1)
        logf.columnconfigure(0, weight=1)
        logf.rowconfigure(0, weight=1)
        self.log_text = tk.Text(logf, height=7, wrap="word", state="disabled", relief="flat",
                                font=self.small_font, highlightthickness=0)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(logf, orient="vertical", command=self.log_text.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=sb.set)

        self._update_buttons()

    def _apply_language(self):
        t = self.t
        self.root.title("%s %s" % (t("title"), __version__))
        for widget, key in self.i18n:
            widget.configure(text=t(key))
        self.pause_btn.configure(text=t("resume") if self.state == "paused" else t("pause"))
        self.ui_lang_cb.current([c for c, _ in UI_LANGUAGES].index(t.lang))
        index = self.product_cb.current()
        self.product_cb.configure(values=[p.title for p in PRODUCTS] + [t("product_custom")])
        if index >= 0:
            self.product_cb.current(index)
        self._fill_arch()
        self._fill_languages(keep=True)
        if not self.stat_var.get() or self.state == "idle":
            self.stat_var.set(t("ready"))

    # ------------------------------------------------------------- helpers --
    def log(self, msg):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", time.strftime("%H:%M:%S  ") + msg + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def log_threadsafe(self, msg):
        self.events.put((self.log, (msg,)))

    def run_bg(self, func, on_done=None, on_error=None):
        def worker():
            try:
                result = func()
            except Exception as e:  # reported on the UI thread
                if on_error:
                    self.events.put((on_error, (e,)))
                else:
                    self.events.put((self._show_error, (e,)))
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
        messagebox.showerror(self.t("error_title"), str(error), parent=self.root)

    def product(self):
        index = self.product_cb.current()
        return PRODUCTS[index] if 0 <= index < len(PRODUCTS) else None

    def client(self):
        return MsdlClient(proxy=self.proxy_var.get().strip() or None, log=self.log_threadsafe)

    def _update_buttons(self):
        s = self.state
        active = s in ("downloading", "paused")
        self.start_btn.configure(state="normal" if s == "idle" else "disabled")
        self.pause_btn.configure(state="normal" if active else "disabled",
                                 text=self.t("resume") if s == "paused" else self.t("pause"))
        self.cancel_btn.configure(state="normal" if active or s == "verifying" else "disabled")
        self.copy_btn.configure(state="normal" if self.link_url else "disabled")
        selecting = "readonly" if s == "idle" else "disabled"
        for cb in (self.product_cb, self.edition_cb, self.lang_cb, self.arch_cb):
            cb.configure(state=selecting)
        self.refresh_btn.configure(state="normal" if s == "idle" else "disabled")
        self.url_entry.configure(state="normal" if s == "idle" else "disabled")

    # ---------------------------------------------------------- selection --
    def on_ui_language(self, event=None):
        self.t.lang = UI_LANGUAGES[self.ui_lang_cb.current()][0]
        self.cfg.set("ui_language", self.t.lang)
        self.cfg.save()
        self._apply_language()

    def _show_custom(self, custom):
        rows = ((self.edition_lbl, self.edition_cb, self.refresh_btn), (self.lang_lbl, self.lang_cb),
                (self.arch_lbl, self.arch_cb), (self.source_title, self.source_lbl))
        for row in rows:
            for w in row:
                if custom:
                    w.grid_remove()
                else:
                    w.grid()
        if custom:
            self.url_lbl.grid(row=4, column=0, sticky="w", padx=(0, 12), pady=4)
            self.url_entry.grid(row=4, column=1, columnspan=2, sticky="ew", pady=4)
            self.url_hint.grid(row=5, column=1, columnspan=2, sticky="w")
            self.url_entry.focus_set()
        else:
            for w in (self.url_lbl, self.url_entry, self.url_hint):
                w.grid_remove()

    def on_product(self, force=False):
        product = self.product()
        self.cfg.set("product", product.key if product else CUSTOM)
        self._show_custom(product is None)
        self.link_url = ""
        self._update_buttons()
        if product is None:
            self.file_var.set("")
            self.hash_var.set("")
            return
        self._fill_arch()
        self.edition_cb.set("")
        self.lang_cb.set("")
        self.lang_cb.configure(values=[])
        self.skus = []
        self.tokens["skus"] += 1
        info = self.product_infos.get(product.key)
        if info and not force:
            self._set_editions(product, info)
            return
        self.tokens["editions"] += 1
        token = self.tokens["editions"]
        self.edition_cb.set(self.t("loading"))
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
        self.edition_cb.configure(values=[e.name for e in info.editions])
        if info.editions:
            self.edition_cb.current(0)
            self.on_edition()

    def on_refresh(self):
        if self.product() is None:
            return
        self.on_product(force=True)

    def _fill_arch(self):
        product = self.product()
        if not product:
            return
        current = self.arch_cb.current()
        self.arch_cb.configure(values=[self.t("arch_" + a) for a in product.archs])
        self.arch_cb.current(current if 0 <= current < len(product.archs) else 0)

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
        else:
            text = str(error)
        self.log(text.splitlines()[0])
        self.stat_var.set(text.splitlines()[0])
        messagebox.showerror(self.t("error_title"), text, parent=self.root)

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
            messagebox.showerror(self.t("error_title"), str(e), parent=self.root)
            return
        if not find_aria2c():
            messagebox.showerror(self.t("error_title"), self.t("no_aria2"), parent=self.root)
            return
        self._save_settings()
        product = self.product()
        self.progress.configure(value=0)
        self.percent_var.set("")
        self.hash_var.set("")

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
        arch = product.archs[max(0, self.arch_cb.current())]
        info = self.product_infos.get(product.key)
        # Reuse the session that listed the languages, unless the proxy changed since.
        client = self.sku_client
        if client is None or client.proxy != (self.proxy_var.get().strip() or None):
            client = self.client()
        self.state = "busy"
        self._update_buttons()
        self.stat_var.set(self.t("requesting_link"))
        self.log(self.t("requesting_link"))

        def fetch():
            return client.links(product, sku.id)

        def done(links):
            match = [l for l in links if l.arch == arch]
            if not match:
                self.state = "idle"
                self._update_buttons()
                self._show_error(self.t("no_arch", arch=arch))
                return
            link = match[0]
            self.link_url = link.url
            self.expected_hash = find_hash(info.hashes, sku, arch) if info else None
            self.log(self.t("link_ok", name=link.filename))
            self.state = "idle"
            self._begin_download(link.url, link.filename)

        self.run_bg(fetch, done, self._report_msdl_error)

    def _begin_download(self, url, filename):
        directory = self.dir_var.get().strip()
        path = os.path.join(directory, filename)
        control = path + ".aria2"
        self.target_path = path
        self.file_var.set("%s: %s" % (self.t("file"), filename))
        if self.expected_hash:
            self.hash_var.set("SHA-256 (Microsoft): " + self.expected_hash.upper())
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
        self.stat_var.set(self.t("starting_aria2"))
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
            self.started_at = time.time()
            self._update_buttons()
            self.stat_var.set(self.t("downloading"))

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

        def fetch():
            return self.aria2.status(gid)

        def done(status):
            self.poll_busy = False
            if gid == self.gid:
                self._on_status(status)

        def failed(error):
            self.poll_busy = False
            if gid == self.gid and (self.aria2 is None or not self.aria2.running()):
                output = self.aria2.console_output() if self.aria2 else ""
                self._download_failed("aria2c stopped unexpectedly. %s" % output)

        self.run_bg(fetch, done, failed)

    def _on_status(self, st):
        total = int(st.get("totalLength") or 0)
        done = int(st.get("completedLength") or 0)
        speed = int(st.get("downloadSpeed") or 0)
        status = st.get("status")
        if total:
            self.progress.configure(value=done * 1000 // total)
            self.percent_var.set("%.1f%%" % (done * 100.0 / total))
        eta = (total - done) / speed if speed and total else None
        if status == "paused":
            self.stat_var.set("%s    %s / %s" % (self.t("paused"), human_size(done),
                                                 human_size(total) if total else "?"))
        else:
            self.stat_var.set(self.t("stat_line", done=human_size(done), total=human_size(total) if total else "?",
                                     speed=human_size(speed), eta=human_time(eta),
                                     conns=st.get("connections", "0")))
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
        self.stat_var.set(self.t("failed", error=message))
        self.log(self.t("failed", error=message))
        messagebox.showerror(self.t("error_title"), self.t("failed", error=message), parent=self.root)

    def _verify(self):
        self.state = "verifying"
        self._update_buttons()
        self.stat_var.set(self.t("verifying"))
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
            self.log(self.t("no_hash"))
            self.log(self.t("sha256_actual", value=actual.upper()))
            self.hash_var.set("SHA-256: " + actual.upper())
            self._finished()
        elif actual.lower() == expected.lower():
            self.log(self.t("verify_ok"))
            self.hash_var.set("SHA-256 ✓ " + actual.upper())
            self._finished(note=self.t("verify_ok"))
        else:
            text = self.t("verify_bad", expected=expected.upper(), actual=actual.upper())
            self.log(text.replace("\n", " "))
            self._finished(error=text)

    def _finished(self, note=None, error=None):
        self.state = "idle"
        self._update_buttons()
        if error:
            self.stat_var.set(str(error).splitlines()[0])
            messagebox.showerror(self.t("error_title"), str(error), parent=self.root)
            return
        self.stat_var.set(self.t("done", path=self.target_path))
        text = self.t("done", path=self.target_path)
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
            if state == "paused":
                self.stat_var.set(self.t("paused"))

    def on_cancel(self):
        if self.state == "verifying":
            self.verify_cancel.set()
            self.state = "idle"
            self._update_buttons()
            self.stat_var.set(self.t("cancelled"))
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
            self.progress.configure(value=0)
            self.percent_var.set("")
            self.stat_var.set(self.t("cancelled"))
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
        icon = os.path.join(resource_dir(), "assets", "icon.png")
        if not os.path.isfile(icon):
            icon = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "icon.png")
        if os.path.isfile(icon):
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
    App(root)
    root.update_idletasks()
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    w = min(max(root.winfo_reqwidth(), 820), sw - 40)
    h = min(max(root.winfo_reqheight(), 680), sh - 90)
    x = max(0, (sw - w) // 2)
    y = max(0, (sh - h) // 3)
    root.geometry("%dx%d+%d+%d" % (w, h, x, y))
    root.mainloop()
