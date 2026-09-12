"""删除层位前的证据链检查。"""
import pytest

from app.services.layers import delete_layer
from app.errors import BusinessError

from conftest import make_find, make_layer, make_trench


async def _blocked(conn, layer_id):
    """模拟服务层删除前检查，返回阻断原因。"""
    blockers = {}
    n = await conn.fetchval("SELECT count(*) FROM layer_parents WHERE parent_id=$1", layer_id)
    if n:
        blockers["child_layers"] = n
    for table, col in (("finds", "layer_id"), ("photos", "layer_id"), ("samples", "layer_id")):
        n = await conn.fetchval(f"SELECT count(*) FROM {table} WHERE {col}=$1", layer_id)
        if n:
            blockers[table] = n
    return blockers


async def test_delete_blocked_by_child(conn):
    t = await make_trench(conn)
    parent = await make_layer(conn, t, "P")
    await make_layer(conn, t, "C", parent_ids=[parent])
    assert (await _blocked(conn, parent)).get("child_layers") == 1
    # 父层确实还在
    assert await conn.fetchval("SELECT count(*) FROM layers WHERE id=$1", parent) == 1


async def test_delete_blocked_by_find(conn):
    t = await make_trench(conn)
    l = await make_layer(conn, t)
    await make_find(conn, l)
    assert (await _blocked(conn, l)).get("finds") == 1


async def test_delete_blocked_by_sample(conn):
    t = await make_trench(conn)
    l = await make_layer(conn, t)
    await conn.execute(
        "INSERT INTO samples (layer_id, code, material, collected_on) "
        "VALUES ($1,'SMP','炭样','2026-09-02')", l
    )
    assert (await _blocked(conn, l)).get("samples") == 1


async def test_delete_blocked_by_photo(conn):
    t = await make_trench(conn)
    l = await make_layer(conn, t)
    await conn.execute(
        "INSERT INTO photos (layer_id, object_key, bucket, filename) "
        "VALUES ($1,'k/x.jpg','b','x.jpg')", l
    )
    assert (await _blocked(conn, l)).get("photos") == 1


async def test_service_delete_blocked_by_find(conn):
    t = await make_trench(conn)
    l = await make_layer(conn, t)
    await make_find(conn, l)
    with pytest.raises(BusinessError, match="证据引用"):
        await delete_layer(conn, l)
    assert await conn.fetchval("SELECT count(*) FROM layers WHERE id=$1", l) == 1


async def test_service_delete_blocked_by_child(conn):
    t = await make_trench(conn)
    parent = await make_layer(conn, t, "P")
    await make_layer(conn, t, "C", parent_ids=[parent])
    with pytest.raises(BusinessError, match="子层位"):
        await delete_layer(conn, parent)
    assert await conn.fetchval("SELECT count(*) FROM layers WHERE id=$1", parent) == 1


async def test_clean_layer_can_delete_and_cascades_links(conn):
    t = await make_trench(conn)
    root = await make_layer(conn, t, "root")
    leaf = await make_layer(conn, t, "leaf", parent_ids=[root])
    # leaf 无任何证据/子层，服务层删除成功；其父子边与修订随层位一并清理
    await delete_layer(conn, leaf)
    assert await conn.fetchval("SELECT count(*) FROM layer_parents WHERE child_id=$1", leaf) == 0
    assert await conn.fetchval("SELECT count(*) FROM layer_revisions WHERE layer_id=$1", leaf) == 0
    assert await conn.fetchval("SELECT count(*) FROM layers WHERE id=$1", root) == 1
    assert await conn.fetchval(
        "SELECT count(*) FROM audit_events WHERE event_type='layer.deleted'"
    ) == 1
