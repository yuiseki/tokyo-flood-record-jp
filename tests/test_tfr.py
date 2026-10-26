import io
import zipfile

import pytest
import shapefile
import tfr


def test_zip_url_quotes_the_path():
    assert tfr.zip_url(1974, "1974.zip") == f"{tfr.SITE}/data/shinsuijisseki/1974/1974.zip"


def test_clean_blank_text_is_null_and_numbers_in_text_columns_are_digits():
    assert tfr.clean("river", "  ") is None
    assert tfr.clean("river", "神田川  ") == "神田川"
    assert tfr.clean("utf_bldg", 12) == "12"
    assert tfr.clean("utf_bldg", "6(0)") == "6(0)"
    assert tfr.clean("area_no", None) is None
    assert tfr.clean("area", 2.59) == 2.59
    with pytest.raises(ValueError):
        tfr.clean("utf_bldg", 1.5)


def _zip_with(layers: dict[str, tuple[int, list]]) -> bytes:
    """A zip with one Shapefile per name; each is (shape type, [(coords, id)])."""
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        for name, (kind, items) in layers.items():
            shp, shx, dbf = io.BytesIO(), io.BytesIO(), io.BytesIO()
            w = shapefile.Writer(shp=shp, shx=shx, dbf=dbf, shapeType=kind, encoding="utf-8")
            w.field("id", "N", 5, 0)
            w.field("river", "C", 20)
            for coords, i in items:
                if kind == shapefile.POINT:
                    w.point(*coords)
                else:
                    w.poly([coords])
                w.record(i, "神田川")
            w.close()
            z.writestr(f"{name}.shp", shp.getvalue())
            z.writestr(f"{name}.shx", shx.getvalue())
            z.writestr(f"{name}.dbf", dbf.getvalue())
            z.writestr(f"{name}.cpg", "UTF-8")
    return out.getvalue()


def test_layers_reads_every_shapefile_of_a_zip_in_name_order():
    sq = [(0, 0), (0, 1), (1, 1), (1, 0), (0, 0)]
    data = _zip_with(
        {"b_ポイント": (shapefile.POINT, [((5, 6), 1)]), "a": (shapefile.POLYGON, [(sq, 7)])}
    )
    got = tfr.layers(data)
    assert [g[0] for g in got] == ["a", "b_ポイント"]
    assert [g[1] for g in got] == ["POLYGON", "POINT"]
    assert got[0][2] == ["id", "river"] and got[0][3] == [[7, "神田川"]]


def test_layers_refuses_an_unknown_field():
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        shp, shx, dbf = io.BytesIO(), io.BytesIO(), io.BytesIO()
        w = shapefile.Writer(shp=shp, shx=shx, dbf=dbf, shapeType=shapefile.POINT)
        w.field("surprise", "C", 5)
        w.point(1, 2)
        w.record("x")
        w.close()
        z.writestr("a.shp", shp.getvalue())
        z.writestr("a.shx", shx.getvalue())
        z.writestr("a.dbf", dbf.getvalue())
    with pytest.raises(ValueError):
        tfr.layers(out.getvalue())


def test_attributes_cover_every_typed_column_once():
    assert len(tfr.ATTRIBUTES) == len(set(tfr.ATTRIBUTES)) == 32
