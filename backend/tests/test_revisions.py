"""修订记录：只追加、不可覆盖原始观察值、逐字段留痕。"""
import json

import pytest

from conftest import make_layer, make_trench


async def test_create_emits_revision_snapshot(conn):
    t = await make_trench(conn)
    l = await make_layer(conn, t, "L1")
    rows = await conn.fetch(
        "SELECT kind, new_value FROM layer_revisions WHERE layer_id=$1", l
    )
    assert len(rows) == 1
    assert rows[0]["kind"] == "create"
    assert rows[0]["new_value"]["code"] == "L1"


async def test_amend_writes_field_level_revision(conn):
    t = await make_trench(conn)
    l = await make_layer(conn, t, "L1")
    await conn.execute("UPDATE layers SET soil_color='红褐色' WHERE id=$1", l)
    rows = await conn.fetch(
        "SELECT kind, field, old_value, new_value FROM layer_revisions "
        "WHERE layer_id=$1 AND kind='amend'", l
    )
    assert len(rows) >= 1
    soil = [r for r in rows if r["field"] == "soil_color"]
    assert soil and soil[0]["new_value"] == "红褐色"


async def test_original_observation_immutable(conn):
    t = await make_trench(conn)
    l = await make_layer(conn, t, "L1")
    with pytest.raises(Exception) as ei:
        await conn.execute(
            "UPDATE layers SET original_observation=$2::jsonb WHERE id=$1",
            l, json.dumps({"tampered": True}),
        )
    assert "原始观察" in str(ei.value)
    # 原值完好
    val = await conn.fetchval("SELECT original_observation->>'note' FROM layers WHERE id=$1", l)
    assert val == "原始"


async def test_revisions_table_is_append_only(conn):
    t = await make_trench(conn)
    l = await make_layer(conn, t, "L1")
    rev_id = await conn.fetchval("SELECT id FROM layer_revisions WHERE layer_id=$1", l)
    with pytest.raises(Exception):
        await conn.execute("UPDATE layer_revisions SET new_value='{}'::jsonb WHERE id=$1", rev_id)
    with pytest.raises(Exception):
        await conn.execute("DELETE FROM layer_revisions WHERE id=$1", rev_id)


async def test_each_actor_recorded_via_session_var(conn):
    t = await make_trench(conn)
    l = await make_layer(conn, t, "L1")
    # 会话级设置（false = 非事务局部），跨后续语句生效
    await conn.execute("SELECT set_config('app.actor','prof-wang', false)")
    await conn.execute("UPDATE layers SET soil_texture='黏土' WHERE id=$1", l)
    actor = await conn.fetchval(
        "SELECT actor FROM layer_revisions WHERE layer_id=$1 AND field='soil_texture'", l
    )
    assert actor == "prof-wang"
