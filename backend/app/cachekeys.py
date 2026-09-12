"""缓存键约定与按探方失效辅助。"""
from fastapi import Request

from app.cache import cache_from


def tree_key(trench_id: str) -> str:
    return f"trench:{trench_id}:tree"


def features_key(trench_id: str) -> str:
    return f"trench:{trench_id}:features"


async def invalidate_trench(request: Request, trench_id: str) -> None:
    await cache_from(request).invalidate_prefix(f"trench:{trench_id}:")


async def invalidate_for_layer(request: Request, conn, layer_id: str) -> None:
    trench_id = await conn.fetchval(
        "SELECT trench_id FROM layers WHERE id=$1", layer_id
    )
    if trench_id:
        await invalidate_trench(request, str(trench_id))
