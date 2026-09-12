import json
from typing import Any

import redis.asyncio as aioredis
from fastapi import Request

from app.config import get_settings


class Cache:
    """简单 JSON 缓存；Redis 不可用时自动降级为无缓存，不阻塞业务。"""

    def __init__(self) -> None:
        settings = get_settings()
        self._redis = aioredis.from_url(settings.redis_url, decode_responses=True)
        self._ttl = settings.cache_ttl_seconds

    async def get(self, key: str) -> Any | None:
        try:
            raw = await self._redis.get(key)
            return json.loads(raw) if raw else None
        except Exception:
            return None

    async def set(self, key: str, value: Any) -> None:
        try:
            await self._redis.set(key, json.dumps(value, default=str), ex=self._ttl)
        except Exception:
            pass

    async def invalidate_prefix(self, *prefixes: str) -> None:
        try:
            for prefix in prefixes:
                async for key in self._redis.scan_iter(match=f"{prefix}*", count=200):
                    await self._redis.delete(key)
        except Exception:
            pass

    async def close(self) -> None:
        try:
            await self._redis.aclose()
        except Exception:
            pass


def cache_from(request: Request) -> Cache:
    return request.app.state.cache
