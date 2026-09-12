"""批量导入：整批在单个数据库事务内提交，任一项失败整体回滚。

批内可用 "ref" 给实体起临时名，后续项通过 {"$ref": "name"} 引用，
例如先建层位 L1，再把出土物挂到 {"$ref": "L1"}。
"""
import json
from datetime import date, datetime
from typing import Any
from uuid import UUID

import asyncpg

from app.errors import BusinessError

_REF_PREFIX = "$ref"


def _resolve(value: Any, refs: dict[str, UUID]) -> Any:
    if isinstance(value, dict) and _REF_PREFIX in value and len(value) == 1:
        key = value[_REF_PREFIX]
        if key not in refs:
            raise BusinessError(f"批量项引用了不存在的 ref: {key}", 400, "bad_ref")
        return refs[key]
    if isinstance(value, dict):
        return {k: _resolve(v, refs) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve(v, refs) for v in value]
    return value


def _coerce_date(value: Any) -> date | None:
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


async def run_batch(conn: asyncpg.Connection, trench_id: UUID,
                    items: list[dict]) -> dict:
    refs: dict[str, UUID] = {}
    ids: dict[str, str] = {}
    try:
        async with conn.transaction():
            for index, item in enumerate(items):
                op = item.get("op")
                raw = item.get("data") or {}
                data = _resolve(raw, refs)
                ref = item.get("ref")
                ctx = f"items[{index}](op={op})"

                if op == "layer":
                    layer_id = await conn.fetchval(
                        """
                        INSERT INTO layers (trench_id, code, opened_on, closed_on,
                            description, soil_color, soil_texture, depth_top_cm,
                            depth_bottom_cm, original_observation)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::jsonb) RETURNING id
                        """,
                        trench_id, data["code"], _coerce_date(data.get("opened_on")),
                        _coerce_date(data.get("closed_on")), data.get("description"),
                        data.get("soil_color"), data.get("soil_texture"),
                        data.get("depth_top_cm"), data.get("depth_bottom_cm"),
                        json.dumps(data.get("original_observation") or {}),
                    )
                    for pid in data.get("parent_ids") or []:
                        await conn.execute(
                            "INSERT INTO layer_parents (child_id, parent_id, relation) "
                            "VALUES ($1,$2,$3)",
                            layer_id, pid, data.get("relation", "stratigraphic"),
                        )
                    ids[f"{index}:layer"] = str(layer_id)
                    if ref:
                        refs[ref] = layer_id

                elif op == "parent_link":
                    await conn.execute(
                        "INSERT INTO layer_parents (child_id, parent_id, relation) "
                        "VALUES ($1,$2,$3)",
                        data["child_id"], data["parent_id"],
                        data.get("relation", "stratigraphic"),
                    )
                    ids[f"{index}:parent_link"] = "ok"

                elif op == "find":
                    find_id = await conn.fetchval(
                        """
                        INSERT INTO finds (layer_id, code, category, found_on,
                            z_elevation, note, position)
                        VALUES ($1,$2,$3,$4,$5,$6,
                            CASE WHEN $7::text IS NULL THEN NULL
                                 ELSE ST_GeomFromGeoJSON($7::text) END) RETURNING id
                        """,
                        data["layer_id"], data["code"], data["category"],
                        _coerce_date(data.get("found_on")), data.get("z_elevation"),
                        data.get("note"),
                        json.dumps(data["position"]) if data.get("position") else None,
                    )
                    ids[f"{index}:find"] = str(find_id)
                    if ref:
                        refs[ref] = find_id

                elif op == "sample":
                    sample_id = await conn.fetchval(
                        """
                        INSERT INTO samples (layer_id, find_id, code, material,
                            collected_on, note, position)
                        VALUES ($1,$2,$3,$4,$5,$6,
                            CASE WHEN $7::text IS NULL THEN NULL
                                 ELSE ST_GeomFromGeoJSON($7::text) END) RETURNING id
                        """,
                        data["layer_id"], data.get("find_id"), data["code"],
                        data["material"], _coerce_date(data.get("collected_on")),
                        data.get("note"),
                        json.dumps(data["position"]) if data.get("position") else None,
                    )
                    ids[f"{index}:sample"] = str(sample_id)
                    if ref:
                        refs[ref] = sample_id

                else:
                    raise BusinessError(f"{ctx}: 未知 op {op!r}", 400, "bad_op")

            await conn.execute(
                """
                INSERT INTO audit_events (event_type, entity_type, entity_id, payload)
                VALUES ('batch.committed', 'trench', $1::uuid,
                        json_build_object('trench_id', $1::uuid, 'items', $2::int)::jsonb)
                """,
                trench_id, len(items),
            )
    except (KeyError, asyncpg.PostgresError, BusinessError) as exc:
        if isinstance(exc, KeyError):
            detail = f"items 数据缺少必填字段: {exc}"
            sqlstate = None
        elif isinstance(exc, BusinessError):
            raise
        else:
            detail = getattr(exc, "detail", None) or str(exc).strip()
            sqlstate = getattr(exc, "sqlstate", None)
        raise BusinessError(
            f"批量导入失败，整批已回滚: {detail}",
            409, "batch_rolled_back",
            {"sqlstate": sqlstate, "processed_items": len(ids)},
        )

    return {"committed": True, "count": len(items), "ids": ids, "error": None}
