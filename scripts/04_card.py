"""Write data/README.md (the dataset card), data/LICENSE and data/provenance.yaml.

uv run python scripts/04_card.py
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

import pyarrow.parquet as pq
import tfr

ROOT = Path(__file__).parents[1]
REPO = "tokyo-flood-record-jp"
CREDIT = f"出典：東京都「水害リスク情報システム 浸水実績図データ」（{tfr.PAGE_URL}）を加工して作成"

CARD = """---
license: cc-by-4.0
license_name: cc-by-4.0
license_link: https://creativecommons.org/licenses/by/4.0/legalcode.ja
language:
- ja
tags:
- japan
- tokyo
- flood
- disaster
- geospatial
size_categories:
- 1K<n<10K
pretty_name: Flood records of Tokyo (浸水実績図, 1974 to 2019)
---

# {repo}

The flood records (浸水実績図) of Tokyo, {year0} to {year1}: {n_area:,} flooded areas as polygons and {n_point} as
points, with the damage counts, the river, the municipality and the rainfall of the nearest gauge, from the
Flood Risk Information System (水害リスク情報システム) of the Tokyo Metropolitan Government. As GeoParquet.

## Source

- Page: <{page}> (東京都 水害リスク情報システム, 水害記録資料集, 浸水実績図データ), which states the licence
  「クリエイティブ・コモンズ・ライセンス 表示4.0国際」.
- What the page says the records are: the floods found by the flood statistics survey (水害統計調査, a
  general statistical survey of the Ministry of Land, Infrastructure, Transport and Tourism, carried out
  with the prefecture and the municipalities), where the flooded area is 0.1 ha or more or 10 or more
  buildings were hit in one stretch, put together by the Tokyo Metropolitan Government.
- Files: the page, the listing that the page calls to fill its download table (`listing.json`), the page's
  list of the attributes (`attributes.pdf`) and the {n_zip} zips of the listing (one Shapefile zip per
  year), as served, unchanged under `raw/{run}/` with their sha256 in `MANIFEST.json`. Fetched {fetched}.

The page's notice says that the map shows the approximate places where floods were recorded, that it can
differ from the real extent, that it does not reflect every flooded place and that it does not tell
whether an individual plot flooded or how deep.

## Files

| File | Rows | Geometry |
|---|---|---|
| `parquet/flood_area.parquet` | {n_area:,} | Polygon or MultiPolygon |
| `parquet/flood_point.parquet` | {n_point} | Point |

`parquet/columns.json` lists, for every layer of every zip, its type, its rows and its fields. The
source zips are in `raw/{run}/`. Years in the dataset: {n_years} ({year0} to {year1}).

{year_table}

Years with no zip in the listing: {missing}. The page's text says the records run to 令和4年 (2022); the
listing has no file after 2019, and for 2020 it marks the file as not enabled.

## Columns

Both tables have the same columns. Added to the source's attributes: `year` (of the zip), `source_zip`,
`layer` (the Shapefile's name), `row` (its position in the layer) and `geometry` (WKB, longitude and
latitude of JGD2000, EPSG:4612). Then the attributes, with the names and the meaning of the page's list
(`attributes.pdf`):

`id`, `area_no` (水害区域番号), `dis_name` (災害名称), `dis_date_s` and `dis_date_e` (災害の開始と終了の日),
`river` (河川名), `munic` (区市町村), `district` (町丁目), `area` (浸水面積, ha), `utf_bldg`, `utf_house`
(床下の棟数と世帯数), `otf_bldg`, `otf_house` (床上), `pd_bldg`, `pd_house` (半壊), `cd_bldg`, `cd_house`
(全壊), `tot_bldg`, `tot_house` (合計), `reason` (原因), `nro_name`, `nro_tot`, `nro_60min`, `nro_flag`
(the nearest rain gauge of the municipality: its name, the total rain, the 60 minute maximum, and a flag),
`mro_name`, `mro_tot`, `mro_60min` (the gauge with the greatest 60 minute rain of the event).

The layers of {n_wide} years write the district in `district0` to `district4` (up to five parts) instead of
`district`; those columns are as the source has them and `district` is then null, and the other way
round. A column that a layer does not have is null. Text is text; the counts of buildings and
households and the rain figures stay text, because the source writes some with parentheses (for
example `6(0)` and `(213)`; the attribute list says text is used for the counts because of the parentheses, and
it does not explain them). `id`, `area_no` and `nro_flag` are integers, the two dates are dates, `area` is a double.

## What was changed

- Nothing in the attributes, except: blank text and the source's null markers are null (see known
  issues), numbers that the source stores as numbers in a text column are written as their digits, and the
  Shapefiles' coordinates were projected to longitude and latitude. Added the columns above.
- Every polygon layer is in `flood_area` and every point layer in `flood_point`; nothing was merged,
  de-duplicated, dropped or corrected.
- The Parquet was checked against the zips with a second reader (the `.dbf` and the `.shp` parsed by
  hand), every row, every column and every vertex.

## Coordinates

The Shapefiles carry a `.prj`: JGD2000 / Japan Plane Rectangular CS IX (EPSG:2451), in metres. They were
projected to JGD2000 longitude and latitude (EPSG:4612), and the geometry columns say so. The
Shapefiles of the islands (Ōshima, Kōzushima, Ogasawara) are in the same system, and all of their records lie in their island municipality. As a check, {in_named:,} of
the {named:,} records whose `munic` is a municipality of N03 (国土数値情報 行政区域, 2026-01-01) lie in that municipality
(point, or a representative point of the polygon), and {elsewhere} do not: {neighbour} lie in another municipality (a polygon that crosses a border or a point near it)
and {nowhere} in none of N03's polygons; this was not examined one by one. N03 was used for
this check only and is not part of the dataset.

## Known issues

- `id` is not a key: in {dup_layers} of the {n_layers} layers an `id` occurs more than once (the page's list calls it unique per Shapefile).
- `area_no` is null in {null_area_no:,} rows: the source has a run of asterisks there, a number that did not fit.
  `nro_flag` is null in {null_flag} rows for the same reason. `dis_date_s` and `dis_date_e` are null in {null_dates} polygons
  that the source marks `00000000` (no date).
- `munic` is the name as written at the time and sometimes wrong: {not_in_n03_text}.
  `田無市`, `保谷市`, `秋川市`, `五日市町` and `羽村町` are names of municipalities that have since been merged or renamed, `太田区` and `世田ヶ谷区` look like misspellings of 大田区 and 世田谷区.
- `river` is not always a river: it holds values such as `普通河川` and `河川海岸以外` and, in 1987 and
  1988, the string `99`. `reason` and `dis_name` are free text and written in many ways
  (`内水・溢水`, `溢水内水`, `台風19 号`).
- Some zips hold two layers: a polygon layer and a point layer named with `ポイント` ({n_point_layers} years), and 1979 has two
  polygon layers (`1979_S54_` and `1979_S54_2_`, different events). The source does not say what the point
  layers are; they are kept as they are, in `flood_point`.
- The records are the source's selection and reflect the survey and the notice quoted above, not all floods. They are not
  a measure of flood risk of a place.

## Licence

The page states Creative Commons Attribution 4.0 International for the data. This dataset is offered
under CC BY 4.0 and the credit is to the Tokyo Metropolitan Government:

> {credit}
"""


def main() -> int:
    run = sorted((ROOT / "data" / "raw").glob("*/MANIFEST.json"))[-1].parent
    m = json.loads((run / "MANIFEST.json").read_text())
    cols = json.loads((ROOT / "data/parquet/columns.json").read_text())
    assert cols["run"] == run.name
    a = pq.read_table(ROOT / "data/parquet/flood_area.parquet").to_pydict()
    p = pq.read_table(ROOT / "data/parquet/flood_point.parquet").to_pydict()
    check = json.loads((ROOT / "data/docs/municipality_check.json").read_text())
    zips = [k for k in m["files"] if k[:4].isdigit()]
    per = defaultdict(lambda: [0, 0])
    for y in a["year"]:
        per[y][0] += 1
    for y in p["year"]:
        per[y][1] += 1
    year_rows = "\n".join(
        f"| {y} | `{m['years_in_listing'][str(y)]['filename']}` | {n[0]:,} | {n[1]} |"
        for y, n in sorted(per.items())
    )
    year_table = "| Year | Zip as served | Polygons | Points |\n|---|---|---|---|\n" + year_rows
    missing = ", ".join(y for y, v in m["years_in_listing"].items() if not v["path"])
    layers = cols["layers"]
    ids = defaultdict(list)
    for t, d in (("a", a), ("p", p)):
        for z, layer, i in zip(d["source_zip"], d["layer"], d["id"], strict=True):
            ids[(t, z, layer)].append(i)
    dup_layers = sum(len(v) != len(set(v)) for v in ids.values())
    wide = sorted({y for y, d0 in zip(a["year"], a["district0"], strict=True) if d0})
    nin = check["not_in_n03"]
    not_in_n03_text = ", ".join(
        f"`{k}` ({v})" for k, v in sorted(nin.items(), key=lambda kv: -kv[1])
    )
    c = check["counts"]
    first = "in the named municipality"
    point_years = {x["year"] for x in layers if x["type"] == "POINT"}
    card = CARD.format(
        repo=REPO, page=tfr.PAGE_URL, run=run.name, fetched=run.name, credit=CREDIT,
        n_area=cols["counts"]["flood_area"], n_point=cols["counts"]["flood_point"],
        n_zip=len(zips), year0=min(per), year1=max(per), n_years=len(per),
        year_table=year_table, missing=missing, n_wide=len(wide),
        in_named=c[first], named=c[first] + c["elsewhere"], elsewhere=c["elsewhere"],
        nowhere=sum(e[2] == "()" for e in check["elsewhere"]),
        neighbour=sum(e[2] != "()" for e in check["elsewhere"]),
        dup_layers=dup_layers, n_layers=len(ids),
        null_area_no=sum(x is None for x in a["area_no"]) + sum(x is None for x in p["area_no"]),
        null_flag=sum(x is None for x in a["nro_flag"]) + sum(x is None for x in p["nro_flag"]),
        null_dates=sum(x is None for x in a["dis_date_s"]) + sum(x is None for x in p["dis_date_s"]),
        not_in_n03_text=not_in_n03_text, n_point_layers=len(point_years),
    )  # fmt: skip
    data = ROOT / "data"
    (data / "README.md").write_text(card, encoding="utf-8")
    (data / "LICENSE").write_text(
        "CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/legalcode)\n\n"
        "The records are the 浸水実績図データ of the Flood Risk Information System of the Tokyo Metropolitan\n"
        f"Government, published under Creative Commons Attribution 4.0 ({tfr.PAGE_URL}),\n"
        "processed as described in README.md.\n"
        f"Credit: {CREDIT}\n",
        encoding="utf-8",
    )
    rows = sum(cols["counts"].values())
    (data / "provenance.yaml").write_text(
        f"source: 東京都 水害リスク情報システム 浸水実績図データ\nurl: {tfr.PAGE_URL}\nlicense: CC BY 4.0\n"
        f"run: {run.name}\nretrieved: {run.name}\nrows: {rows}\n",
        encoding="utf-8",
    )
    print("wrote data/README.md, LICENSE, provenance.yaml")
    return 0


if __name__ == "__main__":
    sys.exit(main())
