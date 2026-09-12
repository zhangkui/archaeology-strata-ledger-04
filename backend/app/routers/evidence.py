from datetime import date

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile

from app.cachekeys import invalidate_for_layer
from app.db.pool import get_conn
from app import schemas
from app.services import evidence as svc

router = APIRouter(prefix="/api", tags=["evidence"])


@router.post("/finds", response_model=schemas.FindOut, status_code=201)
async def create_find(body: schemas.FindIn, request: Request, conn=Depends(get_conn)):
    find_id = await svc.create_find(conn, body.model_dump())
    await invalidate_for_layer(request, conn, str(body.layer_id))
    rows = await svc.list_finds(conn)
    return next(r for r in rows if str(r["id"]) == str(find_id))


@router.get("/finds", response_model=list[schemas.FindOut])
async def all_finds(layer_id: str | None = None, conn=Depends(get_conn)):
    return await svc.list_finds(conn, layer_id=layer_id)


@router.post("/samples", response_model=schemas.SampleOut, status_code=201)
async def create_sample(body: schemas.SampleIn, request: Request, conn=Depends(get_conn)):
    sample_id = await svc.create_sample(conn, body.model_dump())
    await invalidate_for_layer(request, conn, str(body.layer_id))
    rows = await svc.list_samples(conn)
    return next(r for r in rows if str(r["id"]) == str(sample_id))


@router.get("/samples", response_model=list[schemas.SampleOut])
async def all_samples(layer_id: str | None = None, conn=Depends(get_conn)):
    return await svc.list_samples(conn, layer_id=layer_id)


@router.post("/photos", response_model=schemas.PhotoOut, status_code=201)
async def upload_photo(
    request: Request,
    file: UploadFile = File(...),
    layer_id: str | None = Form(default=None),
    find_id: str | None = Form(default=None),
    taken_on: date | None = Form(default=None),
    conn=Depends(get_conn),
):
    if not layer_id and not find_id:
        from fastapi import HTTPException
        raise HTTPException(400, "照片必须关联层位或出土物")

    storage = request.app.state.storage
    import io

    blob = await file.read()
    key_prefix = f"layers/{layer_id}" if layer_id else f"finds/{find_id}"
    object_key = f"{key_prefix}/{file.filename}"
    try:
        # 读入内存以获得长度并可重放；考古照片通常 < 20MB，由反向代理限制体积
        storage._client.put_object(
            storage.bucket, object_key, io.BytesIO(blob),
            length=len(blob), content_type=file.content_type or "application/octet-stream",
        )
    except Exception as exc:  # MinIO 不可达 / 建桶失败
        from fastapi import HTTPException
        raise HTTPException(503, f"对象存储不可用，照片未保存: {exc}") from exc
    photo_id = await svc.create_photo_record(
        conn, layer_id=layer_id, find_id=find_id, object_key=object_key,
        bucket=storage.bucket, filename=file.filename or "photo",
        content_type=file.content_type, size_bytes=len(blob), taken_on=taken_on,
    )
    rows = await svc.list_photos(conn, storage, layer_id=layer_id, find_id=find_id)
    return next(r for r in rows if str(r["id"]) == str(photo_id))


@router.get("/photos", response_model=list[schemas.PhotoOut])
async def list_photos(request: Request, layer_id: str | None = None,
                      find_id: str | None = None, conn=Depends(get_conn)):
    return await svc.list_photos(request.app.state.storage, conn,
                                 layer_id=layer_id, find_id=find_id)
