from pathlib import Path
from typing import AsyncIterator

import asyncpg
from fastapi import Request

from app.config import get_settings

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


async def create_pool() -> asyncpg.Pool:
    settings = get_settings()
    return await asyncpg.create_pool(
        settings.database_url,
        min_size=2,
        max_size=10,
        # asyncpg 无法直接编码 geometry，统一以 WKT/EWKT 文本收发
        init=asyncpg_init,
    )


async def asyncpg_init(conn: asyncpg.Connection) -> None:
    import json
    import uuid

    # 允许 str / UUID 两种 Python 值绑定到 uuid 列，读出统一为 uuid.UUID
    await conn.set_type_codec(
        "uuid",
        encoder=lambda value: str(value),
        decoder=lambda value: uuid.UUID(value),
        schema="pg_catalog",
        format="text",
    )
    # json/jsonb：读出自动解析；写入接受 Python 对象（预序列化字符串原样透传）
    await conn.set_type_codec(
        "json",
        encoder=lambda v: v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, default=str),
        decoder=json.loads,
        schema="pg_catalog",
    )
    await conn.set_type_codec(
        "jsonb",
        encoder=lambda v: v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, default=str),
        decoder=json.loads,
        schema="pg_catalog",
    )
    # geometry 类型由迁移中的 CREATE EXTENSION postgis 创建；
    # 池首个连接可能早于迁移，注册失败可忽略（读写均显式走 ST_AsGeoJSON/ST_GeomFromGeoJSON）
    try:
        await conn.set_type_codec(
            "geometry",
            encoder=str,
            decoder=str,
            format="text",
            schema="public",
        )
    except ValueError:
        pass
    # 审计触发器通过会话变量取操作人
    await conn.execute("SELECT set_config('app.actor', COALESCE(current_setting('app.actor', true), 'system'), true)")


async def run_migrations(conn: asyncpg.Connection) -> list[str]:
    applied: list[str] = []
    # 扩展必须先于 geometry 编解码器 / 应用 SQL 就位
    await conn.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    await conn.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version text PRIMARY KEY,
            applied_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        version = path.name
        already = await conn.fetchval(
            "SELECT 1 FROM schema_migrations WHERE version = $1", version
        )
        if already:
            continue
        sql = path.read_text(encoding="utf-8")
        async with conn.transaction():
            await conn.execute(sql)
            await conn.execute(
                "INSERT INTO schema_migrations (version) VALUES ($1)", version
            )
        applied.append(version)
    return applied


async def get_conn(request: Request) -> AsyncIterator[asyncpg.Connection]:
    """路由依赖：从事务池取连接，并把 X-Actor 注入审计会话变量。

    用会话级设置(false)：asyncpg 自动提交模式下事务局部设置(true)会在语句结束即失效。
    """
    pool: asyncpg.Pool = request.app.state.pool
    async with pool.acquire() as conn:
        actor = request.headers.get("X-Actor", "anonymous")[:200]
        await conn.execute("SELECT set_config('app.actor', $1, false)", actor)
        yield conn
