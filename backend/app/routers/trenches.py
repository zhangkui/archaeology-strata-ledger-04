from fastapi import APIRouter, Depends, Request

from app.cache import cache_from
from app.cachekeys import features_key, invalidate_trench, tree_key
from app.db.pool import get_conn
from app import schemas
from app.services import sites as site_svc
from app.services import layers as layer_svc
from app.services import evidence as ev_svc
from app.services import spatial as spatial_svc

router = APIRouter(prefix="/api/trenches", tags=["trenches"])


@router.post("/{trench_id}/layers", response_model=schemas.LayerOut, status_code=201)
async def create_layer(trench_id: str, body: schemas.LayerIn, request: Request, conn=Depends(get_conn)):
    data = body.model_dump()
    layer_id = await layer_svc.create_layer(conn, trench_id, data)
    await invalidate_trench(request, trench_id)
    return await layer_svc.get_layer(conn, layer_id)


@router.get("/{trench_id}/layers", response_model=list[schemas.LayerOut])
async def list_layers(trench_id: str, conn=Depends(get_conn)):
    return await layer_svc.list_layers(conn, trench_id)


@router.get("/{trench_id}/layer-tree")
async def layer_tree(trench_id: str, request: Request, conn=Depends(get_conn)):
    cache = cache_from(request)
    key = tree_key(trench_id)
    cached = await cache.get(key)
    if cached is not None:
        return cached
    tree = await layer_svc.layer_tree(conn, trench_id)
    await cache.set(key, tree)
    return tree


@router.post("/{trench_id}/batch", response_model=schemas.BatchResult)
async def run_batch(trench_id: str, body: schemas.BatchIn, request: Request, conn=Depends(get_conn)):
    from app.services.batch import run_batch as _run
    result = await _run(conn, trench_id, [i.model_dump() for i in body.items])
    await invalidate_trench(request, trench_id)
    return result


@router.get("/{trench_id}/finds", response_model=list[schemas.FindOut])
async def list_trench_finds(trench_id: str, conn=Depends(get_conn)):
    return await ev_svc.list_finds(conn, trench_id=trench_id)


@router.get("/{trench_id}/samples", response_model=list[schemas.SampleOut])
async def list_trench_samples(trench_id: str, conn=Depends(get_conn)):
    return await ev_svc.list_samples(conn, trench_id=trench_id)


@router.get("/{trench_id}/features")
async def trench_features(trench_id: str, request: Request, conn=Depends(get_conn)):
    cache = cache_from(request)
    key = features_key(trench_id)
    cached = await cache.get(key)
    if cached is not None:
        return cached
    fc = await spatial_svc.features_in_trench(conn, trench_id)
    await cache.set(key, fc)
    return fc


# 遗址下的探方
sites_router = APIRouter(prefix="/api/sites", tags=["trenches"])


@sites_router.post("/{site_id}/trenches", response_model=schemas.TrenchOut, status_code=201)
async def create_trench(site_id: str, body: schemas.TrenchIn, conn=Depends(get_conn)):
    trench_id = await site_svc.create_trench(conn, site_id, body.model_dump())
    return await site_svc.get_trench(conn, trench_id)


@sites_router.get("/{site_id}/trenches", response_model=list[schemas.TrenchOut])
async def list_trenches(site_id: str, conn=Depends(get_conn)):
    return await site_svc.list_trenches(conn, site_id)
