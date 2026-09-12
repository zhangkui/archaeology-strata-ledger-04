from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query

from app.db.pool import get_conn
from app import schemas
from app.services import layers as layer_svc

router = APIRouter(prefix="/api/trenches", tags=["replay"])


@router.get("/{trench_id}/replay", response_model=schemas.ReplayOut)
async def replay(
    trench_id: str,
    as_of: datetime = Query(..., description="ISO8601，回放该时刻的数据版本"),
    conn=Depends(get_conn),
):
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)
    return await layer_svc.replay_as_of(conn, trench_id, as_of)
