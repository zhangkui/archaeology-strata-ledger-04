"""批量导入单事务：全部成功才提交，任一失败整体回滚。"""
import json

import pytest

from app.errors import BusinessError
from app.services.batch import run_batch

from conftest import make_trench


def _items_ok():
    return [
        {"op": "layer", "ref": "L1", "data": {
            "code": "L1", "opened_on": "2026-09-01",
            "original_observation": {"note": "表土层"}}},
        {"op": "layer", "ref": "L2", "data": {
            "code": "L2", "opened_on": "2026-09-01",
            "parent_ids": [{"$ref": "L1"}]}},
        {"op": "find", "data": {
            "layer_id": {"$ref": "L2"}, "code": "F1", "category": "陶片",
            "found_on": "2026-09-02"}},
        {"op": "sample", "data": {
            "layer_id": {"$ref": "L2"}, "code": "S1", "material": "炭样",
            "collected_on": "2026-09-02"}},
    ]


async def test_batch_commits_all_or_nothing_success(conn):
    t = await make_trench(conn)
    result = await run_batch(conn, t, _items_ok())
    assert result["committed"] is True
    assert result["count"] == 4
    assert await conn.fetchval("SELECT count(*) FROM layers WHERE trench_id=$1", t) == 2
    assert await conn.fetchval("SELECT count(*) FROM finds") == 1
    # 批内 $ref 生效
    l1 = await conn.fetchval("SELECT id FROM layers WHERE trench_id=$1 AND code='L1'", t)
    l2 = await conn.fetchval("SELECT id FROM layers WHERE trench_id=$1 AND code='L2'", t)
    assert await conn.fetchval(
        "SELECT parent_id FROM layer_parents WHERE child_id=$1", l2
    ) == l1
    # 批审计事件
    assert await conn.fetchval(
        "SELECT count(*) FROM audit_events WHERE event_type='batch.committed'"
    ) == 1


async def test_batch_rolls_back_when_last_item_invalid(conn):
    t = await make_trench(conn)
    items = _items_ok()
    # 最后一个出土物引用不存在的层位 -> FK 失败
    items.append({"op": "find", "data": {
        "layer_id": "00000000-0000-0000-0000-000000000000",
        "code": "Fbad", "category": "x", "found_on": "2026-09-02"}})
    with pytest.raises(BusinessError, match="回滚"):
        await run_batch(conn, t, items)
    # 前面已 INSERT 的层位/出土物必须全部回滚
    assert await conn.fetchval("SELECT count(*) FROM layers WHERE trench_id=$1", t) == 0
    assert await conn.fetchval("SELECT count(*) FROM finds") == 0
    assert await conn.fetchval("SELECT count(*) FROM layer_parents") == 0
    assert await conn.fetchval(
        "SELECT count(*) FROM audit_events WHERE event_type='batch.committed'"
    ) == 0


async def test_batch_rolls_back_on_cycle(conn):
    t = await make_trench(conn)
    items = [
        {"op": "layer", "ref": "A", "data": {"code": "A", "opened_on": "2026-09-01"}},
        {"op": "layer", "ref": "B", "data": {"code": "B", "opened_on": "2026-09-01",
                                             "parent_ids": [{"$ref": "A"}]}},
        {"op": "parent_link", "data": {"child_id": {"$ref": "A"},
                                       "parent_id": {"$ref": "B"}}},
    ]
    with pytest.raises(BusinessError, match="回滚"):
        await run_batch(conn, t, items)
    assert await conn.fetchval("SELECT count(*) FROM layers WHERE trench_id=$1", t) == 0


async def test_batch_bad_ref_rejected(conn):
    t = await make_trench(conn)
    with pytest.raises(BusinessError, match="ref"):
        await run_batch(conn, t, [
            {"op": "find", "data": {"layer_id": {"$ref": "GHOST"},
                                    "code": "F", "category": "x",
                                    "found_on": "2026-09-02"}},
        ])


async def test_batch_rolls_back_on_closed_layer(conn):
    t = await make_trench(conn)
    await run_batch(conn, t, [
        {"op": "layer", "ref": "L1", "data": {"code": "L1", "opened_on": "2026-09-01"}},
    ])
    layer_id = await conn.fetchval(
        "SELECT id FROM layers WHERE trench_id=$1 AND code='L1'", t
    )
    await conn.execute("UPDATE layers SET status='closed' WHERE id=$1", layer_id)
    with pytest.raises(BusinessError, match="回滚"):
        await run_batch(conn, t, [
            {"op": "find", "data": {"layer_id": str(layer_id),
                                    "code": "F2", "category": "x",
                                    "found_on": "2026-09-03"}},
        ])
    assert await conn.fetchval("SELECT count(*) FROM finds") == 0
