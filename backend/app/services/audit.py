import json
from typing import Any
from uuid import UUID

import asyncpg


async def record_event(
    conn: asyncpg.Connection,
    event_type: str,
    entity_type: str,
    entity_id: UUID | str | None,
    payload: dict[str, Any],
) -> None:
    await conn.execute(
        """
        INSERT INTO audit_events (event_type, entity_type, entity_id, payload)
        VALUES ($1, $2, $3, $4::jsonb)
        """,
        event_type,
        entity_type,
        entity_id if isinstance(entity_id, UUID) else (UUID(entity_id) if entity_id else None),
        json.dumps(payload, ensure_ascii=False, default=str),
    )
