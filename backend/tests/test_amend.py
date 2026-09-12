"""层位字段修订：动态 UPDATE 绑定正确、原始值不动、修订留痕。"""
import pytest

from app.errors import BusinessError
from app.services.layers import amend_layer

from conftest import make_layer, make_trench


async def test_amend_single_field_binds_correctly(conn):
    """回归：动态 SQL 占位符曾有 off-by-one，单字段修订直接 400。"""
    t = await make_trench(conn)
    l = await make_layer(conn, t, "L1")
    out = await amend_layer(conn, l, {"description": "新描述"})
    assert out["description"] == "新描述"


async def test_amend_multiple_fields(conn):
    t = await make_trench(conn)
    l = await make_layer(conn, t, "L1")
    out = await amend_layer(conn, l, {
        "soil_color": "红褐", "depth_top_cm": 12, "depth_bottom_cm": 30})
    assert out["soil_color"] == "红褐"
    assert float(out["depth_top_cm"]) == 12
    assert float(out["depth_bottom_cm"]) == 30
    n = await conn.fetchval(
        "SELECT count(*) FROM layer_revisions WHERE layer_id=$1 AND kind='amend'", l)
    assert n == 3


async def test_amend_keeps_original_observation(conn):
    t = await make_trench(conn)
    l = await make_layer(conn, t, "L1")
    await amend_layer(conn, l, {"soil_color": "黑"})
    val = await conn.fetchval(
        "SELECT original_observation->>'note' FROM layers WHERE id=$1", l)
    assert val == "原始"


async def test_amend_empty_patch_rejected(conn):
    t = await make_trench(conn)
    l = await make_layer(conn, t, "L1")
    with pytest.raises(BusinessError):
        await amend_layer(conn, l, {})


async def test_reopen_merged_layer_rejected(conn):
    t = await make_trench(conn)
    src = await make_layer(conn, t, "S")
    tgt = await make_layer(conn, t, "G")
    await conn.execute(
        "UPDATE layers SET status='merged', merged_into_id=$2 WHERE id=$1", src, tgt)
    with pytest.raises(BusinessError, match="不能重新开放"):
        await amend_layer(conn, src, {"reopen": True})
