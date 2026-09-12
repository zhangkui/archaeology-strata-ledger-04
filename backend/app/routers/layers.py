from fastapi import APIRouter, Depends, Request

from app.cachekeys import invalidate_for_layer
from app.db.pool import get_conn
from app import schemas
from app.services import layers as svc

router = APIRouter(prefix="/api/layers", tags=["layers"])


@router.get("/{layer_id}", response_model=schemas.LayerOut)
async def get_layer(layer_id: str, conn=Depends(get_conn)):
    return await svc.get_layer(conn, layer_id)


@router.patch("/{layer_id}", response_model=schemas.LayerOut)
async def amend_layer(layer_id: str, body: schemas.LayerUpdate, request: Request, conn=Depends(get_conn)):
    patch = body.model_dump(exclude_unset=True)
    reason = patch.pop("reason", None)
    close = patch.pop("close", False)
    reopen = patch.pop("reopen", False)
    patch.pop("status", None)  # 状态只能通过 close/reopen/merge 流转
    if close:
        patch["close"] = True
    if reopen:
        patch["reopen"] = True
    result = await svc.amend_layer(conn, layer_id, patch, reason)
    await invalidate_for_layer(request, conn, layer_id)
    return result


@router.post("/{layer_id}/parents", status_code=204)
async def add_parent(layer_id: str, body: schemas.ParentLinkIn, request: Request, conn=Depends(get_conn)):
    await svc.add_parent_link(conn, layer_id, body.parent_id, body.relation)
    await invalidate_for_layer(request, conn, layer_id)


@router.delete("/{layer_id}/parents/{parent_id}", status_code=204)
async def remove_parent(layer_id: str, parent_id: str, request: Request, conn=Depends(get_conn)):
    await svc.remove_parent_link(conn, layer_id, parent_id)
    await invalidate_for_layer(request, conn, layer_id)


@router.delete("/{layer_id}", status_code=204)
async def delete_layer(layer_id: str, request: Request, conn=Depends(get_conn)):
    await svc.delete_layer(conn, layer_id)
    await invalidate_for_layer(request, conn, layer_id)


@router.get("/{layer_id}/revisions", response_model=list[schemas.RevisionOut])
async def revisions(layer_id: str, conn=Depends(get_conn)):
    return await svc.list_revisions(conn, layer_id)


@router.post("/merge", response_model=schemas.MergeOut)
async def merge(body: schemas.MergeIn, request: Request, conn=Depends(get_conn)):
    result = await svc.merge_layers(
        conn, body.source_layer_id, body.target_layer_id, body.reason
    )
    await invalidate_for_layer(request, conn, str(body.source_layer_id))
    return result


@router.post("/{layer_id}/close", response_model=schemas.LayerOut)
async def close_layer(layer_id: str, request: Request, conn=Depends(get_conn)):
    result = await svc.amend_layer(conn, layer_id, {"close": True})
    await invalidate_for_layer(request, conn, layer_id)
    return result


@router.post("/{layer_id}/reopen", response_model=schemas.LayerOut)
async def reopen_layer(layer_id: str, request: Request, conn=Depends(get_conn)):
    result = await svc.amend_layer(conn, layer_id, {"reopen": True})
    await invalidate_for_layer(request, conn, layer_id)
    return result
