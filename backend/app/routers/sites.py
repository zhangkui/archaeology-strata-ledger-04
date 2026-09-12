from fastapi import APIRouter, Depends
from asyncpg import Connection

from app.db.pool import get_conn
from app import schemas
from app.services import sites as site_svc

router = APIRouter(prefix="/api/sites", tags=["sites"])


@router.post("", response_model=schemas.SiteOut, status_code=201)
async def create_site(body: schemas.SiteIn, conn=Depends(get_conn)):
    site_id = await site_svc.create_site(conn, body.model_dump())
    return await site_svc.get_site(conn, site_id)


@router.get("", response_model=list[schemas.SiteOut])
async def list_sites(conn=Depends(get_conn)):
    return await site_svc.list_sites(conn)


@router.get("/{site_id}", response_model=schemas.SiteOut)
async def get_site(site_id: str, conn=Depends(get_conn)):
    return await site_svc.get_site(conn, site_id)
