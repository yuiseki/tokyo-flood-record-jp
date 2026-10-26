"""Download the 浸水実績図 (Shapefile, one zip per year) of the Tokyo Flood Risk Information System.

Saves the page, the listing the page calls, the attribute list (PDF) and every zip the listing
offers, as served, with sha256 and Last-Modified, in data/raw/<version>/MANIFEST.json. Stops when
the page does not state Creative Commons Attribution 4.0, or when a file is listed but not public.
Also fetches the municipalities of Tokyo (N03, 2026-01-01) under data/docs/ (not published), used only
to check the coordinates. The version is the UTC date of the run.

    uv run python scripts/01_download.py [--version 2026-10-26]
"""

import argparse
import datetime as dt
import hashlib
import json
import sys
import time
import urllib.request
from pathlib import Path

import tfr

ROOT = Path(__file__).parents[1]
UA = "tokyo-flood-record-jp/0.1 (+https://github.com/yuiseki/tokyo-flood-record-jp)"


def get(url: str) -> tuple[bytes, dict]:
    with urllib.request.urlopen(
        urllib.request.Request(url, headers={"User-Agent": UA}), timeout=120
    ) as r:
        return r.read(), {h.lower(): v for h, v in r.headers.items()}


def entry(url: str, body: bytes, h: dict) -> dict:
    return {"url": url, "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(),
            "last_modified": h.get("last-modified")}  # fmt: skip


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default=dt.datetime.now(dt.UTC).strftime("%Y-%m-%d"))
    args = ap.parse_args()
    raw = ROOT / "data" / "raw" / args.version
    raw.mkdir(parents=True, exist_ok=True)
    page, ph = get(tfr.PAGE_URL)
    text = page.decode("utf-8")
    if tfr.LICENSE_PHRASE not in text or tfr.LICENSE_LINK not in text:
        raise SystemExit("the page no longer states Creative Commons Attribution 4.0: stopping")
    files = {"page.html": entry(tfr.PAGE_URL, page, ph)}
    (raw / "page.html").write_bytes(page)
    listing, lh = get(tfr.LISTING_URL)
    rows = json.loads(listing)
    (raw / "listing.json").write_bytes(listing)
    files["listing.json"] = entry(tfr.LISTING_URL, listing, lh)
    pdf, dh = get(tfr.ATTR_PDF_URL)
    (raw / "attributes.pdf").write_bytes(pdf)
    files["attributes.pdf"] = entry(tfr.ATTR_PDF_URL, pdf, dh)
    years = {}
    for r in sorted(rows, key=lambda r: r["year"]):
        if r["year"] in years:
            raise SystemExit(f"year {r['year']} twice in the listing")
        years[r["year"]] = {k: r[k] for k in ("filename", "path", "is_public", "is_enable")}
        if not r["path"]:
            continue
        if not r["is_public"]:
            raise SystemExit(f"{r['year']} has a file but is not public: stopping")
        url = tfr.zip_url(r["year"], r["path"])
        time.sleep(1)
        body, h = get(url)
        name = f"{r['year']}.zip"
        (raw / name).write_bytes(body)
        files[name] = {**entry(url, body, h), "filename": r["filename"]}
        print(name, len(body))
    docs = ROOT / "data" / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    time.sleep(1)
    n03, _ = get(tfr.N03_URL)
    (docs / Path(tfr.N03_URL).name).write_bytes(n03)
    manifest = {"retrieved": args.version, "page": tfr.PAGE_URL, "license": "CC BY 4.0",
                "years_in_listing": years, "files": files,
                "n03": {"url": tfr.N03_URL, "sha256": hashlib.sha256(n03).hexdigest()}}  # fmt: skip
    (raw / "MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(sum(1 for y in years.values() if y["path"]), "zips")
    return 0


if __name__ == "__main__":
    sys.exit(main())
