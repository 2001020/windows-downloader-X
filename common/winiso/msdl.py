"""Client for Microsoft's official software-download service.

This is the same service used by https://www.microsoft.com/software-download.
It hands out time-limited (24 h) links on software.download.prss.microsoft.com,
Microsoft's own global CDN, so downloads are fast from anywhere.

Flow:
  1. Read the product page -> edition ids and the official SHA-256 table.
  2. Register a random session id with Microsoft's anti-abuse services.
  3. getskuinformationbyproductedition -> languages (SKUs) of an edition.
  4. GetProductDownloadLinksBySku -> ISO links (one per architecture).
"""

import html
import re
import time
import uuid
from dataclasses import dataclass, field
from urllib.parse import unquote, urlparse

from .net import Http, HttpError

SITE = "https://www.microsoft.com"
API = SITE + "/software-download-connector/api"
PROFILE_ID = "606624d44113"
ORG_ID = "y6jn8c31"
INSTANCE_ID = "560dc9f3-1aa5-4a2f-b63c-9e18f8d0e175"


@dataclass
class Edition:
    id: str
    name: str
    name_zh: str = ""


@dataclass
class Product:
    key: str
    page: str  # path below /software-download/, "" when Microsoft retired the page
    title: str
    archs: tuple
    # Built-in edition list: used when the product page cannot be parsed, and
    # as the only list for retired products (Windows 7 / 8.1), whose pages are
    # gone although Microsoft's CDN still serves the images.
    editions: tuple = ()
    family: str = ""  # UI grouping (Windows 11 x64 and Arm64 share one tile)

    @property
    def page_url(self):
        return "%s/en-us/software-download/%s" % (SITE, self.page) if self.page else ""

    @property
    def referer(self):
        return self.page_url or "%s/en-us/software-download/windows10ISO" % SITE

    @property
    def retired(self):
        return not self.page


PRODUCTS = (
    Product("win11", "windows11", "Windows 11", ("x64",),
            (Edition("3321", "Windows 11 (multi-edition ISO for x64 devices)", "Windows 11（多版本 ISO，x64 设备）"),),
            "win11"),
    Product("win11arm", "windows11arm64", "Windows 11 Arm64", ("arm64",),
            (Edition("3324", "Windows 11 (multi-edition ISO for Arm64)", "Windows 11（多版本 ISO，Arm64 设备）"),),
            "win11"),
    Product("win10", "windows10ISO", "Windows 10", ("x64", "x86"),
            (Edition("2618", "Windows 10 (multi-edition ISO)", "Windows 10（多版本 ISO）"),), "win10"),
    Product("win81", "", "Windows 8.1", ("x64", "x86"), (
        Edition("52", "Windows 8.1 (Core / Pro)", "Windows 8.1（核心版 / 专业版）"),
        Edition("55", "Windows 8.1 N (Core / Pro)", "Windows 8.1 N（欧洲版，不含媒体组件）"),
        Edition("61", "Windows 8.1 K", "Windows 8.1 K（韩国版）"),
        Edition("62", "Windows 8.1 KN", "Windows 8.1 KN（韩国版，不含媒体组件）"),
    ), "win81"),
    # Only editions whose images were confirmed on Microsoft's CDN are listed.
    Product("win7", "", "Windows 7 SP1", ("x64", "x86"), (
        Edition("8", "Windows 7 Ultimate SP1", "Windows 7 旗舰版 SP1"),
        Edition("4", "Windows 7 Professional SP1", "Windows 7 专业版 SP1"),
        Edition("28", "Windows 7 Starter SP1 (32-bit only)", "Windows 7 简易版 SP1（仅 32 位）"),
        Edition("14", "Windows 7 Ultimate N SP1", "Windows 7 旗舰版 N SP1（欧洲版，不含媒体组件）"),
        Edition("10", "Windows 7 Home Premium N SP1", "Windows 7 家庭高级版 N SP1（欧洲版，不含媒体组件）"),
    ), "win7"),
)


@dataclass
class Sku:
    id: str
    language: str  # English name, e.g. "Chinese (Simplified)"
    localized_language: str
    product_name: str  # e.g. "Windows 11 25H2"


@dataclass
class DownloadLink:
    url: str
    arch: str  # x64 / x86 / arm64
    filename: str
    expires: str = ""


@dataclass
class ProductInfo:
    editions: list
    hashes: dict = field(default_factory=dict)  # normalised "language bits" -> sha256
    from_fallback: bool = False


class MsdlError(Exception):
    pass


class BlockedError(MsdlError):
    """Microsoft's anti-abuse service ("Sentinel") refused the request."""


class NoLinksError(MsdlError):
    """Microsoft has no image for this edition / language combination."""


def normalise(text):
    return re.sub(r"[^a-z0-9]", "", text.lower())


def bits_for_arch(arch):
    return "32bit" if arch == "x86" else "64bit"


def parse_editions(page_html):
    select = re.search(r'<select[^>]*id="product-edition".*?</select>', page_html, re.S)
    scope = select.group(0) if select else page_html
    editions = []
    for value, name in re.findall(r'<option[^>]*value="(\d+)"[^>]*>(.*?)</option>', scope, re.S):
        name = html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", name))).strip()
        editions.append(Edition(value, name))
    return editions


def parse_hashes(page_html):
    """Parse the "Verify your download" table: 'Chinese Simplified 64-bit' -> SHA-256."""
    hashes = {}
    for label, value in re.findall(r"<tr>\s*<td>(.*?)</td>\s*<td>(.*?)</td>", page_html, re.S):
        label = html.unescape(re.sub(r"<[^>]+>", "", label))
        value = re.sub(r"<[^>]+>|\s", "", value)
        if re.fullmatch(r"[0-9A-Fa-f]{64}", value):
            hashes[normalise(label)] = value.lower()
    return hashes


def arch_from_link(download_type, url):
    name = urlparse(url).path.rsplit("/", 1)[-1].lower()
    if re.search(r"(arm64|_a64)", name):
        return "arm64"
    if re.search(r"(x64|amd64)", name):
        return "x64"
    if re.search(r"(x32|x86|_32)", name):
        return "x86"
    return {0: "x86", 1: "x64", 2: "arm64"}.get(download_type, "x64")


def clean_product_name(name):
    return re.sub(r"_+v\d+$", "", name, flags=re.I).replace("  ", " ").strip()


def _errors(payload):
    if not isinstance(payload, dict):
        return []
    errors = list(payload.get("Errors") or [])
    container = payload.get("ValidationContainer") or {}
    errors += list(container.get("Errors") or [])
    return errors


def _raise_for_errors(payload):
    errors = _errors(payload)
    if not errors:
        return
    text = "; ".join(str(e.get("Value") or e.get("Key") or e) for e in errors)
    for e in errors:
        if "sentinel" in str(e.get("Key", "")).lower() or e.get("Type") in (8, 9):
            raise BlockedError(text)
    raise MsdlError(text)


class MsdlClient:
    def __init__(self, proxy=None, log=None):
        self.proxy = proxy
        self.http = Http(proxy=proxy)
        self.log = log or (lambda msg: None)
        self.session_id = None

    # -- product page -------------------------------------------------------
    def product_info(self, product):
        if product.retired:
            return ProductInfo(list(product.editions), {})
        try:
            page = self.http.get_text(product.page_url)
            editions = parse_editions(page)
            hashes = parse_hashes(page)
            known = {e.id: e.name_zh for e in product.editions}
            for e in editions:
                e.name_zh = known.get(e.id, "")
            if editions:
                return ProductInfo(editions, hashes)
            self.log("No editions found on %s, using built-in list" % product.page_url)
        except HttpError as e:
            self.log("Could not read %s (%s), using built-in list" % (product.page_url, e))
        return ProductInfo(list(product.editions), {}, True)

    # -- session ------------------------------------------------------------
    def new_session(self, referer):
        """Create a session id and register it with Microsoft's anti-abuse checks.

        These calls are best effort: when they fail the API may still work.
        """
        self.session_id = str(uuid.uuid4())
        sid = self.session_id
        try:
            self.http.get("https://vlscppe.microsoft.com/tags?org_id=%s&session_id=%s" % (ORG_ID, sid), referer)
        except HttpError as e:
            self.log("Session registration (vlscppe) failed: %s" % e)
        try:
            js = self.http.get_text(
                "https://ov-df.microsoft.com/mdt.js?instanceId=%s&PageId=si&session_id=%s" % (INSTANCE_ID, sid),
                referer)
            w = re.search(r"[?&]w=([A-F0-9]+)", js)
            rticks = re.search(r'rticks=\"?\+?(\d+)', js)
            if w and rticks:
                self.http.get(
                    "https://ov-df.microsoft.com/?session_id=%s&CustomerId=%s&PageId=si&w=%s&mdt=%d&rticks=%s"
                    % (sid, INSTANCE_ID, w.group(1), int(time.time() * 1000), rticks.group(1)),
                    referer)
        except HttpError as e:
            self.log("Session registration (ov-df) failed: %s" % e)
        return sid

    # -- API ----------------------------------------------------------------
    def skus(self, product, edition_id):
        if not self.session_id:
            self.new_session(product.referer)
        url = ("%s/getskuinformationbyproductedition?profile=%s&ProductEditionId=%s"
               "&SKU=undefined&friendlyFileName=undefined&Locale=en-US&sessionID=%s"
               % (API, PROFILE_ID, edition_id, self.session_id))
        payload = self.http.get_json(url, product.referer)
        _raise_for_errors(payload)
        result = []
        for s in payload.get("Skus") or []:
            result.append(Sku(str(s.get("Id")), s.get("Language") or "",
                              s.get("LocalizedLanguage") or s.get("Language") or "",
                              clean_product_name(s.get("ProductDisplayName") or "")))
        if not result:
            raise MsdlError("Microsoft returned no languages for this edition")
        return result

    def links(self, product, sku_id, retry=True):
        if not self.session_id:
            self.new_session(product.referer)
        url = ("%s/GetProductDownloadLinksBySku?profile=%s&productEditionId=undefined"
               "&SKU=%s&friendlyFileName=undefined&Locale=en-US&sessionID=%s"
               % (API, PROFILE_ID, sku_id, self.session_id))
        payload = self.http.get_json(url, product.referer)
        try:
            _raise_for_errors(payload)
        except BlockedError:
            if not retry:
                raise
            # A fresh, freshly registered session sometimes succeeds.
            self.log("Request rejected by Microsoft, retrying with a new session")
            self.new_session(product.referer)
            return self.links(product, sku_id, retry=False)
        result = []
        for opt in payload.get("ProductDownloadOptions") or []:
            uri = opt.get("Uri")
            if not uri:
                continue
            filename = unquote(urlparse(uri).path.rsplit("/", 1)[-1]) or "windows.iso"
            result.append(DownloadLink(uri, arch_from_link(opt.get("DownloadType"), uri), filename,
                                       payload.get("DownloadExpirationDatetime") or ""))
        if not result:
            raise NoLinksError("Microsoft returned no download links")
        return result


def find_hash(hashes, sku, arch):
    bits = bits_for_arch(arch)
    for name in (sku.language, sku.localized_language):
        value = hashes.get(normalise(name) + bits)
        if value:
            return value
    return None
