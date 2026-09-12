from uuid import UUID

from fastapi import APIRouter, Body, Depends

from app.db.pool import get_conn
from app.services import spatial as svc

router = APIRouter(prefix="/api/spatial", tags=["spatial"])


@router.post("/search/{kind}")
async def search(kind: str, geometry: dict = Body(..., embed=True), conn=Depends(get_conn)):
    """kind=find|sample；body 为任意 GeoJSON 几何（点/多边形）。"""
    if kind not in {"find", "sample"}:
        kind = "find"
    return await svc.spatial_search(conn, geometry, kind)


@router.get("/distance")
async def distance(a: UUID, b: UUID, conn=Depends(get_conn)):
    return await svc.distance_between(conn, a, b)
