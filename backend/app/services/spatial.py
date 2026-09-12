import json
from typing import Any
from uuid import UUID

import asyncpg


async def features_in_trench(conn: asyncpg.Connection, trench_id: UUID) -> dict:
    """GeoJSON FeatureCollection：探方边界 + 层位出土点。"""
    trench = await conn.fetchrow(
        "SELECT code, ST_AsGeoJSON(geom)::jsonb AS geom FROM trenches WHERE id=$1",
        trench_id,
    )
    find_rows = await conn.fetch(
        """
        SELECT f.code, f.category, f.found_on, f.layer_id, l.code AS layer_code,
               ST_AsGeoJSON(f.position)::jsonb AS geom
        FROM finds f JOIN layers l ON l.id = f.layer_id
        WHERE l.trench_id=$1 AND f.position IS NOT NULL
        """,
        trench_id,
    )
    sample_rows = await conn.fetch(
        """
        SELECT s.code, s.material, s.collected_on, s.layer_id, l.code AS layer_code,
               ST_AsGeoJSON(s.position)::jsonb AS geom
        FROM samples s JOIN layers l ON l.id = s.layer_id
        WHERE l.trench_id=$1 AND s.position IS NOT NULL
        """,
        trench_id,
    )
    features: list[dict[str, Any]] = []

    def _as_dict(value: Any) -> dict:
        return value if isinstance(value, dict) else json.loads(value)

    if trench and trench["geom"]:
        features.append({
            "type": "Feature",
            "geometry": _as_dict(trench["geom"]),
            "properties": {"kind": "trench", "code": trench["code"]},
        })
    for r in find_rows:
        d = dict(r)
        geom = d.pop("geom")
        features.append({"type": "Feature", "geometry": _as_dict(geom),
                         "properties": {"kind": "find", **d}})
    for r in sample_rows:
        d = dict(r)
        geom = d.pop("geom")
        features.append({"type": "Feature", "geometry": _as_dict(geom),
                         "properties": {"kind": "sample", **d}})
    return {"type": "FeatureCollection", "features": features}


async def spatial_search(conn: asyncpg.Connection, geojson_geom: dict,
                         kind: str = "find") -> list[dict]:
    geom_text = json.dumps(geojson_geom)
    if kind == "find":
        rows = await conn.fetch(
            """
            SELECT f.id, f.code, f.category, f.found_on, f.layer_id,
                   ST_AsGeoJSON(f.position)::jsonb AS position
            FROM finds f
            WHERE f.position IS NOT NULL
              AND ST_Intersects(f.position, ST_GeomFromGeoJSON($1::text))
            """,
            geom_text,
        )
    else:
        rows = await conn.fetch(
            """
            SELECT s.id, s.code, s.material, s.collected_on, s.layer_id,
                   ST_AsGeoJSON(s.position)::jsonb AS position
            FROM samples s
            WHERE s.position IS NOT NULL
              AND ST_Intersects(s.position, ST_GeomFromGeoJSON($1::text))
            """,
            geom_text,
        )
    return [dict(r) for r in rows]


async def distance_between(conn: asyncpg.Connection, find_a: UUID,
                           find_b: UUID) -> dict:
    row = await conn.fetchrow(
        """
        SELECT ST_Distance(a.position::geography, b.position::geography) AS meters
        FROM finds a, finds b
        WHERE a.id=$1 AND b.id=$2
        """,
        find_a, find_b,
    )
    if not row or row["meters"] is None:
        return {"meters": None}
    return {"meters": round(float(row["meters"]), 3)}
