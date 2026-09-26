"""Temporary probe: which legacy Windows editions still get download links."""

import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "common"))

from winiso.msdl import MsdlClient, MsdlError, Product  # noqa: E402
from winiso.net import USER_AGENT, make_ssl_context  # noqa: E402

REF = Product("ref", "windows10ISO", "ref", ("x64",))
EDITIONS = [52, 61, 62, 68, 71, 2, 6, 10, 12, 14, 16, 18, 20, 22, 24, 26, 28]
WANT = ("English", "Chinese (Simplified)", "Korean")


def head(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Range": "bytes=0-1023"})
    opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=make_ssl_context()))
    try:
        with opener.open(req, timeout=30) as r:
            return "%s %s range=%s type=%s" % (r.status, r.geturl().split("?")[0][:90],
                                               r.headers.get("Content-Range"), r.headers.get("Content-Type"))
    except Exception as e:
        return "ERR %r" % e


client = MsdlClient(log=lambda m: print("  log:", m))
for ed in EDITIONS:
    try:
        skus = client.skus(REF, ed)
    except MsdlError as e:
        print("edition %s: skus failed %s" % (ed, e))
        continue
    print("edition %s: %s, %d languages" % (ed, skus[0].product_name, len(skus)))
    tried = 0
    for sku in skus:
        if sku.language not in WANT or (ed != 52 and tried):
            continue
        tried += 1
        time.sleep(15)
        client.new_session(REF.page_url)
        try:
            links = client.links(REF, sku.id)
        except Exception as e:
            print("  %s %s: links failed: %s" % (sku.id, sku.language, e))
            continue
        for l in links:
            print("  %s %s: %s %s" % (sku.id, sku.language, l.arch, l.filename))
            print("      host=%s" % l.url.split("/")[2])
            print("      %s" % head(l.url))
