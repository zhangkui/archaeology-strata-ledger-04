"""按发掘日期回放：用只追加修订流重建历史版本。"""
from datetime import datetime, timezone

from app.services.layers import merge_layers, replay_as_of

from conftest import make_layer, make_trench


async def test_replay_reconstructs_layer_state_at_date(conn):
    t = await make_trench(conn)
    l1 = await make_layer(conn, t, "L1")

    # 修订流：先建后改
    await conn.execute("UPDATE layers SET soil_color='灰褐' WHERE id=$1", l1)
    await conn.execute("UPDATE layers SET soil_color='黄褐', soil_texture='粉砂' WHERE id=$1", l1)

    # 在两次修订之间取一个时刻：Postgres now() 在事务内可能相同，改用 revised_at 边界构造
    rows = await conn.fetch(
        "SELECT field, revised_at FROM layer_revisions "
        "WHERE layer_id=$1 AND field='soil_color' ORDER BY revised_at, id", l1
    )
    assert len(rows) == 2
    after_first = rows[0]["revised_at"]
    after_second = rows[1]["revised_at"]

    snap1 = await replay_as_of(conn, t, after_first)
    state1 = next(x for x in snap1["layers"] if x["id"] == str(l1))
    assert state1["soil_color"] == "灰褐"
    assert state1.get("soil_texture") is None

    snap2 = await replay_as_of(conn, t, after_second)
    state2 = next(x for x in snap2["layers"] if x["id"] == str(l1))
    assert state2["soil_color"] == "黄褐"
    assert state2["soil_texture"] == "粉砂"


async def test_replay_excludes_future_layers_and_finds(conn):
    t = await make_trench(conn)
    early = await make_layer(conn, t, "EARLY")

    # 在早期层位建立后取一个「当前时刻」，再稍等建立晚期层位
    await conn.execute("SELECT pg_sleep(0.02)")
    as_of = await conn.fetchval("SELECT now()")
    await conn.execute("SELECT pg_sleep(0.02)")
    late = await make_layer(conn, t, "LATE")

    snap = await replay_as_of(conn, t, as_of)
    codes = {x.get("code") for x in snap["layers"]}
    assert "EARLY" in codes
    assert "LATE" not in codes

    # finds 按出土日期过滤：未来日期的出土物不在回放结果内
    await conn.execute(
        "INSERT INTO finds (layer_id, code, category, found_on) "
        "VALUES ($1,'F-now','陶片', now()::date)", early
    )
    await conn.execute(
        "INSERT INTO finds (layer_id, code, category, found_on) "
        "VALUES ($1,'F-future','陶片', now()::date + 10)", early
    )
    snap2 = await replay_as_of(conn, t, as_of)
    codes_f = {x["code"] for x in snap2["finds"]}
    assert "F-future" not in codes_f
    # F-now 的出土日期 <= as_of，会出现
    assert "F-now" in codes_f


async def test_replay_includes_merge_as_status_change(conn):
    t = await make_trench(conn)
    src = await make_layer(conn, t, "SRC")
    tgt = await make_layer(conn, t, "TGT")
    await merge_layers(conn, src, tgt, reason="r")

    snap = await replay_as_of(conn, t, datetime.now(timezone.utc))
    src_state = next(x for x in snap["layers"] if x["id"] == str(src))
    assert src_state["status"] == "merged"
    assert src_state["merged_into_id"] == str(tgt)
    # 合并审计事件出现在时间线
    types = {e["event_type"] for e in snap["audit_events"]}
    assert "layer.merged" in types
