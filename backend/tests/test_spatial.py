"""空间规则：坐标必须落在探方边界内（ST_Within 触发器）。"""
import json

import pytest

from conftest import POINT_INSIDE, POINT_OUTSIDE, make_find, make_layer, make_trench


async def test_point_inside_trench_accepted(conn):
    t = await make_trench(conn)
    l = await make_layer(conn, t)
    f = await make_find(conn, l, "Fin", POINT_INSIDE)
    pos = await conn.fetchval("SELECT ST_AsGeoJSON(position) FROM finds WHERE id=$1", f)
    assert json.loads(pos)["coordinates"] == [116.4015, 39.9015]


async def test_point_outside_trench_rejected(conn):
    t = await make_trench(conn)
    l = await make_layer(conn, t)
    with pytest.raises(Exception) as ei:
        await make_find(conn, l, "Fout", POINT_OUTSIDE)
    assert "探方边界" in str(ei.value)


async def test_find_without_point_accepted(conn):
    t = await make_trench(conn, geom=None)
    l = await make_layer(conn, t)
    f = await conn.fetchval(
        "INSERT INTO finds (layer_id, code, category, found_on) "
        "VALUES ($1,'Fnopos','石器','2026-09-02') RETURNING id", l
    )
    assert f is not None


async def test_boundary_on_edge_within_polygon(conn):
    """边界点按 ST_Within 严格判断（边界不算 within），应被拒，证明用的是真正的空间谓词。"""
    t = await make_trench(conn)
    l = await make_layer(conn, t)
    edge = '{"type":"Point","coordinates":[116.4010,39.9010]}'
    with pytest.raises(Exception):
        await make_find(conn, l, "Fedge", edge)


async def test_spatial_distance_geography(conn):
    t = await make_trench(conn)
    l = await make_layer(conn, t)
    # 经度相差 0.0008°（约 68m @ lat39.9）
    a = await make_find(conn, l, "A", '{"type":"Point","coordinates":[116.4011,39.9011]}')
    b = await make_find(conn, l, "B", '{"type":"Point","coordinates":[116.4019,39.9011]}')
    meters = await conn.fetchval(
        "SELECT ST_Distance(x.position::geography, y.position::geography) "
        "FROM finds x, finds y WHERE x.id=$1 AND y.id=$2", a, b
    )
    assert 60 < float(meters) < 80
