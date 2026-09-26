"""Program entry point shared by the Windows, macOS and Linux builds."""

import importlib
import os
import ssl
import sys

from . import APP_NAME, __version__


def selftest(out_path=None, network=False):
    """Check that a packaged build is complete. Used by CI on every platform."""
    lines = []
    ok = True

    def check(name, func):
        nonlocal ok
        try:
            lines.append("PASS %s: %s" % (name, func()))
        except Exception as e:
            ok = False
            lines.append("FAIL %s: %r" % (name, e))

    from .aria2 import Aria2, find_aria2c
    from .net import bundled_ca_file, ca_file_for_aria2, make_ssl_context

    check("version", lambda: "%s %s, Python %s, %s" % (APP_NAME, __version__, sys.version.split()[0],
                                                       ssl.OPENSSL_VERSION))
    check("aria2c", lambda: find_aria2c() or _fail("not found"))
    check("aria2c --version", lambda: Aria2().version() or _fail("no output"))

    def rpc():
        a = Aria2()
        a.start()
        try:
            return a.call("aria2.getVersion")["version"]
        finally:
            a.stop()

    check("aria2c rpc", rpc)
    check("ca bundle", lambda: bundled_ca_file() or _fail("certifi missing"))
    check("aria2 ca option", lambda: ca_file_for_aria2() or "not needed on this platform")
    check("ssl context", lambda: "%d CA certs" % len(make_ssl_context().get_ca_certs()))

    def tcl():
        import tkinter

        interp = tkinter.Tcl()
        return "Tcl %s" % interp.eval("info patchlevel")

    check("tcl", tcl)
    check("gui module", lambda: importlib.import_module(".gui", __package__).__name__)

    def theme():
        import sv_ttk

        path = sv_ttk.TCL_THEME_FILE_PATH
        if not path.is_file():
            _fail("%s missing" % path)
        return "sv_ttk %s" % path.parent.name

    check("theme", theme)

    def ui_text():
        from .i18n import FORBIDDEN_CHARS, LANGUAGE_ZH, STRINGS
        from .msdl import PRODUCTS

        texts = [v for entry in STRINGS.values() for v in entry.values()] + list(LANGUAGE_ZH.values())
        texts += [n for p in PRODUCTS for e in p.editions for n in (e.name, e.name_zh)] + [p.title for p in PRODUCTS]
        bad = [t for t in texts if any(ch in t for ch in FORBIDDEN_CHARS)]
        if bad:
            _fail("forbidden characters in %r" % bad)
        return "%d strings clean" % len(texts)

    check("ui text", ui_text)

    if network:
        def editions():
            from .msdl import PRODUCTS, MsdlClient

            info = MsdlClient().product_info(PRODUCTS[0])
            if info.from_fallback:
                _fail("product page not readable")
            return "%s, %d hashes" % (", ".join(e.id for e in info.editions), len(info.hashes))

        check("microsoft product page", editions)

        def aria2_https():
            import tempfile
            import time

            a = Aria2()
            a.start()
            try:
                with tempfile.TemporaryDirectory() as tmp:
                    gid = a.add("https://www.microsoft.com/favicon.ico", tmp, "favicon.ico", connections=1)
                    deadline = time.time() + 45
                    while time.time() < deadline:
                        st = a.status(gid)
                        if st["status"] == "complete":
                            return "%s bytes over HTTPS" % st["completedLength"]
                        if st["status"] == "error":
                            _fail("%s %s" % (st.get("errorCode"), st.get("errorMessage")))
                        time.sleep(0.5)
                    _fail("timed out")
            finally:
                a.stop()

        check("aria2c https download", aria2_https)

    report = "\n".join(lines) + "\nRESULT: %s\n" % ("OK" if ok else "FAILED")
    if out_path:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(report)
    try:
        sys.stdout.write(report)
    except Exception:
        pass
    return 0 if ok else 1


def _fail(msg):
    raise RuntimeError(msg)


def main():
    args = sys.argv[1:]
    if args and args[0] == "--selftest":
        out = args[1] if len(args) > 1 and not args[1].startswith("--") else None
        sys.exit(selftest(out, network="--network" in args))
    if args and args[0] in ("--version", "-V"):
        print("%s %s" % (APP_NAME, __version__))
        return
    if getattr(sys, "frozen", False) and sys.platform == "darwin":
        # Finder launches apps with "/" as working directory.
        os.chdir(os.path.expanduser("~"))
    from .gui import main as gui_main

    gui_main()
