import json
from uuid import UUID

import asyncpg

from app.errors import BusinessError
from app.services.audit import record_event


async def create_site(conn: asyncpg.Connection, data: dict) -> UUID:
    try:
        return await conn.fetchval(
            """
            INSERT INTO sites (code, name, description, centroid, boundary)
            VALUES ($1,$2,$3,
                    CASE WHEN $4::text IS NULL THEN NULL ELSE ST_GeomFromGeoJSON($4::text) END,
                    CASE WHEN $5::text IS NULL THEN NULL ELSE ST_GeomFromGeoJSON($5::text) END)
            RETURNING id
            """,
            data["code"], data["name"], data.get("description"),
            json.dumps(data["centroid"]) if data.get("centroid") else None,
            json.dumps(data["boundary"]) if data.get("boundary") else None,
        )
    except asyncpg.UniqueViolationError:
        raise BusinessError(f"遗址编号 {data['code']} 已存在", 409, "duplicate_code")


async def list_sites(conn: asyncpg.Connection) -> list[dict]:
    rows = await conn.fetch(
        """
        SELECT id, code, name, description,
               ST_AsGeoJSON(centroid)::jsonb AS centroid,
               ST_AsGeoJSON(boundary)::jsonb AS boundary,
               created_at
        FROM sites ORDER BY code
        """
    )
    return [dict(r) for r in rows]


async def get_site(conn: asyncpg.Connection, site_id: UUID) -> dict:
    row = await conn.fetchrow(
        """
        SELECT id, code, name, description,
               ST_AsGeoJSON(centroid)::jsonb AS centroid,
               ST_AsGeoJSON(boundary)::jsonb AS boundary,
               created_at
        FROM sites WHERE id=$1
        """,
        site_id,
    )
    if not row:
        raise BusinessError("遗址不存在", 404, "not_found")
    return dict(row)


async def create_trench(conn: asyncpg.Connection, site_id: UUID, data: dict) -> UUID:
    async with conn.transaction():
        try:
            trench_id = await conn.fetchval(
                """
                INSERT INTO trenches (site_id, code, geom, elevation, opened_on, closed_on, note)
                VALUES ($1,$2,
                        CASE WHEN $3::text IS NULL THEN NULL
                             ELSE ST_GeomFromGeoJSON($3::text) END,
                        $4,$5,$6,$7)
                RETURNING id
                """,
                site_id, data["code"],
                json.dumps(data["geom"]) if data.get("geom") else None,
                data.get("elevation"), data["opened_on"], data.get("closed_on"),
                data.get("note"),
            )
        except asyncpg.ForeignKeyViolationError:
            raise BusinessError("遗址不存在", 404, "not_found")
        except asyncpg.UniqueViolationError:
            raise BusinessError(f"探方编号 {data['code']} 在该遗址下已存在", 409,
                                "duplicate_code")
        await record_event(conn, "trench.created", "trench", trench_id,
                           {"site_id": str(site_id), "code": data["code"]})
    return trench_id


async def list_trenches(conn: asyncpg.Connection, site_id: UUID) -> list[dict]:
    rows = await conn.fetch(
        """
        SELECT id, site_id, code, elevation, opened_on, closed_on, note,
               ST_AsGeoJSON(geom)::jsonb AS geom, created_at
        FROM trenches WHERE site_id=$1 ORDER BY code
        """,
        site_id,
    )
    return [dict(r) for r in rows]


async def get_trench(conn: asyncpg.Connection, trench_id: UUID) -> dict:
    row = await conn.fetchrow(
        """
        SELECT id, site_id, code, elevation, opened_on, closed_on, note,
               ST_AsGeoJSON(geom)::jsonb AS geom, created_at
        FROM trenches WHERE id=$1
        """,
        trench_id,
    )
    if not row:
        raise BusinessError("探方不存在", 404, "not_found")
    return dict(row)
