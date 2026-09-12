from uuid import UUID

from fastapi import APIRouter, Depends

from app.db.pool import get_conn
from app import schemas

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("", response_model=list[schemas.AuditOut])
async def list_audit(
    entity_type: str | None = None,
    entity_id: UUID | None = None,
    event_type: str | None = None,
    limit: int = 200,
    conn=Depends(get_conn),
):
    clauses, args = [], []
    if entity_type:
        args.append(entity_type)
        clauses.append(f"entity_type = ${len(args)}")
    if entity_id:
        args.append(entity_id)
        clauses.append(f"entity_id = ${len(args)}")
    if event_type:
        args.append(event_type)
        clauses.append(f"event_type = ${len(args)}")
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    args.append(min(limit, 1000))
    rows = await conn.fetch(
        f"SELECT * FROM audit_events {where} ORDER BY created_at DESC, id DESC "
        f"LIMIT ${len(args)}",
        *args,
    )
    return [dict(r) for r in rows]


@router.get("/layer-merges")
async def list_merges(layer_id: UUID | None = None, conn=Depends(get_conn)):
    if layer_id:
        rows = await conn.fetch(
            "SELECT * FROM layer_merge_relations "
            "WHERE source_layer_id=$1 OR target_layer_id=$1 ORDER BY merged_at DESC",
            layer_id,
        )
    else:
        rows = await conn.fetch(
            "SELECT * FROM layer_merge_relations ORDER BY merged_at DESC"
        )
    return [dict(r) for r in rows]
