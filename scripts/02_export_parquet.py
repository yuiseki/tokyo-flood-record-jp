"""Write the 浸水実績図 of Tokyo (1974 to 2019) as two GeoParquet files: flood_area and flood_point.

Every layer of every zip is read with pyshp. The polygon layers go to flood_area and the point layers
to flood_point, one row per record, in the order of the year, the layer's name and the record. Added
to the attributes of the source (the 27 to 31 fields, unioned; a field a layer does not have is null):
`year` (of the zip), `source_zip`, `layer` (the Shapefile's name), `row` (its position in the layer)
and `geometry` (WKB, JGD2000 longitude and latitude, projected from the source's JGD2000 / plane
rectangular CS IX). Text stays text (blank is null; the counts of buildings and households stay text
because the source writes some with parentheses), `id`, `area_no` and `nro_flag` are integers, the
dates are dates, `area` (ha) is a double.

    uv run python scripts/02_export_parquet.py [--version 2026-10-26]
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import shapely
import tfr
from pyproj import Transformer
from shapely.geometry import shape

ROOT = Path(__file__).parents[1]
GEO = {"POLYGON": "flood_area", "POINT": "flood_point"}
GEOMETRY_TYPES = {"flood_area": ["Polygon", "MultiPolygon"], "flood_point": ["Point"]}


def arrow_type(c: str) -> pa.DataType:
    if c in tfr.INT_COLUMNS:
        return pa.int32()
    if c in tfr.DATE_COLUMNS:
        return pa.date32()
    if c in tfr.FLOAT_COLUMNS:
        return pa.float64()
    return pa.string()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default=None)
    args = ap.parse_args()
    runs = sorted((ROOT / "data" / "raw").glob("*/MANIFEST.json"))
    raw = runs[-1].parent if args.version is None else ROOT / "data" / "raw" / args.version
    manifest = json.loads((raw / "MANIFEST.json").read_text())
    to_ll = Transformer.from_crs(tfr.PLANE_EPSG, tfr.GEOGRAPHIC_EPSG, always_xy=True)
    rows = {t: [] for t in GEO.values()}
    per_layer = []
    for key in sorted(k for k in manifest["files"] if k[:4].isdigit()):
        year = int(key[:4])
        for name, kind, head, recs, shapes in tfr.layers((raw / key).read_bytes()):
            table = GEO[kind]
            for i, (rec, sh) in enumerate(zip(recs, shapes, strict=True), 1):
                row = {"year": year, "source_zip": key, "layer": name, "row": i}
                d = dict(zip(head, rec, strict=True))
                for c in tfr.ATTRIBUTES:
                    row[c] = tfr.clean(c, d.get(c))
                g = shape(sh.__geo_interface__)
                row["geometry"] = shapely.transform(
                    g, lambda xy: np.column_stack(to_ll.transform(xy[:, 0], xy[:, 1]))
                ).wkb
                lon0, lat0, lon1, lat1 = shapely.from_wkb(row["geometry"]).bounds
                b = tfr.BBOX
                if not (b[0] <= lon0 and lon1 <= b[2] and b[1] <= lat0 and lat1 <= b[3]):
                    raise ValueError(f"{key} {name} row {i}: outside Tokyo")
                rows[table].append(row)
            per_layer.append({"year": year, "zip": key, "layer": name, "type": kind,
                              "rows": len(recs), "fields": head})  # fmt: skip
    out = ROOT / "data" / "parquet"
    out.mkdir(parents=True, exist_ok=True)
    schema_cols = [("year", pa.int32()), ("source_zip", pa.string()), ("layer", pa.string()),
                   ("row", pa.int32())] + [(c, arrow_type(c)) for c in tfr.ATTRIBUTES]  # fmt: skip
    counts, geom_types = {}, {}
    for table, rs in rows.items():
        cols = {n: pa.array([r[n] for r in rs], type=t) for n, t in schema_cols}
        cols["geometry"] = pa.array([r["geometry"] for r in rs], type=pa.binary())
        geo = {"version": "1.1.0", "primary_column": "geometry", "columns": {"geometry": {
            "encoding": "WKB", "geometry_types": GEOMETRY_TYPES[table],
            "crs": {"$schema": "https://proj.org/schemas/v0.7/projjson.schema.json", "type": "GeographicCRS",
                    "name": "JGD2000", "id": {"authority": "EPSG", "code": tfr.GEOGRAPHIC_EPSG}}}}}  # fmt: skip
        t = pa.table(cols).replace_schema_metadata({b"geo": json.dumps(geo).encode()})
        pq.write_table(t, out / f"{table}.parquet", compression="zstd")
        counts[table] = t.num_rows
        geom_types[table] = sorted(
            {shapely.from_wkb(g).geom_type for g in cols["geometry"].to_pylist()}
        )
        print(table, t.num_rows, geom_types[table])
    (out / "columns.json").write_text(
        json.dumps({"run": raw.name, "counts": counts, "geometry_types": geom_types, "layers": per_layer,
                    "attributes": list(tfr.ATTRIBUTES)}, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8")  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
