"""Look and feel: the Sun Valley ttk theme (light / dark) and fonts."""

import subprocess
import sys
import tkinter as tk
from tkinter import font as tkfont, ttk

try:
    import sv_ttk
except ImportError:  # the app still works with the stock ttk theme
    sv_ttk = None

PALETTE = {
    "light": {"bg": "#fafafa", "fg": "#1c1c1c", "muted": "#5f5f5f", "accent": "#005fb8",
              "ok": "#0f7b0f", "warn": "#9d5d00", "error": "#c42b1c", "field": "#ffffff", "border": "#e5e5e5"},
    "dark": {"bg": "#1c1c1c", "fg": "#fafafa", "muted": "#a8a8a8", "accent": "#57c8ff",
             "ok": "#6ccb5f", "warn": "#fce100", "error": "#ff99a4", "field": "#2b2b2b", "border": "#3a3a3a"},
}


def system_dark(env=None):
    """True when the operating system uses a dark appearance."""
    try:
        if sys.platform.startswith("win"):
            import winreg

            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                 r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return value == 0
        if sys.platform == "darwin":
            out = subprocess.run(["defaults", "read", "-g", "AppleInterfaceStyle"], capture_output=True,
                                 text=True, timeout=5).stdout
            return out.strip().lower() == "dark"
        out = subprocess.run(["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
                             capture_output=True, text=True, timeout=5, env=env).stdout
        return "dark" in out.lower()
    except Exception:
        return False


def _families():
    try:
        return set(tkfont.families())
    except tk.TclError:
        return set()


def font_family(lang):
    families = _families()
    if sys.platform.startswith("win"):
        wanted = ("Microsoft YaHei UI", "Microsoft YaHei") if lang == "zh" else ()
        wanted += ("Segoe UI Variable Text", "Segoe UI")
    elif sys.platform == "darwin":
        wanted = ("PingFang SC",) if lang == "zh" else ()
    else:
        wanted = ("Noto Sans CJK SC", "Source Han Sans SC", "WenQuanYi Micro Hei") if lang == "zh" else ()
        wanted += ("Noto Sans", "Cantarell", "Ubuntu", "DejaVu Sans")
    for name in wanted:
        if name in families:
            return name
    return tkfont.nametofont("TkDefaultFont").actual("family")


class Theme:
    def __init__(self, root):
        self.root = root
        self.style = ttk.Style(root)
        self.mode = "light"
        self.fonts = {}
        # Pixel sizes below are for a 96 dpi screen; scale them on HiDPI
        # Windows / Linux. macOS already works in points.
        try:
            dpi = root.winfo_fpixels("1i")
        except tk.TclError:
            dpi = 96
        self.scale = 1.0 if sys.platform == "darwin" else max(1.0, round(dpi / 96 * 4) / 4)

    def px(self, n):
        return int(round(n * self.scale))

    @property
    def colors(self):
        return PALETTE[self.mode]

    def apply(self, mode, lang):
        """mode: "system", "light" or "dark"."""
        if mode == "system":
            mode = "dark" if system_dark() else "light"
        self.mode = mode if mode in PALETTE else "light"
        if sv_ttk is not None:
            try:
                sv_ttk.set_theme(self.mode, self.root)
                self._hook_theme_changed()
            except Exception:
                pass
        self._fonts(lang)
        self._styles()
        self._title_bar()

    def _hook_theme_changed(self):
        """Keep label styles working under Sun Valley.

        On every <<ThemeChanged>> (also fired by each style change) the theme
        calls tk_setPalette, which stamps explicit colours onto all existing
        ttk labels and so hides their styles. Clear them again right after.
        """
        if getattr(self, "_hooked", False):
            return
        self._hooked = True
        self.root.bind_class(self.root.winfo_class(), "<<ThemeChanged>>",
                             lambda e: self._reset_label_colors(self.root), add="+")

    def _reset_label_colors(self, widget):
        for child in widget.winfo_children():
            if child.winfo_class() == "TLabel":
                child.configure(foreground="", background="")
            self._reset_label_colors(child)

    def _fonts(self, lang):
        family = font_family(lang)
        # Negative sizes are pixels, so the layout looks the same on every platform.
        spec = {
            "body": (-14, "normal"), "strong": (-14, "bold"), "caption": (-12, "normal"),
            "subtitle": (-18, "bold"), "title": (-24, "bold"), "big": (-26, "bold"), "mono": (-12, "normal"),
        }
        for name, (size, weight) in spec.items():
            size = -self.px(-size)
            fam = family
            if name == "mono":
                fam = "Consolas" if sys.platform.startswith("win") else "Menlo" if sys.platform == "darwin" \
                    else "DejaVu Sans Mono"
            if name in self.fonts:
                self.fonts[name].configure(family=fam, size=size, weight=weight)
            else:
                self.fonts[name] = tkfont.Font(self.root, family=fam, size=size, weight=weight)
        for named in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont", "TkCaptionFont"):
            try:
                tkfont.nametofont(named).configure(family=family, size=-self.px(14))
            except tk.TclError:
                pass
        # Fonts used inside the Sun Valley theme itself.
        for named, key in (("SunValleyBodyFont", "body"), ("SunValleyBodyStrongFont", "strong"),
                           ("SunValleyCaptionFont", "caption"), ("SunValleyBodyLargeFont", "subtitle"),
                           ("SunValleySubtitleFont", "subtitle"), ("SunValleyTitleFont", "title")):
            try:
                f = self.fonts[key]
                self.root.tk.call("font", "configure", named, "-family", f.cget("family"),
                                  "-size", f.cget("size"), "-weight", f.cget("weight"))
            except tk.TclError:
                pass

    def _styles(self):
        c, f, s = self.colors, self.fonts, self.style
        s.configure("TLabel", font=f["body"])
        s.configure("Title.TLabel", font=f["title"])
        s.configure("Heading.TLabel", font=f["subtitle"])
        s.configure("Strong.TLabel", font=f["strong"])
        s.configure("Big.TLabel", font=f["big"], foreground=c["accent"])
        s.configure("Muted.TLabel", font=f["caption"], foreground=c["muted"])
        s.configure("Value.TLabel", font=f["strong"])
        s.configure("Ok.TLabel", font=f["caption"], foreground=c["ok"])
        s.configure("Warn.TLabel", font=f["caption"], foreground=c["warn"])
        s.configure("Mono.TLabel", font=f["mono"], foreground=c["muted"])
        s.configure("Accent.TButton", font=f["strong"])
        s.configure("Big.Accent.TButton", font=f["strong"], padding=(self.px(22), self.px(6)))
        s.configure("Tile.Toggle.TButton", font=f["strong"], padding=(self.px(10), self.px(9)))
        s.configure("Seg.Toggle.TButton", font=f["body"], padding=(self.px(12), self.px(4)))
        s.configure("Link.TButton", font=f["body"])
        if sv_ttk is None:
            # Stock ttk: keep the custom styles readable.
            s.configure("Tile.Toggle.TButton", relief="raised")

    def refresh_title_bar(self):
        self._title_bar()

    def _title_bar(self):
        """Match the Windows title bar to the theme (Windows 10 20H1 and later)."""
        if not sys.platform.startswith("win"):
            return
        try:
            import ctypes

            self.root.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            value = ctypes.c_int(1 if self.mode == "dark" else 0)
            for attribute in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (new, old)
                if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(value),
                                                              ctypes.sizeof(value)) == 0:
                    break
            # Nudge Windows into repainting the frame.
            ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0027)
        except Exception:
            pass
