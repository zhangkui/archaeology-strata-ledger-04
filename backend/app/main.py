import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.cache import Cache
from app.config import get_settings
from app.db.pool import create_pool, run_migrations
from app.errors import register_exception_handlers
from app.routers import audit, evidence, layers, replay, sites, spatial, trenches
from app.storage import ObjectStorage

logger = logging.getLogger("archaeo")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.pool = await create_pool()

    # 迁移：数据库就绪后执行；容器内由 healthcheck 保证
    async with app.state.pool.acquire() as conn:
        applied = await run_migrations(conn)
        if applied:
            logger.info("applied migrations: %s", applied)

    app.state.cache = Cache()
    app.state.storage = ObjectStorage()
    try:
        app.state.storage.ensure_bucket()
    except Exception as exc:  # MinIO 尚未就绪不应阻断 API
        logger.warning("MinIO bucket ensure skipped: %s", exc)

    yield

    await app.state.cache.close()
    await app.state.pool.close()


app = FastAPI(
    title="考古发掘层位证据链记录系统",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

for r in (
    sites.router,
    trenches.sites_router,
    trenches.router,
    layers.router,
    evidence.router,
    replay.router,
    audit.router,
    spatial.router,
):
    app.include_router(r)


@app.get("/health")
async def health():
    async with app.state.pool.acquire() as conn:
        ok = await conn.fetchval("SELECT 1")
    return {"status": "ok" if ok == 1 else "degraded", "postgis": True}
