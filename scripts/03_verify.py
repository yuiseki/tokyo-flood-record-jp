"""Check both Parquet files against the zips as served, with a second reader of Shapefiles.

The export reads the zips with pyshp. Here every layer's .dbf (cp932, or UTF-8 when a .cpg says so)
and .shp are parsed by hand from their byte layout: the header, the field descriptors, the records;
a polygon record is its type, bounding box, part offsets and the doubles of x and y, a point record
its two doubles. For every row of both files: each attribute equals the source's (blank is null; a
number in a text column is its digits; a date is the date of its YYYYMMDD), `year`, `source_zip`,
`layer` and `row` are the position in the source, and the vertices of the geometry equal the
source's, projected from JGD2000 / plane rectangular CS IX and, inverted, give the plane coordinates
back to a micrometre. Also: no record is marked deleted, there are as many rows as records, the
sha256 of each zip equals the manifest's, and the point (or a representative point of the polygon)
lies in the municipality that the record names in `munic`, among the municipalities of N03
(2026-01-01): the check behind reading these files as zone IX. Names that N03 does not have
(municipalities merged since) are counted apart.

    uv run python scripts/03_verify.py
"""

import datetime as dt
import hashlib
import io
import json
import struct
import sys
import zipfile
from collections import Counter
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
import shapefile
import shapely
import tfr
from pyproj import Transformer
from shapely.geometry import shape
from shapely.strtree import STRtree

ROOT = Path(__file__).parents[1]


def read_dbf(b: bytes, enc: str):
    """(field names, records as lists of str/int/float/date/None) of a dBASE III file."""
    n, hlen, rlen = struct.unpack("<IHH", b[4:12])
    fields, pos = [], 32
    while b[pos] != 0x0D:
        raw = b[pos : pos + 32]
        fields.append((raw[:11].split(b"\0")[0].decode(enc), chr(raw[11]), raw[16], raw[17]))
        pos += 32
    recs = []
    for i in range(n):
        rec = b[hlen + i * rlen : hlen + (i + 1) * rlen]
        assert rec[:1] == b" ", f"record {i} is marked deleted"
        off, row = 1, []
        for _, typ, ln, dec in fields:
            s = rec[off : off + ln].decode(enc).rstrip(" \0")
            off += ln
            if typ == "N":
                # blank, or a run of asterisks (the marker of a number that does not fit), is null
                null = not s.strip() or set(s.strip()) == {"*"}
                v = None if null else int(s) if dec == 0 else float(s)
            elif typ == "D":
                # blank, or 00000000, is null
                v = dt.date(int(s[:4]), int(s[4:6]), int(s[6:8])) if s.strip("0 ") else None
            else:
                assert typ == "C", typ
                v = s or None
            row.append(v)
        recs.append(row)
    return [f[0] for f in fields], recs


def read_shapes(b: bytes):
    """Each record of a .shp as a list of rings (polygons) or one (x, y) (points): the raw coordinates."""
    out, pos = [], 100
    while pos < len(b):
        _, words = struct.unpack(">ii", b[pos : pos + 8])
        typ = struct.unpack("<i", b[pos + 8 : pos + 12])[0]
        body = b[pos + 12 : pos + 8 + words * 2]
        if typ == 1:
            out.append(("POINT", np.array([struct.unpack("<2d", body[:16])])))
        elif typ == 5:
            nparts, npts = struct.unpack("<ii", body[32:40])
            parts = struct.unpack(f"<{nparts}i", body[40 : 40 + 4 * nparts])
            xy = np.frombuffer(
                body[40 + 4 * nparts : 40 + 4 * nparts + 16 * npts], dtype="<f8"
            ).reshape(-1, 2)
            assert len(xy) == npts and parts[0] == 0
            out.append(("POLYGON", xy))
        else:
            raise AssertionError(f"shape type {typ}")
        pos += 8 + words * 2
    return out


def vertices(g) -> np.ndarray:
    """All the vertices of a geometry (every ring, closing vertex included), sorted."""
    xy = shapely.get_coordinates(g)
    return xy[np.lexsort((xy[:, 1], xy[:, 0]))]


def main() -> int:
    run = sorted((ROOT / "data" / "raw").glob("*/MANIFEST.json"))[-1].parent
    manifest = json.loads((run / "MANIFEST.json").read_text())
    cols = json.loads((ROOT / "data/parquet/columns.json").read_text())
    assert cols["run"] == run.name
    to_ll = Transformer.from_crs(tfr.PLANE_EPSG, tfr.GEOGRAPHIC_EPSG, always_xy=True)
    to_plane = Transformer.from_crs(tfr.GEOGRAPHIC_EPSG, tfr.PLANE_EPSG, always_xy=True)
    with zipfile.ZipFile(ROOT / "data" / "docs" / Path(tfr.N03_URL).name) as z:
        stem = next(n[:-4] for n in z.namelist() if n.endswith(".shp"))
        sf = shapefile.Reader(shp=io.BytesIO(z.read(stem + ".shp")), shx=io.BytesIO(z.read(stem + ".shx")),
                              dbf=io.BytesIO(z.read(stem + ".dbf")), encoding="utf-8")  # fmt: skip
    muni = [
        (sr.record.as_dict()["N03_004"], shape(sr.shape.__geo_interface__))
        for sr in sf.iterShapeRecords()
    ]
    n03_names = {m[0] for m in muni}
    tree = STRtree([g for _, g in muni])
    tables = {
        t: pq.read_table(ROOT / "data/parquet" / f"{t}.parquet").to_pydict() for t in cols["counts"]
    }
    pos = {t: 0 for t in tables}
    kinds = {"POLYGON": "flood_area", "POINT": "flood_point"}
    inside = Counter()
    not_in_n03 = Counter()
    mismatched = Counter()
    total = 0
    for key in sorted(k for k in manifest["files"] if k[:4].isdigit()):
        data = (run / key).read_bytes()
        assert hashlib.sha256(data).hexdigest() == manifest["files"][key]["sha256"], key
        z = zipfile.ZipFile(io.BytesIO(data), metadata_encoding="cp932")
        names = [n for n in z.namelist() if not n.endswith("/")]
        for stem in sorted({n[:-4] for n in names if n.lower().endswith(".shp")}):
            enc = (
                z.read(stem + ".cpg").decode("ascii").strip().lower()
                if stem + ".cpg" in names
                else "cp932"
            )
            head, recs = read_dbf(z.read(stem + ".dbf"), enc)
            shapes = read_shapes(z.read(stem + ".shp"))
            assert len(shapes) == len(recs), stem
            kind = shapes[0][0]
            assert all(s[0] == kind for s in shapes)
            t, d = kinds[kind], tables[kinds[kind]]
            for i, (rec, (_, xy)) in enumerate(zip(recs, shapes, strict=True)):
                j = pos[t]
                pos[t] += 1
                assert d["year"][j] == int(key[:4]) and d["source_zip"][j] == key, (key, j)
                assert d["layer"][j] == stem.rsplit("/", 1)[-1] and d["row"][j] == i + 1, (
                    key,
                    stem,
                    j,
                )
                row = dict(zip(head, rec, strict=True))
                for c in tfr.ATTRIBUTES:
                    v = row.get(c)
                    if c in tfr.STRING_COLUMNS and isinstance(v, (int, float)):
                        v = str(int(v))
                    assert d[c][j] == v, (key, stem, i, c, d[c][j], v)
                g = shapely.from_wkb(d["geometry"][j])
                lon, lat = to_ll.transform(xy[:, 0], xy[:, 1])
                want = np.column_stack([lon, lat])
                order = np.lexsort((want[:, 1], want[:, 0]))
                want = want[order]
                have = vertices(g)
                assert have.shape == want.shape and np.array_equal(have, want), (key, stem, i)
                back = np.column_stack(to_plane.transform(have[:, 0], have[:, 1]))
                src = xy[order]
                assert np.abs(back - src).max() < 1e-6, (key, stem, i)
                p = g if kind == "POINT" else g.representative_point()
                hit = [muni[x][0] for x in tree.query(p) if muni[x][1].covers(p)]
                name = (d["munic"][j] or "").strip()
                if not name:
                    inside["no munic"] += 1
                elif name not in n03_names:
                    not_in_n03[name] += 1
                    inside["name not in N03"] += 1
                elif name in hit:
                    inside["in the named municipality"] += 1
                else:
                    mismatched[(key, name, tuple(hit))] += 1
                    inside["elsewhere"] += 1
                total += 1
        print(key, "ok", flush=True)
    for t, n in cols["counts"].items():
        assert pos[t] == n == len(tables[t]["year"]), t
    check = {"counts": dict(inside), "not_in_n03": dict(not_in_n03),
             "elsewhere": [list(map(str, k)) for k in mismatched], "rows": total}  # fmt: skip
    (ROOT / "data" / "docs" / "municipality_check.json").write_text(
        json.dumps(check, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(json.dumps(check["counts"], ensure_ascii=False), "not in N03:", dict(not_in_n03))
    named = inside["in the named municipality"] + inside["elsewhere"]
    assert inside["in the named municipality"] / named >= 0.98, (
        "too many records outside their municipality"
    )
    print(f"OK: {total} rows in {len(cols['counts'])} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
