import json
from typing import Any
from uuid import UUID

import asyncpg

from app.services.audit import record_event


def _find_select(where: str = "") -> str:
    return f"""
    SELECT id, layer_id, code, category, found_on, z_elevation, note,
           ST_AsGeoJSON(position)::jsonb AS position, created_at
    FROM finds {where}
    """


async def list_finds(conn: asyncpg.Connection, layer_id: UUID | None = None,
                     trench_id: UUID | None = None) -> list[dict]:
    if layer_id:
        rows = await conn.fetch(_find_select("WHERE layer_id=$1 ORDER BY found_on, code"),
                                layer_id)
    elif trench_id:
        rows = await conn.fetch(
            _find_select(
                "WHERE layer_id IN (SELECT id FROM layers WHERE trench_id=$1) "
                "ORDER BY found_on, code"
            ),
            trench_id,
        )
    else:
        rows = await conn.fetch(_find_select("ORDER BY found_on, code"))
    return [dict(r) for r in rows]


async def create_find(conn: asyncpg.Connection, data: dict, ref: str | None = None) -> UUID:
    position = data.get("position")
    async with conn.transaction():
        find_id = await conn.fetchval(
            """
            INSERT INTO finds (layer_id, code, category, found_on, z_elevation, note, position)
            VALUES ($1,$2,$3,$4,$5,$6,
                    CASE WHEN $7::text IS NULL THEN NULL
                         ELSE ST_GeomFromGeoJSON($7::text) END)
            RETURNING id
            """,
            data["layer_id"], data["code"], data["category"], data["found_on"],
            data.get("z_elevation"), data.get("note"),
            json.dumps(position) if position is not None else None,
        )
        await record_event(conn, "find.created", "find", find_id,
                           {"code": data["code"], "layer_id": str(data["layer_id"]),
                            "ref": ref})
    return find_id


async def create_sample(conn: asyncpg.Connection, data: dict, ref: str | None = None) -> UUID:
    position = data.get("position")
    async with conn.transaction():
        sample_id = await conn.fetchval(
            """
            INSERT INTO samples (layer_id, find_id, code, material, collected_on, note, position)
            VALUES ($1,$2,$3,$4,$5,$6,
                    CASE WHEN $7::text IS NULL THEN NULL
                         ELSE ST_GeomFromGeoJSON($7::text) END)
            RETURNING id
            """,
            data["layer_id"], data.get("find_id"), data["code"], data["material"],
            data["collected_on"], data.get("note"),
            json.dumps(position) if position is not None else None,
        )
        await record_event(conn, "sample.created", "sample", sample_id,
                           {"code": data["code"], "layer_id": str(data["layer_id"]),
                            "ref": ref})
    return sample_id


async def list_samples(conn: asyncpg.Connection, layer_id: UUID | None = None,
                       trench_id: UUID | None = None) -> list[dict]:
    base = """
        SELECT s.id, s.layer_id, s.find_id, s.code, s.material, s.collected_on, s.note,
               ST_AsGeoJSON(s.position)::jsonb AS position, s.created_at
        FROM samples s
    """
    if layer_id:
        rows = await conn.fetch(base + " WHERE s.layer_id=$1 ORDER BY s.collected_on, s.code",
                                layer_id)
    elif trench_id:
        rows = await conn.fetch(
            base + " JOIN layers l ON l.id = s.layer_id "
                   "WHERE l.trench_id=$1 ORDER BY s.collected_on, s.code",
            trench_id,
        )
    else:
        rows = await conn.fetch(base + " ORDER BY s.collected_on, s.code")
    return [dict(r) for r in rows]


async def list_photos(conn: asyncpg.Connection, storage: Any,
                      layer_id: UUID | None = None, find_id: UUID | None = None) -> list[dict]:
    sql = "SELECT * FROM photos"
    clauses, args = [], []
    if layer_id:
        clauses.append(f"layer_id=${len(args) + 1}")
        args.append(layer_id)
    if find_id:
        clauses.append(f"find_id=${len(args) + 1}")
        args.append(find_id)
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY created_at DESC"
    rows = await conn.fetch(sql, *args)
    out = []
    for r in rows:
        d = dict(r)
        d["url"] = storage.presigned_url(d["object_key"])
        out.append(d)
    return out


async def create_photo_record(conn: asyncpg.Connection, *, layer_id: UUID | None,
                              find_id: UUID | None, object_key: str, bucket: str,
                              filename: str, content_type: str | None,
                              size_bytes: int, taken_on: Any) -> UUID:
    async with conn.transaction():
        photo_id = await conn.fetchval(
            """
            INSERT INTO photos (layer_id, find_id, object_key, bucket, filename,
                                content_type, size_bytes, taken_on)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8) RETURNING id
            """,
            layer_id, find_id, object_key, bucket, filename, content_type,
            size_bytes, taken_on,
        )
        await record_event(conn, "photo.created", "photo", photo_id,
                           {"filename": filename, "layer_id": str(layer_id) if layer_id else None,
                            "find_id": str(find_id) if find_id else None})
    return photo_id
