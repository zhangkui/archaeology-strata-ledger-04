"""开放层位状态机：出土物只能归属 open 层位。"""
import pytest

from conftest import make_find, make_layer, make_trench


async def test_find_on_open_layer_ok(conn):
    t = await make_trench(conn)
    l = await make_layer(conn, t)
    f = await make_find(conn, l)
    assert f is not None


async def test_find_on_closed_layer_rejected(conn):
    t = await make_trench(conn)
    l = await make_layer(conn, t, status="closed")
    with pytest.raises(Exception) as ei:
        await make_find(conn, l, "F-closed")
    assert "开放" in str(ei.value)


async def test_find_on_merged_layer_rejected(conn):
    t = await make_trench(conn)
    target = await make_layer(conn, t, "T")
    src = await make_layer(conn, t, "S", status="merged")
    await conn.execute(
        "UPDATE layers SET merged_into_id=$2 WHERE id=$1", src, target
    )
    with pytest.raises(Exception) as ei:
        await make_find(conn, src, "F-merged")
    assert "开放" in str(ei.value)


async def test_moving_find_to_closed_layer_rejected(conn):
    t = await make_trench(conn)
    open_l = await make_layer(conn, t, "openL")
    closed_l = await make_layer(conn, t, "closedL", status="closed")
    f = await make_find(conn, open_l)
    with pytest.raises(Exception) as ei:
        await conn.execute("UPDATE finds SET layer_id=$2 WHERE id=$1", f, closed_l)
    assert "开放" in str(ei.value)


async def test_close_then_reopen_allows_find(conn):
    t = await make_trench(conn)
    l = await make_layer(conn, t)
    await conn.execute("UPDATE layers SET status='closed', closed_on='2026-09-05' WHERE id=$1", l)
    with pytest.raises(Exception):
        await make_find(conn, l, "F1")
    await conn.execute("UPDATE layers SET status='open', closed_on=NULL WHERE id=$1", l)
    f = await make_find(conn, l, "F2")
    assert await conn.fetchval("SELECT status FROM layers WHERE id=$1", l) == "open"
    assert f is not None
