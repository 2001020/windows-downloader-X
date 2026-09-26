"""Small HTTP helper built on urllib: CA handling, proxy and browser headers."""

import gzip
import json
import os
import ssl
import sys
import urllib.error
import urllib.request

# The Microsoft download pages only offer ISO files to non-Windows browsers,
# so always present ourselves as desktop Firefox on Linux.
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64; rv:130.0) Gecko/20100101 Firefox/130.0"

# Certificate bundles shipped by common Linux / BSD distributions.
SYSTEM_CA_FILES = (
    "/etc/ssl/certs/ca-certificates.crt",  # Debian, Ubuntu, Arch, Gentoo, Alpine
    "/etc/pki/tls/certs/ca-bundle.crt",  # Fedora, RHEL, CentOS
    "/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem",  # Fedora, RHEL
    "/etc/ssl/ca-bundle.pem",  # openSUSE
    "/etc/ssl/cert.pem",  # Alpine, macOS, BSD
)


def bundled_ca_file():
    try:
        import certifi

        path = certifi.where()
        if os.path.isfile(path):
            return path
    except Exception:
        pass
    return None


def system_ca_file():
    if sys.platform.startswith("win") or sys.platform == "darwin":
        return None
    for path in SYSTEM_CA_FILES:
        if os.path.isfile(path):
            return path
    return None


def ca_file_for_aria2():
    """CA bundle for aria2c builds that link OpenSSL (the static Linux build).

    Windows (WinTLS) and macOS (AppleTLS) builds use the OS trust store and
    need nothing.
    """
    if sys.platform.startswith("win") or sys.platform == "darwin":
        return None
    return system_ca_file() or bundled_ca_file()


def make_ssl_context():
    ctx = ssl.create_default_context()
    # A frozen Python cannot rely on the build machine's OpenSSL paths, and the
    # python.org macOS build never reads the keychain, so add explicit bundles.
    for path in (system_ca_file(), bundled_ca_file()):
        if path:
            try:
                ctx.load_verify_locations(cafile=path)
            except Exception:
                pass
    return ctx


class HttpError(Exception):
    pass


class Http:
    def __init__(self, proxy=None, timeout=30):
        self.timeout = timeout
        handlers = [urllib.request.HTTPSHandler(context=make_ssl_context())]
        if proxy:
            handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
        else:
            handlers.append(urllib.request.ProxyHandler({}))
        self.opener = urllib.request.build_opener(*handlers)

    def get(self, url, referer=None, accept="*/*"):
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": accept,
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip",
        }
        if referer:
            headers["Referer"] = referer
        req = urllib.request.Request(url, headers=headers)
        try:
            with self.opener.open(req, timeout=self.timeout) as resp:
                data = resp.read()
                if resp.headers.get("Content-Encoding", "").lower() == "gzip":
                    data = gzip.decompress(data)
                return data
        except urllib.error.HTTPError as e:
            raise HttpError("HTTP %d: %s" % (e.code, url.split("?")[0])) from e
        except (urllib.error.URLError, OSError) as e:
            reason = getattr(e, "reason", e)
            raise HttpError("%s: %s" % (reason, url.split("?")[0])) from e

    def get_text(self, url, referer=None):
        return self.get(url, referer, "text/html,application/xhtml+xml,*/*").decode("utf-8", "replace")

    def get_json(self, url, referer=None):
        raw = self.get(url, referer, "application/json, text/plain, */*")
        try:
            return json.loads(raw.decode("utf-8-sig"))
        except ValueError as e:
            raise HttpError("Unexpected response (not JSON): %s" % url.split("?")[0]) from e


def system_proxy():
    """Return the OS-configured HTTP(S) proxy, or "" when there is none."""
    try:
        proxies = urllib.request.getproxies()
    except Exception:
        return ""
    for key in ("https", "http"):
        value = proxies.get(key)
        if value and not value.lower().startswith("socks"):
            if "://" not in value:
                value = "http://" + value
            return value
    return ""
