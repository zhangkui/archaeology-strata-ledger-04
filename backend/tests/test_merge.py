"""合并层位：证据迁移、DAG 改写、迁移关系、审计事件（服务层单事务）。"""
import pytest

from app.errors import BusinessError
from app.services.layers import merge_layers

from conftest import make_find, make_layer, make_trench


async def _photo(conn, layer_id, code="p.jpg"):
    return await conn.fetchval(
        "INSERT INTO photos (layer_id, object_key, bucket, filename) "
        "VALUES ($1,$2,'b',$2) RETURNING id", layer_id, code
    )


async def _sample(conn, layer_id, code="C1"):
    return await conn.fetchval(
        "INSERT INTO samples (layer_id, code, material, collected_on) "
        "VALUES ($1,$2,'炭样','2026-09-03') RETURNING id", layer_id, code
    )


async def test_merge_moves_evidence_and_audits(conn):
    t = await make_trench(conn)
    src = await make_layer(conn, t, "SRC")
    tgt = await make_layer(conn, t, "TGT")
    f = await make_find(conn, src, "F1")
    await _photo(conn, src)
    await _sample(conn, src)

    result = await merge_layers(conn, src, tgt, reason="同一堆积单位")

    assert result["migrated_finds"] == 1
    assert result["migrated_photos"] == 1
    assert result["migrated_samples"] == 1
    # 出土物已挂到目标层
    assert await conn.fetchval("SELECT layer_id FROM finds WHERE id=$1", f) == tgt
    # 源层位终态
    row = await conn.fetchrow("SELECT status, merged_into_id FROM layers WHERE id=$1", src)
    assert row["status"] == "merged"
    assert row["merged_into_id"] == tgt
    # 迁移关系留痕
    rel = await conn.fetchrow(
        "SELECT * FROM layer_merge_relations WHERE source_layer_id=$1", src
    )
    assert rel["target_layer_id"] == tgt and rel["reason"] == "同一堆积单位"
    # 审计事件
    n = await conn.fetchval(
        "SELECT count(*) FROM audit_events WHERE event_type='layer.merged' AND entity_id=$1", src
    )
    assert n == 1


async def test_merge_rewrites_dag_edges(conn):
    t = await make_trench(conn)
    top = await make_layer(conn, t, "TOP")
    src = await make_layer(conn, t, "SRC", parent_ids=[top])
    tgt = await make_layer(conn, t, "TGT")
    child = await make_layer(conn, t, "CHILD", parent_ids=[src])

    await merge_layers(conn, src, tgt)

    # 目标层继承源层的父边；子层改挂目标层
    assert await conn.fetchval(
        "SELECT 1 FROM layer_parents WHERE child_id=$1 AND parent_id=$2", tgt, top
    )
    assert await conn.fetchval(
        "SELECT 1 FROM layer_parents WHERE child_id=$1 AND parent_id=$2", child, tgt
    )
    assert await conn.fetchval("SELECT count(*) FROM layer_parents WHERE child_id=$1 OR parent_id=$1", src) == 0


async def test_merge_into_closed_target_rejected(conn):
    t = await make_trench(conn)
    src = await make_layer(conn, t, "SRC")
    tgt = await make_layer(conn, t, "TGT", status="closed")
    with pytest.raises(BusinessError, match="开放"):
        await merge_layers(conn, src, tgt)
    # 失败不留痕：源层仍开放，无迁移关系
    assert await conn.fetchval("SELECT status FROM layers WHERE id=$1", src) == "open"
    assert await conn.fetchval("SELECT count(*) FROM layer_merge_relations") == 0


async def test_merge_self_rejected(conn):
    t = await make_trench(conn)
    a = await make_layer(conn, t, "A")
    with pytest.raises(BusinessError):
        await merge_layers(conn, a, a)


async def test_merge_then_new_find_must_go_to_target(conn):
    t = await make_trench(conn)
    src = await make_layer(conn, t, "SRC")
    tgt = await make_layer(conn, t, "TGT")
    await merge_layers(conn, src, tgt)
    # 已合并源层不再接收出土物
    with pytest.raises(Exception):
        await make_find(conn, src, "Fbad")
    # 目标层仍可接收
    f = await make_find(conn, tgt, "Fok")
    assert f is not None
