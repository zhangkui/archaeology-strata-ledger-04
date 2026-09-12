"""层位 DAG：无环关系、跨探方限制、父子约束。"""
import pytest

from conftest import make_layer, make_site, make_trench


async def test_simple_parent_chain_ok(conn):
    t = await make_trench(conn)
    l1 = await make_layer(conn, t, "L1")
    l2 = await make_layer(conn, t, "L2", parent_ids=[l1])
    l3 = await make_layer(conn, t, "L3", parent_ids=[l2])

    parents = await conn.fetch(
        "SELECT parent_id FROM layer_parents WHERE child_id=$1 ORDER BY parent_id", l3
    )
    assert len(parents) == 1
    assert parents[0]["parent_id"] == l2


async def test_direct_cycle_rejected(conn):
    t = await make_trench(conn)
    a = await make_layer(conn, t, "A")
    b = await make_layer(conn, t, "A2", parent_ids=[a])
    # 让 A 反过来挂到 B 上 -> A->B->A 成环
    with pytest.raises(Exception) as ei:
        await conn.execute(
            "INSERT INTO layer_parents (child_id, parent_id) VALUES ($1,$2)", a, b
        )
    assert "环" in str(ei.value)


async def test_indirect_cycle_rejected(conn):
    t = await make_trench(conn)
    a = await make_layer(conn, t, "A")
    b = await make_layer(conn, t, "B", parent_ids=[a])
    c = await make_layer(conn, t, "C", parent_ids=[b])
    d = await make_layer(conn, t, "D", parent_ids=[c])
    with pytest.raises(Exception) as ei:
        # A -> D -> C -> B -> A
        await conn.execute(
            "INSERT INTO layer_parents (child_id, parent_id) VALUES ($1,$2)", a, d
        )
    assert "环" in str(ei.value)


async def test_diamond_dag_allowed(conn):
    """同一层有多个父层（菱形）是合法 DAG。"""
    t = await make_trench(conn)
    a = await make_layer(conn, t, "A")
    b = await make_layer(conn, t, "B", parent_ids=[a])
    c = await make_layer(conn, t, "C", parent_ids=[a])
    d = await make_layer(conn, t, "D", parent_ids=[b, c])
    links = await conn.fetchval(
        "SELECT count(*) FROM layer_parents WHERE child_id=$1", d
    )
    assert links == 2


async def test_self_link_rejected(conn):
    t = await make_trench(conn)
    a = await make_layer(conn, t, "A")
    with pytest.raises(Exception):
        await conn.execute(
            "INSERT INTO layer_parents (child_id, parent_id) VALUES ($1,$1)", a
        )


async def test_cross_trench_parent_rejected(conn):
    s1, s2 = await make_site(conn, "S1"), await make_site(conn, "S2")
    t1, t2 = await make_trench(conn, s1, "T1", None), await make_trench(conn, s2, "T2", None)
    l1 = await make_layer(conn, t1, "L1")
    l2 = await make_layer(conn, t2, "L2")
    with pytest.raises(Exception) as ei:
        await conn.execute(
            "INSERT INTO layer_parents (child_id, parent_id) VALUES ($1,$2)", l2, l1
        )
    assert "同一探方" in str(ei.value)
