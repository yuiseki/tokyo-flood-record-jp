"""Shared helpers: the 浸水実績図 (flood records) of the Tokyo Metropolitan Government Flood Risk Information System."""

import io
import urllib.parse
import zipfile

SITE = "https://www.suigai-risk.metro.tokyo.lg.jp"
PAGE_URL = f"{SITE}/shiryoshu/shinsui-chizudata/"
# the listing the page itself calls to fill its download table
LISTING_URL = f"{SITE}/api/tokyoflood/file/searchFloodRecordMap.py"
ATTR_PDF_URL = f"{PAGE_URL}pdf/" + urllib.parse.quote(
    "浸水実績地図データシェープファイル属性情報一覧（水害リスク情報システム）.pdf"
)
LICENSE_PHRASE = "クリエイティブ・コモンズ・ライセンス 表示4.0国際"
LICENSE_LINK = "https://creativecommons.org/licenses/by/4.0/deed.ja"


def zip_url(year: int, path: str) -> str:
    return f"{SITE}/data/shinsuijisseki/{year}/{urllib.parse.quote(path)}"


ENCODING_DEFAULT = "cp932"
# the Shapefiles are JGD2000 / Japan Plane Rectangular CS IX (their .prj says so); the export writes JGD2000 longitude and latitude
PLANE_EPSG = 2451
GEOGRAPHIC_EPSG = 4612
# Tokyo with a margin (lon min, lat min, lon max, lat max), the Izu and Ogasawara islands included
BBOX = (138.8, 26.5, 142.5, 35.95)
N03_URL = "https://nlftp.mlit.go.jp/ksj/gml/data/N03/N03-2026/N03-20260101_13_GML.zip"
N03_PAGE_URL = "https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-N03-2026.html"
STRING_COLUMNS = (
    "dis_name", "river", "munic", "district", "district0", "district1", "district2", "district3",
    "district4", "utf_bldg", "utf_house", "otf_bldg", "otf_house", "pd_bldg", "pd_house", "cd_bldg",
    "cd_house", "tot_bldg", "tot_house", "reason", "nro_name", "nro_tot", "nro_60min", "mro_name",
    "mro_tot", "mro_60min",
)  # fmt: skip
INT_COLUMNS = ("id", "area_no", "nro_flag")
DATE_COLUMNS = ("dis_date_s", "dis_date_e")
FLOAT_COLUMNS = ("area",)
# the columns of the tables, in this order; a column a layer does not have is null
ATTRIBUTES = (
    "id", "area_no", "dis_name", "dis_date_s", "dis_date_e", "river", "munic", "district", "district0",
    "district1", "district2", "district3", "district4", "area", "utf_bldg", "utf_house", "otf_bldg",
    "otf_house", "pd_bldg", "pd_house", "cd_bldg", "cd_house", "tot_bldg", "tot_house", "reason",
    "nro_name", "nro_tot", "nro_60min", "nro_flag", "mro_name", "mro_tot", "mro_60min",
)  # fmt: skip
assert set(ATTRIBUTES) == set(STRING_COLUMNS + INT_COLUMNS + DATE_COLUMNS + FLOAT_COLUMNS)


def layers(data: bytes):
    """The Shapefile layers of a zip: (layer name, shape type, field names, records, shapes), sorted by name.

    A zip holds one layer, or two (a polygon layer and a point layer ``..._ポイント_...``, or two polygon
    layers in 1979), some in a folder. Names are cp932; the .dbf is UTF-8 when a .cpg says so, else cp932.
    """
    import shapefile

    z = zipfile.ZipFile(io.BytesIO(data), metadata_encoding="cp932")
    names = [n for n in z.namelist() if not n.endswith("/")]
    out = []
    for stem in sorted({n[:-4] for n in names if n.lower().endswith(".shp")}):
        enc = ENCODING_DEFAULT
        if stem + ".cpg" in names:
            enc = z.read(stem + ".cpg").decode("ascii").strip().lower()
        sf = shapefile.Reader(
            shp=io.BytesIO(z.read(stem + ".shp")), shx=io.BytesIO(z.read(stem + ".shx")),
            dbf=io.BytesIO(z.read(stem + ".dbf")), encoding=enc)  # fmt: skip
        head = [f[0] for f in sf.fields[1:]]
        if len(set(head)) != len(head) or not set(head) <= set(ATTRIBUTES):
            raise ValueError(f"{stem}: unexpected fields {sorted(set(head) - set(ATTRIBUTES))}")
        recs = [list(r) for r in sf.records()]
        out.append((stem.rsplit("/", 1)[-1], sf.shapeTypeName, head, recs, sf.shapes()))
    return out


def clean(column: str, v):
    """One attribute value: blank text is null, a number in a text column is its digits."""
    if v is None:
        return None
    if column in STRING_COLUMNS:
        if isinstance(v, (int, float)):
            if isinstance(v, float) and v != int(v):
                raise ValueError(f"{column}: {v}")
            return str(int(v))
        v = v.rstrip(" \0")
        return v or None
    return v
