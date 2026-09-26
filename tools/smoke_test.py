"""End-to-end check against Microsoft's live service.

    python tools/smoke_test.py [--download-seconds N]

1. reads every product page (editions + SHA-256 table),
2. lists the languages of each edition,
3. asks for a real download link (Windows 11 x64, English International),
4. downloads from Microsoft's CDN with aria2 for a few seconds and reports speed.

Microsoft sometimes rejects requests from data-centre IPs (CI runners); that
is reported as a warning, not a failure, because it says nothing about the
code. Anything else that goes wrong fails the run.
"""

import argparse
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "common"))

from winiso.aria2 import Aria2  # noqa: E402
from winiso.msdl import PRODUCTS, BlockedError, MsdlClient, find_hash  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--download-seconds", type=int, default=15)
    args = parser.parse_args()

    client = MsdlClient(log=lambda m: print("  log:", m))
    infos = {}
    for product in PRODUCTS:
        info = client.product_info(product)
        infos[product.key] = info
        print("%-24s editions=%s hashes=%d fallback=%s" % (
            product.title, [(e.id, e.name) for e in info.editions], len(info.hashes), info.from_fallback))
        assert info.editions, "no editions for %s" % product.title
        assert not info.from_fallback, "product page of %s could not be parsed" % product.title
        assert info.hashes, "no SHA-256 table on %s" % product.page_url

    for product in PRODUCTS:
        skus = client.skus(product, infos[product.key].editions[0].id)
        print("%-24s %s: %d languages" % (product.title, skus[0].product_name, len(skus)))
        for arch in product.archs:
            missing = [s.language for s in skus if not find_hash(infos[product.key].hashes, s, arch)]
            print("    %s: SHA-256 known for %d/%d languages %s" % (
                arch, len(skus) - len(missing), len(skus), ("(missing: %s)" % missing) if missing else ""))

    product = PRODUCTS[0]
    skus = client.skus(product, infos[product.key].editions[0].id)
    sku = next(s for s in skus if s.language == "English International")
    try:
        links = client.links(product, sku.id)
    except BlockedError as e:
        print("::warning::Microsoft rejected the link request from this runner (%s)" % e)
        return 0
    for link in links:
        print("link: %s %s (expires %s)" % (link.arch, link.filename, link.expires))
        print("      %s" % link.url.split("?")[0])
    link = next(l for l in links if l.arch == "x64")
    expected = find_hash(infos[product.key].hashes, sku, "x64")
    print("expected SHA-256: %s" % expected)
    assert expected, "no hash for English International x64"

    if args.download_seconds <= 0:
        return 0
    aria2 = Aria2()
    aria2.start()
    print(aria2.version())
    with tempfile.TemporaryDirectory() as tmp:
        gid = aria2.add(link.url, tmp, link.filename, connections=16)
        started = time.time()
        st = {}
        peak = 0
        while time.time() - started < args.download_seconds:
            time.sleep(1)
            st = aria2.status(gid)
            peak = max(peak, int(st.get("downloadSpeed") or 0))
            print("  %5.1f MB/s  %7.1f MB  %s connections" % (
                int(st.get("downloadSpeed") or 0) / 1e6, int(st.get("completedLength") or 0) / 1e6,
                st.get("connections")))
            if st.get("status") in ("error", "complete"):
                break
        t = time.time()
        aria2.remove(gid)
        print("forceRemove answered in %.1fs" % (time.time() - t))
        aria2.stop()
    done = int(st.get("completedLength") or 0)
    total = int(st.get("totalLength") or 0)
    print("aria2: status=%s %.1f MB of %.1f MB in %ds, peak %.1f MB/s, %s connections" % (
        st.get("status"), done / 1e6, total / 1e6, args.download_seconds, peak / 1e6, st.get("connections")))
    if st.get("status") == "error":
        print("aria2 error: %s %s" % (st.get("errorCode"), st.get("errorMessage")))
        return 1
    assert total > 3_000_000_000, "unexpected ISO size"
    assert done > 0, "nothing downloaded"
    return 0


if __name__ == "__main__":
    sys.exit(main())
