"""pytest 配置：连接真实 PostgreSQL16+PostGIS3.5，每个用例重建 schema。

环境变量 TEST_DATABASE_URL 覆盖默认连接串。
先用 scripts/start-test-db.sh 启动测试库。
"""
import os
from pathlib import Path

import asyncpg
import pytest
import pytest_asyncio

DEFAULT_DSN = "postgresql://postgres@127.0.0.1:55436/archaeo_test"
DSN = os.environ.get("TEST_DATABASE_URL", DEFAULT_DSN)
MIGRATIONS = Path(__file__).parent.parent / "app" / "db" / "migrations"


async def _reset_schema(conn: asyncpg.Connection) -> None:
    await conn.execute("DROP SCHEMA public CASCADE")
    await conn.execute("CREATE SCHEMA public")
    await conn.execute("GRANT ALL ON SCHEMA public TO postgres")
    for path in sorted(MIGRATIONS.glob("*.sql")):
        await conn.execute(path.read_text(encoding="utf-8"))
    await conn.execute("SELECT set_config('app.actor', 'tester', false)")


@pytest_asyncio.fixture
async def conn():
    try:
        connection = await asyncpg.connect(DSN)
    except (asyncpg.PostgresError, OSError) as exc:
        pytest.skip(f"测试数据库不可用 ({DSN}): {exc}")
    # 统一 uuid/jsonb/geometry 编解码，与生产池一致
    import json
    import uuid

    await connection.set_type_codec(
        "uuid", encoder=lambda v: str(v), decoder=lambda v: uuid.UUID(v),
        schema="pg_catalog", format="text",
    )
    await connection.set_type_codec(
        "json",
        encoder=lambda v: v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, default=str),
        decoder=json.loads, schema="pg_catalog",
    )
    await connection.set_type_codec(
        "jsonb",
        encoder=lambda v: v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, default=str),
        decoder=json.loads, schema="pg_catalog",
    )
    await connection.set_type_codec(
        "geometry", encoder=str, decoder=str, schema="public", format="text",
    )
    await _reset_schema(connection)
    yield connection
    await connection.close()


# ---------------------------------------------------------------------------
# 测试数据构造辅助
# ---------------------------------------------------------------------------
POLYGON = (
    '{"type":"Polygon","coordinates":[[[116.4010,39.9010],[116.4020,39.9010],'
    '[116.4020,39.9020],[116.4010,39.9020],[116.4010,39.9010]]]}'
)
POINT_INSIDE = '{"type":"Point","coordinates":[116.4015,39.9015]}'
POINT_OUTSIDE = '{"type":"Point","coordinates":[120.0000,40.0000]}'


async def make_site(conn, code="S1"):
    return await conn.fetchval(
        "INSERT INTO sites (code, name) VALUES ($1,$2) RETURNING id", code, f"遗址{code}"
    )


async def make_trench(conn, site_id=None, code="T1", geom=POLYGON):
    if site_id is None:
        site_id = await make_site(conn)
    return await conn.fetchval(
        "INSERT INTO trenches (site_id, code, geom, opened_on) "
        "VALUES ($1,$2, CASE WHEN $3::text IS NULL THEN NULL ELSE ST_GeomFromGeoJSON($3::text) END, '2026-09-01') "
        "RETURNING id",
        site_id, code, geom,
    )


async def make_layer(conn, trench_id, code="L1", parent_ids=None, status="open"):
    layer_id = await conn.fetchval(
        "INSERT INTO layers (trench_id, code, status, opened_on, original_observation) "
        "VALUES ($1,$2,$3,'2026-09-01','{\"note\":\"原始\"}'::jsonb) RETURNING id",
        trench_id, code, status,
    )
    for pid in parent_ids or []:
        await conn.execute(
            "INSERT INTO layer_parents (child_id, parent_id) VALUES ($1,$2)", layer_id, pid
        )
    return layer_id


async def make_find(conn, layer_id, code="F1", point=POINT_INSIDE):
    return await conn.fetchval(
        "INSERT INTO finds (layer_id, code, category, found_on, position) "
        "VALUES ($1,$2,'陶片','2026-09-02', ST_GeomFromGeoJSON($3::text)) RETURNING id",
        layer_id, code, point,
    )
